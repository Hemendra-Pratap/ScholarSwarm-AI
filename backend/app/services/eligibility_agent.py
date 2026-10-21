from datetime import datetime, timezone
from typing import Any
from app.schemas.eligibility import (
    CriterionRuleDefinition,
    CriterionScope,
    EligibilityAuditRequest,
    EligibilityAuditResponse,
    EvaluatedCriterion,
    OverallEligibilityClassification,
    RuleOperator,
    ScopeAuditResult,
)
from app.schemas.eligibility_assessment import EligibilityStatus
from app.schemas.student_profile import AcademicScore, StudentProfileBase
from app.schemas.verification import (
    CandidateVerificationReport,
    SourceClassification,
)


class EligibilityAuditAgent:
    """
    Deterministic, evidence-driven eligibility audit agent.
    Evaluates student profile data against explicitly represented criteria
    for admission, scholarship, or combined scopes.
    """

    def __init__(self) -> None:
        pass

    async def audit(self, request: EligibilityAuditRequest) -> EligibilityAuditResponse:
        """
        Evaluate all criteria deterministically, separating admission and scholarship scopes,
        and producing a conservative, auditable decision.
        """
        evaluated_criteria: list[EvaluatedCriterion] = []
        evidence_caveats: list[str] = []

        # 1. Map official URLs from verification report if provided
        verified_official_urls: set[str] = set()
        if request.verification_report:
            if request.verification_report.verified_official_url:
                verified_official_urls.add(str(request.verification_report.verified_official_url).rstrip("/"))
            for sa in request.verification_report.source_assessments:
                if sa.classification == SourceClassification.OFFICIAL:
                    verified_official_urls.add(str(sa.source_url).rstrip("/"))

        # 2. Evaluate each criterion individually
        for criterion in request.criteria:
            evaluated = self._evaluate_criterion(
                criterion=criterion,
                profile=request.student_profile,
                conflicting_fields=set(request.conflicting_profile_fields),
                verified_official_urls=verified_official_urls,
                verification_report=request.verification_report,
                evidence_caveats=evidence_caveats,
            )
            evaluated_criteria.append(evaluated)

        # 3. Aggregate results per scope
        admission_criteria = [c for c in evaluated_criteria if c.scope in (CriterionScope.ADMISSION, CriterionScope.BOTH)]
        scholarship_criteria = [c for c in evaluated_criteria if c.scope in (CriterionScope.SCHOLARSHIP, CriterionScope.BOTH)]

        admission_result = self._aggregate_scope(CriterionScope.ADMISSION, admission_criteria) if admission_criteria else None
        scholarship_result = self._aggregate_scope(CriterionScope.SCHOLARSHIP, scholarship_criteria) if scholarship_criteria else None

        # 4. Overall combined classification
        overall_classification = self._aggregate_overall(admission_result, scholarship_result, evaluated_criteria)

        # 5. Extract disqualifying and unknown criteria
        disqualifying = [
            f"[{c.scope.value.upper()}] {c.description}: {c.reason}"
            for c in evaluated_criteria
            if c.outcome == EligibilityStatus.NOT_MET and c.mandatory
        ]
        unknown = [
            f"[{c.scope.value.upper()}] {c.description}: {c.reason}"
            for c in evaluated_criteria
            if c.outcome == EligibilityStatus.UNKNOWN
        ]

        is_incomplete = any(c.outcome == EligibilityStatus.UNKNOWN and c.mandatory for c in evaluated_criteria)

        return EligibilityAuditResponse(
            opportunity_name=request.opportunity_name,
            institution=request.institution,
            admission_assessment=admission_result,
            scholarship_assessment=scholarship_result,
            overall_classification=overall_classification,
            evaluated_criteria=evaluated_criteria,
            disqualifying_criteria=disqualifying,
            unknown_criteria=unknown,
            evidence_caveats=list(dict.fromkeys(evidence_caveats)),
            is_incomplete=is_incomplete,
            evaluated_at=datetime.now(timezone.utc),
        )

    def _evaluate_criterion(
        self,
        criterion: EvaluatedCriterion,
        profile: StudentProfileBase,
        conflicting_fields: set[str],
        verified_official_urls: set[str],
        verification_report: CandidateVerificationReport | None,
        evidence_caveats: list[str],
    ) -> EvaluatedCriterion:
        """
        Evaluate a single criterion against profile data and evidence gates.
        """
        # If the input criterion is already explicitly marked NOT_APPLICABLE with a defensible reason
        if criterion.outcome == EligibilityStatus.NOT_APPLICABLE:
            return criterion.model_copy()

        # Evidence-Quality Gate:
        # A criterion must be supported by official source evidence.
        evidence_status = self._verify_evidence_quality(
            criterion=criterion,
            verified_official_urls=verified_official_urls,
            verification_report=verification_report,
            evidence_caveats=evidence_caveats,
        )

        # If rule definition is missing (unstructured / unsupported natural language rule)
        if criterion.rule is None:
            return criterion.model_copy(
                update={
                    "outcome": EligibilityStatus.UNKNOWN,
                    "reason": f"Unsupported or unparsed natural-language criterion: '{criterion.description}'. Deterministic rule definition required.",
                    "student_value": None,
                }
            )

        rule = criterion.rule
        target_field = rule.target_field

        # Check if the required field is conflicting or ambiguous
        if target_field in conflicting_fields:
            return criterion.model_copy(
                update={
                    "outcome": EligibilityStatus.UNKNOWN,
                    "reason": f"Student profile field '{target_field}' has conflicting or unresolved values.",
                    "student_value": None,
                }
            )

        # Extract student value safely
        student_val = getattr(profile, target_field, None)

        if student_val is None:
            return criterion.model_copy(
                update={
                    "outcome": EligibilityStatus.UNKNOWN,
                    "reason": f"Missing required student profile attribute: '{target_field}'.",
                    "student_value": None,
                }
            )

        # Evaluate deterministic rule by type
        outcome, reason, logged_val = self._apply_deterministic_rule(rule, student_val)

        # If the deterministic comparison evaluated to MET, but the evidence gate failed or was unverified,
        # conservative semantics forbid confirming eligibility!
        if outcome == EligibilityStatus.MET and not evidence_status["is_valid_official"]:
            outcome = EligibilityStatus.UNKNOWN
            reason = f"Criterion condition satisfied by profile, but official evidence verification failed: {evidence_status['reason']}"

        return criterion.model_copy(
            update={
                "outcome": outcome,
                "reason": reason,
                "student_value": logged_val,
                "is_official_evidence": evidence_status["is_valid_official"],
            }
        )

    def _verify_evidence_quality(
        self,
        criterion: EvaluatedCriterion,
        verified_official_urls: set[str],
        verification_report: CandidateVerificationReport | None,
        evidence_caveats: list[str],
    ) -> dict[str, Any]:
        """
        Validate whether the criterion has verifiable official backing.
        Does not allow third-party search snippets to confirm eligibility claims.
        """
        if not criterion.source_url or not criterion.evidence_excerpt:
            msg = f"Criterion '{criterion.description}' lacks required source URL or evidence excerpt."
            evidence_caveats.append(msg)
            return {"is_valid_official": False, "reason": msg}

        norm_url = str(criterion.source_url).rstrip("/")

        # Check if the source is known to be official
        is_official = criterion.is_official_evidence or (norm_url in verified_official_urls)

        # If a verification report exists, cross-check against its source assessments
        if verification_report:
            for sa in verification_report.source_assessments:
                if str(sa.source_url).rstrip("/") == norm_url:
                    if sa.classification == SourceClassification.THIRD_PARTY:
                        msg = f"Source URL '{norm_url}' is classified as third-party, which cannot authoritatively verify eligibility."
                        evidence_caveats.append(msg)
                        return {"is_valid_official": False, "reason": msg}
                    elif sa.classification == SourceClassification.UNCERTAIN:
                        msg = f"Source URL '{norm_url}' is of uncertain classification."
                        evidence_caveats.append(msg)
                        return {"is_valid_official": False, "reason": msg}
                    elif sa.retrieval_status in ("timeout", "blocked_url", "http_error", "failed"):
                        msg = f"Source URL '{norm_url}' was inaccessible ({sa.retrieval_status})."
                        evidence_caveats.append(msg)
                        return {"is_valid_official": False, "reason": msg}

        if not is_official:
            msg = f"Source URL '{norm_url}' has not been confirmed as an official institutional domain."
            evidence_caveats.append(msg)
            return {"is_valid_official": False, "reason": msg}

        return {"is_valid_official": True, "reason": "Verified official evidence present."}

    def _apply_deterministic_rule(
        self,
        rule: CriterionRuleDefinition,
        student_val: Any,
    ) -> tuple[EligibilityStatus, str, Any]:
        """
        Apply supported operators deterministically without arbitrary execution.
        """
        # Academic score comparisons
        if isinstance(student_val, AcademicScore) or rule.target_field == "academic_score":
            return self._compare_academic_score(rule, student_val)

        # Numeric direct comparison
        if isinstance(rule.expected_value, (int, float)) and isinstance(student_val, (int, float)):
            return self._compare_numeric(rule.operator, student_val, rule.expected_value)

        # String / Categorical comparisons
        if isinstance(rule.expected_value, str) and isinstance(student_val, str):
            return self._compare_string(rule.operator, student_val, rule.expected_value)

        # List membership: rule.expected_value is list of allowed values, student_val is scalar string
        if isinstance(rule.expected_value, list) and isinstance(student_val, str):
            return self._compare_in_list(rule.operator, student_val, rule.expected_value)

        # List membership: student_val is list of strings (e.g. target_destinations, academic_interests)
        if isinstance(student_val, list) and isinstance(rule.expected_value, str):
            return self._compare_list_contains(rule.operator, student_val, rule.expected_value)

        return (
            EligibilityStatus.UNKNOWN,
            f"Unsupported rule comparison: type mismatch between student value ({type(student_val).__name__}) and rule expected value ({type(rule.expected_value).__name__}).",
            str(student_val),
        )

    def _compare_academic_score(
        self,
        rule: CriterionRuleDefinition,
        score_obj: Any,
    ) -> tuple[EligibilityStatus, str, Any]:
        """
        Evaluate academic score/GPA strictly verifying numeric value and scale.
        Never compares scores across incompatible scales.
        """
        if not isinstance(score_obj, AcademicScore):
            return (
                EligibilityStatus.UNKNOWN,
                "Malformed academic score: expected structured AcademicScore object.",
                str(score_obj),
            )

        student_score = score_obj.score
        student_scale = score_obj.scale
        expected_threshold = rule.expected_value
        expected_scale = rule.scale

        if not isinstance(expected_threshold, (int, float)):
            return (
                EligibilityStatus.UNKNOWN,
                f"Invalid score rule threshold: expected numeric value, got {type(expected_threshold).__name__}.",
                {"score": student_score, "scale": student_scale},
            )

        # Incompatible scale check
        if expected_scale is not None and student_scale is not None:
            if abs(expected_scale - student_scale) > 0.001:
                return (
                    EligibilityStatus.UNKNOWN,
                    f"Incompatible score scales: student score scale is {student_scale}, but criterion requires scale {expected_scale}. Automatic conversion not permitted.",
                    {"score": student_score, "scale": student_scale},
                )
        elif (expected_scale is not None and student_scale is None) or (expected_scale is None and student_scale is not None):
            return (
                EligibilityStatus.UNKNOWN,
                f"Missing scale information for score comparison (student scale: {student_scale}, criterion scale: {expected_scale}). Cannot verify scale equivalence safely.",
                {"score": student_score, "scale": student_scale},
            )

        # Perform numeric comparison
        status, reason, _ = self._compare_numeric(rule.operator, student_score, float(expected_threshold))
        scale_suffix = f" (on scale {student_scale})" if student_scale else ""
        return (
            status,
            f"{reason}{scale_suffix}",
            {"score": student_score, "scale": student_scale},
        )

    def _compare_numeric(
        self,
        op: RuleOperator,
        val: float | int,
        threshold: float | int,
    ) -> tuple[EligibilityStatus, str, Any]:
        """Strict numeric comparison."""
        val_f = float(val)
        thresh_f = float(threshold)

        if op == RuleOperator.GREATER_THAN_OR_EQUAL:
            met = val_f >= thresh_f
            desc = f"Student value {val_f} >= required minimum {thresh_f}"
        elif op == RuleOperator.GREATER_THAN:
            met = val_f > thresh_f
            desc = f"Student value {val_f} > required minimum {thresh_f}"
        elif op == RuleOperator.LESS_THAN_OR_EQUAL:
            met = val_f <= thresh_f
            desc = f"Student value {val_f} <= required maximum {thresh_f}"
        elif op == RuleOperator.LESS_THAN:
            met = val_f < thresh_f
            desc = f"Student value {val_f} < required maximum {thresh_f}"
        elif op == RuleOperator.EQUALS:
            met = abs(val_f - thresh_f) < 0.00001
            desc = f"Student value {val_f} == required {thresh_f}"
        else:
            return (
                EligibilityStatus.UNKNOWN,
                f"Unsupported numeric operator '{op.value}'.",
                val,
            )

        if met:
            return EligibilityStatus.MET, f"Satisfied: {desc}.", val
        else:
            return EligibilityStatus.NOT_MET, f"Not satisfied: {desc}.", val

    def _compare_string(
        self,
        op: RuleOperator,
        val: str,
        expected: str,
    ) -> tuple[EligibilityStatus, str, Any]:
        """Case-insensitive categorical string comparison."""
        val_norm = val.strip().lower()
        exp_norm = expected.strip().lower()

        if op == RuleOperator.EQUALS:
            if val_norm == exp_norm:
                return EligibilityStatus.MET, f"Satisfied: '{val}' matches required '{expected}'.", val
            return EligibilityStatus.NOT_MET, f"Not satisfied: '{val}' does not match required '{expected}'.", val
        elif op == RuleOperator.CONTAINS:
            if exp_norm in val_norm or val_norm in exp_norm:
                return EligibilityStatus.MET, f"Satisfied: '{val}' corresponds to required '{expected}'.", val
            return EligibilityStatus.NOT_MET, f"Not satisfied: '{val}' does not contain '{expected}'.", val
        elif op in (RuleOperator.IN_LIST, RuleOperator.GREATER_THAN, RuleOperator.GREATER_THAN_OR_EQUAL, RuleOperator.LESS_THAN, RuleOperator.LESS_THAN_OR_EQUAL):
            return (
                EligibilityStatus.UNKNOWN,
                f"Operator '{op.value}' not applicable for single string comparison.",
                val,
            )
        return EligibilityStatus.UNKNOWN, f"Unknown operator '{op}'.", val

    def _compare_in_list(
        self,
        op: RuleOperator,
        student_val: str,
        expected_list: list[Any],
    ) -> tuple[EligibilityStatus, str, Any]:
        """Check if student scalar value is in allowed list."""
        if op not in (RuleOperator.IN_LIST, RuleOperator.EQUALS):
            return (
                EligibilityStatus.UNKNOWN,
                f"Operator '{op.value}' not supported for list membership check.",
                student_val,
            )

        val_norm = student_val.strip().lower()
        norm_list = [str(x).strip().lower() for x in expected_list]

        if val_norm in norm_list:
            return EligibilityStatus.MET, f"Satisfied: student value '{student_val}' is in permitted list.", student_val
        return EligibilityStatus.NOT_MET, f"Not satisfied: student value '{student_val}' is not in permitted list.", student_val

    def _compare_list_contains(
        self,
        op: RuleOperator,
        student_list: list[Any],
        expected_val: str,
    ) -> tuple[EligibilityStatus, str, Any]:
        """Check if student array contains required scalar value."""
        if op not in (RuleOperator.CONTAINS, RuleOperator.IN_LIST, RuleOperator.EQUALS):
            return (
                EligibilityStatus.UNKNOWN,
                f"Operator '{op.value}' not supported for student array check.",
                student_list,
            )

        exp_norm = expected_val.strip().lower()
        norm_student = [str(x).strip().lower() for x in student_list]

        if any(exp_norm == item or exp_norm in item for item in norm_student):
            return EligibilityStatus.MET, f"Satisfied: student list contains '{expected_val}'.", student_list
        return EligibilityStatus.NOT_MET, f"Not satisfied: student list does not include '{expected_val}'.", student_list

    def _aggregate_scope(
        self,
        scope: CriterionScope,
        criteria: list[EvaluatedCriterion],
    ) -> ScopeAuditResult:
        """
        Aggregate results for a given scope using conservative semantics.
        """
        total = len(criteria)
        met_count = sum(1 for c in criteria if c.outcome == EligibilityStatus.MET)
        not_met_count = sum(1 for c in criteria if c.outcome == EligibilityStatus.NOT_MET)
        unknown_count = sum(1 for c in criteria if c.outcome == EligibilityStatus.UNKNOWN)
        not_applicable_count = sum(1 for c in criteria if c.outcome == EligibilityStatus.NOT_APPLICABLE)

        disqualifying = [c.description for c in criteria if c.outcome == EligibilityStatus.NOT_MET and c.mandatory]
        unknown_mandatory = [c.description for c in criteria if c.outcome == EligibilityStatus.UNKNOWN and c.mandatory]

        follow_ups: list[str] = []
        for c in criteria:
            if c.outcome == EligibilityStatus.UNKNOWN:
                follow_ups.append(f"{c.description}: {c.reason}")

        # Classification decision rules:
        if total == 0:
            classification = OverallEligibilityClassification.NOT_ASSESSABLE
        elif disqualifying:
            classification = OverallEligibilityClassification.INELIGIBLE
        elif unknown_mandatory:
            # Check if all criteria are unknown or lack evidence
            applicable_count = total - not_applicable_count
            if unknown_count == applicable_count:
                classification = OverallEligibilityClassification.INSUFFICIENT_EVIDENCE
            else:
                classification = OverallEligibilityClassification.NEEDS_REVIEW
        else:
            # All mandatory criteria are MET (or not_applicable)
            applicable_mandatory = [c for c in criteria if c.mandatory and c.outcome != EligibilityStatus.NOT_APPLICABLE]
            if applicable_mandatory and all(c.outcome == EligibilityStatus.MET for c in applicable_mandatory):
                classification = OverallEligibilityClassification.ELIGIBLE
            elif not applicable_mandatory and not_applicable_count == total:
                classification = OverallEligibilityClassification.NOT_ASSESSABLE
            else:
                classification = OverallEligibilityClassification.NEEDS_REVIEW

        return ScopeAuditResult(
            scope=scope,
            overall_classification=classification,
            total_criteria=total,
            met_count=met_count,
            not_met_count=not_met_count,
            unknown_count=unknown_count,
            not_applicable_count=not_applicable_count,
            disqualifying_criteria=disqualifying,
            unknown_mandatory_criteria=unknown_mandatory,
            follow_up_requirements=follow_ups,
        )

    def _aggregate_overall(
        self,
        admission_result: ScopeAuditResult | None,
        scholarship_result: ScopeAuditResult | None,
        all_criteria: list[EvaluatedCriterion],
    ) -> OverallEligibilityClassification:
        """
        Conservative aggregation across scopes:
        - If no usable criteria: NOT_ASSESSABLE
        - If any mandatory criterion fails in any scope: INELIGIBLE
        - If both scopes present:
          - Both ELIGIBLE -> ELIGIBLE
          - Either INELIGIBLE -> INELIGIBLE
          - Either INSUFFICIENT_EVIDENCE -> INSUFFICIENT_EVIDENCE (unless ineligible)
          - Either NEEDS_REVIEW -> NEEDS_REVIEW
        """
        if not all_criteria:
            return OverallEligibilityClassification.NOT_ASSESSABLE

        scopes = [s for s in (admission_result, scholarship_result) if s is not None]
        if not scopes:
            return OverallEligibilityClassification.NOT_ASSESSABLE

        classes = [s.overall_classification for s in scopes]

        if OverallEligibilityClassification.INELIGIBLE in classes:
            return OverallEligibilityClassification.INELIGIBLE

        if OverallEligibilityClassification.INSUFFICIENT_EVIDENCE in classes:
            return OverallEligibilityClassification.INSUFFICIENT_EVIDENCE

        if OverallEligibilityClassification.NEEDS_REVIEW in classes:
            return OverallEligibilityClassification.NEEDS_REVIEW

        if all(c == OverallEligibilityClassification.ELIGIBLE for c in classes):
            return OverallEligibilityClassification.ELIGIBLE

        if all(c == OverallEligibilityClassification.NOT_ASSESSABLE for c in classes):
            return OverallEligibilityClassification.NOT_ASSESSABLE

        return OverallEligibilityClassification.NEEDS_REVIEW
