from datetime import datetime, timezone
import re
from typing import Any
from app.schemas.eligibility import OverallEligibilityClassification
from app.schemas.opportunity import FundingType, OpportunityBase, VerificationStatus
from app.schemas.ranking import (
    ActionItemPriority,
    ActionItemStatus,
    ApplicationActionItem,
    CandidateOpportunityInput,
    DeadlineFeasibilityStatus,
    ExcludedOpportunityItem,
    RankedOpportunityItem,
    RankingRequest,
    RankingResponse,
    ScoreComponentDetail,
)
from app.schemas.student_profile import StudentProfileBase


# Authoritative, immutable component weights summing to 1.0 (100%)
WEIGHT_ACADEMIC_FIT = 0.35
WEIGHT_EXPERIENCE_FIT = 0.25
WEIGHT_FUNDING_FIT = 0.25
WEIGHT_DEADLINE_FIT = 0.15

COMPONENT_WEIGHTS = {
    "academic_fit": WEIGHT_ACADEMIC_FIT,
    "experience_fit": WEIGHT_EXPERIENCE_FIT,
    "funding_fit": WEIGHT_FUNDING_FIT,
    "deadline_fit": WEIGHT_DEADLINE_FIT,
}


class RankingAndStrategyAgent:
    """
    Deterministic, explainable Ranking & Application Strategy Agent.
    Evaluates candidate opportunities against a student profile using
    eligibility as a strict gate, computing transparent weighted profile-fit scores,
    and generating actionable application next steps.
    """

    def __init__(self) -> None:
        # Validate authoritative weights on initialization
        total_weight = sum(COMPONENT_WEIGHTS.values())
        if abs(total_weight - 1.0) > 0.0001:
            raise ValueError(f"Authoritative ranking weights must sum to 1.0, got {total_weight}")

    async def rank(self, request: RankingRequest) -> RankingResponse:
        """
        Rank candidate opportunities deterministically, enforce eligibility gating,
        and generate prioritized application action items.
        """
        ref_time = request.reference_date if request.reference_date is not None else datetime.now(timezone.utc)
        
        recommended_candidates: list[RankedOpportunityItem] = []
        needs_review_candidates: list[RankedOpportunityItem] = []
        excluded_candidates: list[ExcludedOpportunityItem] = []
        all_actions: list[ApplicationActionItem] = []
        warnings: list[str] = []

        # Deduplicate candidates by unique opportunity identity (name + institution)
        seen_keys: set[str] = set()
        unique_candidates: list[CandidateOpportunityInput] = []
        for cand in request.candidates:
            key = f"{cand.opportunity.name.strip().lower()}::{cand.opportunity.institution.strip().lower()}"
            if key in seen_keys:
                warnings.append(f"Duplicate opportunity '{cand.opportunity.name}' at '{cand.opportunity.institution}' skipped.")
                continue
            seen_keys.add(key)
            unique_candidates.append(cand)

        for cand in unique_candidates:
            opp = cand.opportunity
            elig_status = cand.eligibility_classification

            # 1. Deadline feasibility calculation using supplied reference date
            deadline_status, deadline_reason = self._assess_deadline_feasibility(opp.deadline, ref_time)

            # 2. Score calculation (pure deterministic function)
            scores, score_explanation, strengths, gaps = self._compute_profile_fit(
                profile=request.student_profile,
                opp=opp,
                deadline_status=deadline_status,
            )

            # Weighted fit score
            fit_score = round(sum(s.weighted_score for s in scores.values()), 2)
            known_weight_sum = sum(s.weight for s in scores.values() if s.is_known)
            coverage_pct = round(known_weight_sum * 100.0, 1)

            # 3. Generate actionable next steps
            cand_actions = self._generate_actions(
                profile=request.student_profile,
                cand=cand,
                deadline_status=deadline_status,
            )
            all_actions.extend(cand_actions)

            # Evidence references
            evidence_refs = []
            if opp.official_url:
                evidence_refs.append(str(opp.official_url))

            # Funding & Deadline summaries
            funding_summary = self._summarize_funding(opp)
            deadline_summary = self._summarize_deadline(opp, deadline_status, ref_time)

            # 4. Strict Eligibility & Deadline Gating
            # Rule A: Confirmed failure (INELIGIBLE) must NEVER be recommended
            if elig_status == OverallEligibilityClassification.INELIGIBLE:
                reasons = cand.disqualifying_criteria or ["Failed one or more mandatory eligibility requirements."]
                excluded_candidates.append(
                    ExcludedOpportunityItem(
                        opportunity_name=opp.name,
                        institution=opp.institution,
                        exclusion_reason=f"Eligibility failure: {'; '.join(reasons)}",
                        eligibility_classification=elig_status,
                        deadline_feasibility=deadline_status,
                        disqualifying_criteria=cand.disqualifying_criteria,
                        fit_score=fit_score,
                        recommended_actions=cand_actions,
                    )
                )
                continue

            # Rule B: Confirmed closed deadline cannot be actionable
            if deadline_status == DeadlineFeasibilityStatus.CLOSED:
                excluded_candidates.append(
                    ExcludedOpportunityItem(
                        opportunity_name=opp.name,
                        institution=opp.institution,
                        exclusion_reason=f"Application deadline closed: {deadline_reason}",
                        eligibility_classification=elig_status,
                        deadline_feasibility=deadline_status,
                        disqualifying_criteria=cand.disqualifying_criteria,
                        fit_score=fit_score,
                        recommended_actions=cand_actions,
                    )
                )
                continue

            # Assemble ranked item
            ranked_item = RankedOpportunityItem(
                opportunity=opp,
                rank=1,  # Temporary rank, adjusted after sorting
                fit_score=fit_score,
                max_score=100.0,
                score_coverage_pct=coverage_pct,
                score_components=scores,
                score_explanation=score_explanation,
                eligibility_classification=elig_status,
                disqualifying_criteria=cand.disqualifying_criteria,
                unknown_criteria=cand.unknown_criteria,
                funding_summary=funding_summary,
                deadline_summary=deadline_summary,
                deadline_feasibility=deadline_status,
                deadline_feasibility_reason=deadline_reason,
                main_strengths=strengths,
                main_gaps=gaps,
                recommended_actions=cand_actions,
                evidence_references=evidence_refs,
                caveats=cand.evidence_caveats,
            )

            # Rule C: Confirmed ELIGIBLE goes to recommended candidates
            if elig_status == OverallEligibilityClassification.ELIGIBLE:
                recommended_candidates.append(ranked_item)
            else:
                # NEEDS_REVIEW, INSUFFICIENT_EVIDENCE, or NOT_ASSESSABLE
                # Must be surfaced in needs_review, never falsely presented as eligible
                needs_review_candidates.append(ranked_item)

        # 5. Deterministic sorting with stable tie-breaking:
        # Sort key: (-fit_score, -score_coverage_pct, opp.name, opp.institution)
        recommended_candidates.sort(
            key=lambda x: (-x.fit_score, -x.score_coverage_pct, x.opportunity.name, x.opportunity.institution)
        )
        needs_review_candidates.sort(
            key=lambda x: (-x.fit_score, -x.score_coverage_pct, x.opportunity.name, x.opportunity.institution)
        )

        # Slice recommended candidates to max_shortlist_size
        shortlist = recommended_candidates[: request.max_shortlist_size]
        for i, item in enumerate(shortlist, start=1):
            item.rank = i

        for i, item in enumerate(needs_review_candidates, start=1):
            item.rank = i

        # Deduplicate and sort action items by priority (CRITICAL -> HIGH -> MEDIUM -> LOW)
        priority_order = {
            ActionItemPriority.CRITICAL: 0,
            ActionItemPriority.HIGH: 1,
            ActionItemPriority.MEDIUM: 2,
            ActionItemPriority.LOW: 3,
        }
        seen_action_keys: set[str] = set()
        deduped_actions: list[ApplicationActionItem] = []
        for action in all_actions:
            act_key = f"{action.title.lower()}::{action.opportunity_name or ''}"
            if act_key not in seen_action_keys:
                seen_action_keys.add(act_key)
                deduped_actions.append(action)

        deduped_actions.sort(key=lambda a: (priority_order.get(a.priority, 9), a.title))

        is_complete = not (
            any(item.score_coverage_pct < 100.0 for item in shortlist)
            or bool(needs_review_candidates)
            or bool(warnings)
        )

        return RankingResponse(
            recommended_shortlist=shortlist,
            needs_review_shortlist=needs_review_candidates,
            excluded_opportunities=excluded_candidates,
            prioritized_action_plan=deduped_actions,
            methodology="deterministic_weighted_fit_v1",
            configured_weights=COMPONENT_WEIGHTS,
            is_complete=is_complete,
            warnings=warnings,
            generated_at=datetime.now(timezone.utc),
        )

    def _assess_deadline_feasibility(
        self,
        deadline: datetime | None,
        ref_time: datetime,
    ) -> tuple[DeadlineFeasibilityStatus, str]:
        """
        Evaluate deadline feasibility deterministically relative to reference date.
        """
        if deadline is None:
            return (
                DeadlineFeasibilityStatus.UNKNOWN,
                "No explicit application deadline specified or verified.",
            )

        # Ensure tz-aware comparison
        d_val = deadline if deadline.tzinfo else deadline.replace(tzinfo=timezone.utc)
        r_val = ref_time if ref_time.tzinfo else ref_time.replace(tzinfo=timezone.utc)

        delta = d_val - r_val
        days_remaining = delta.total_seconds() / 86400.0

        if days_remaining < 0:
            return (
                DeadlineFeasibilityStatus.CLOSED,
                f"Deadline passed {abs(round(days_remaining, 1))} days ago on {d_val.strftime('%Y-%m-%d')}.",
            )
        elif days_remaining <= 14.0:
            return (
                DeadlineFeasibilityStatus.CLOSING_SOON,
                f"Closing soon: {round(days_remaining, 1)} days remaining until {d_val.strftime('%Y-%m-%d')}.",
            )
        else:
            return (
                DeadlineFeasibilityStatus.OPEN,
                f"Open: {round(days_remaining, 1)} days remaining until {d_val.strftime('%Y-%m-%d')}.",
            )

    def _compute_profile_fit(
        self,
        profile: StudentProfileBase,
        opp: OpportunityBase,
        deadline_status: DeadlineFeasibilityStatus,
    ) -> tuple[dict[str, ScoreComponentDetail], str, list[str], list[str]]:
        """
        Compute transparent, evidence-aware profile fit score components.
        """
        scores: dict[str, ScoreComponentDetail] = {}
        strengths: list[str] = []
        gaps: list[str] = []

        # 1. Academic & Program Fit (Weight 0.35)
        acad_raw, acad_known, acad_expl = self._score_academic_fit(profile, opp, strengths, gaps)
        scores["academic_fit"] = ScoreComponentDetail(
            weight=WEIGHT_ACADEMIC_FIT,
            raw_score=round(acad_raw, 2) if acad_raw is not None else None,
            weighted_score=round(WEIGHT_ACADEMIC_FIT * acad_raw, 2) if acad_raw is not None else 0.0,
            is_known=acad_known,
            explanation=acad_expl,
        )

        # 2. Project & Experience Fit (Weight 0.25)
        exp_raw, exp_known, exp_expl = self._score_experience_fit(profile, opp, strengths, gaps)
        scores["experience_fit"] = ScoreComponentDetail(
            weight=WEIGHT_EXPERIENCE_FIT,
            raw_score=round(exp_raw, 2) if exp_raw is not None else None,
            weighted_score=round(WEIGHT_EXPERIENCE_FIT * exp_raw, 2) if exp_raw is not None else 0.0,
            is_known=exp_known,
            explanation=exp_expl,
        )

        # 3. Funding Alignment (Weight 0.25)
        fund_raw, fund_known, fund_expl = self._score_funding_fit(profile, opp, strengths, gaps)
        scores["funding_fit"] = ScoreComponentDetail(
            weight=WEIGHT_FUNDING_FIT,
            raw_score=round(fund_raw, 2) if fund_raw is not None else None,
            weighted_score=round(WEIGHT_FUNDING_FIT * fund_raw, 2) if fund_raw is not None else 0.0,
            is_known=fund_known,
            explanation=fund_expl,
        )

        # 4. Deadline Feasibility (Weight 0.15)
        dead_raw, dead_known, dead_expl = self._score_deadline_fit(deadline_status, opp, strengths, gaps)
        scores["deadline_fit"] = ScoreComponentDetail(
            weight=WEIGHT_DEADLINE_FIT,
            raw_score=round(dead_raw, 2) if dead_raw is not None else None,
            weighted_score=round(WEIGHT_DEADLINE_FIT * dead_raw, 2) if dead_raw is not None else 0.0,
            is_known=dead_known,
            explanation=dead_expl,
        )

        # Combined summary explanation
        known_count = sum(1 for s in scores.values() if s.is_known)
        summary = (
            f"Overall profile fit computed across {known_count}/4 components. "
            f"Academic: {acad_expl} | Experience: {exp_expl} | Funding: {fund_expl} | Deadline: {dead_expl}"
        )

        return scores, summary, strengths, gaps

    def _score_academic_fit(
        self,
        profile: StudentProfileBase,
        opp: OpportunityBase,
        strengths: list[str],
        gaps: list[str],
    ) -> tuple[float | None, bool, str]:
        """
        Evaluate academic score strength, target destination match, and field alignment.
        """
        points = 0.0
        max_possible = 100.0
        components_found = 0

        # Destination country alignment
        if opp.destination_country:
            components_found += 1
            norm_dest = opp.destination_country.strip().lower()
            student_dests = [d.strip().lower() for d in profile.target_destinations]
            if any(norm_dest in sd or sd in norm_dest for sd in student_dests):
                points += 35.0
                strengths.append(f"Destination country '{opp.destination_country}' matches student target list.")
            else:
                points += 10.0
                gaps.append(f"Destination '{opp.destination_country}' is not in student's target destinations.")

        # Academic score / GPA standing
        if profile.academic_score and profile.academic_score.score is not None:
            components_found += 1
            score = profile.academic_score.score
            scale = profile.academic_score.scale or 4.0
            ratio = min(1.0, max(0.0, score / scale))
            score_pts = ratio * 40.0
            points += score_pts
            if ratio >= 0.85:
                strengths.append(f"Strong academic record: {score}/{scale} ({round(ratio*100)}%).")
            elif ratio < 0.70:
                gaps.append(f"Moderate academic standing: {score}/{scale}.")
        else:
            gaps.append("Academic GPA/score is not specified in student profile.")

        # Field of study / keywords matching opportunity name
        if profile.field_of_study:
            components_found += 1
            field_norm = profile.field_of_study.strip().lower()
            opp_name_norm = opp.name.strip().lower()
            if field_norm in opp_name_norm or any(token in opp_name_norm for token in field_norm.split() if len(token) > 3):
                points += 25.0
                strengths.append(f"Primary field '{profile.field_of_study}' aligns with program title.")
            else:
                points += 15.0
        elif profile.academic_interests:
            components_found += 1
            points += 15.0

        if components_found == 0:
            return None, False, "Insufficient academic profile data to score academic fit."

        raw = min(100.0, points)
        return raw, True, f"Academic alignment score: {round(raw, 1)}/100."

    def _score_experience_fit(
        self,
        profile: StudentProfileBase,
        opp: OpportunityBase,
        strengths: list[str],
        gaps: list[str],
    ) -> tuple[float | None, bool, str]:
        """
        Evaluate project and research experiences alignment.
        """
        projects = profile.projects_experiences
        if not projects:
            gaps.append("No project or research experiences documented in profile.")
            return 30.0, True, "Baseline experience score (no specific projects listed in profile)."

        points = 40.0  # Base points for having verified experiences
        matched_skills = 0
        opp_text = f"{opp.name} {opp.institution}".lower()

        for proj in projects:
            for tech in proj.technologies:
                if tech.strip().lower() in opp_text:
                    matched_skills += 1

        points += min(60.0, len(projects) * 15.0 + matched_skills * 10.0)
        strengths.append(f"Candidate documents {len(projects)} relevant project/research experience(s).")

        raw = min(100.0, points)
        return raw, True, f"Experience alignment score: {round(raw, 1)}/100 based on {len(projects)} project(s)."

    def _score_funding_fit(
        self,
        profile: StudentProfileBase,
        opp: OpportunityBase,
        strengths: list[str],
        gaps: list[str],
    ) -> tuple[float | None, bool, str]:
        """
        Evaluate funding coverage against student budget constraint.
        """
        funding = opp.funding
        budget = profile.budget_constraint

        if not funding or funding.funding_type == FundingType.UNKNOWN:
            gaps.append("Funding amount or coverage type is unverified/unknown for this opportunity.")
            return None, False, "Opportunity funding details are unverified or unknown."

        # Full coverage
        if funding.funding_type == FundingType.FULL:
            strengths.append("Fully funded opportunity (covers tuition and living expenses).")
            return 100.0, True, "Fully funded opportunity matches all student financial requirements."

        # Research/Teaching assistantship
        if funding.funding_type in (FundingType.RESEARCH_ASSISTANTSHIP, FundingType.TEACHING_ASSISTANTSHIP):
            strengths.append(f"Substantial funding via {funding.funding_type.value.replace('_', ' ')}.")
            return 85.0, True, "Graduate assistantship provides substantial funding."

        # Partial / Tuition only
        if funding.funding_type in (FundingType.PARTIAL, FundingType.TUITION_ONLY):
            if budget and budget.requires_full_funding:
                gaps.append("Student requires full funding, but opportunity provides only partial/tuition support.")
                return 40.0, True, "Partial funding does not satisfy student's 100% full-funding requirement."
            strengths.append(f"Provides {funding.funding_type.value.replace('_', ' ')} coverage.")
            return 65.0, True, "Partial or tuition-only funding support."

        # Loan or nominal
        if funding.funding_type == FundingType.LOAN:
            gaps.append("Opportunity is loan-based, not grant/scholarship funding.")
            return 20.0, True, "Loan-based funding option."

        return 50.0, True, f"Standard funding category: {funding.funding_type.value}."

    def _score_deadline_fit(
        self,
        deadline_status: DeadlineFeasibilityStatus,
        opp: OpportunityBase,
        strengths: list[str],
        gaps: list[str],
    ) -> tuple[float | None, bool, str]:
        """
        Score deadline feasibility using verified deadline status.
        """
        if deadline_status == DeadlineFeasibilityStatus.OPEN:
            strengths.append("Application deadline is open with ample preparation time.")
            return 100.0, True, "Deadline is open with sufficient preparation buffer."
        elif deadline_status == DeadlineFeasibilityStatus.CLOSING_SOON:
            gaps.append("Urgent deadline: closing within 14 days.")
            return 60.0, True, "Deadline is closing soon; expedited preparation required."
        elif deadline_status == DeadlineFeasibilityStatus.CLOSED:
            gaps.append("Application deadline has passed.")
            return 0.0, True, "Application deadline has closed."
        elif deadline_status == DeadlineFeasibilityStatus.NOT_APPLICABLE:
            return 80.0, True, "Rolling admission or open deadline."
        else:
            gaps.append("Application deadline is unverified or unknown on official source.")
            return None, False, "Official application deadline is unknown or unverified."

    def _generate_actions(
        self,
        profile: StudentProfileBase,
        cand: CandidateOpportunityInput,
        deadline_status: DeadlineFeasibilityStatus,
    ) -> list[ApplicationActionItem]:
        """
        Generate deterministic next steps based on verified gaps, deadlines, and criteria.
        """
        actions: list[ApplicationActionItem] = []
        opp = cand.opportunity

        # 1. Critical Deadline Action
        if deadline_status == DeadlineFeasibilityStatus.CLOSING_SOON:
            actions.append(
                ApplicationActionItem(
                    title=f"Expedite Application Submission for {opp.name}",
                    reason="Application closes in less than 14 days.",
                    priority=ActionItemPriority.CRITICAL,
                    status=ActionItemStatus.REQUIRED,
                    opportunity_name=opp.name,
                    source_url=str(opp.official_url) if opp.official_url else None,
                )
            )
        elif deadline_status == DeadlineFeasibilityStatus.UNKNOWN:
            actions.append(
                ApplicationActionItem(
                    title=f"Confirm Official Application Deadline for {opp.name}",
                    reason="Official deadline was not verified on inspected official pages.",
                    priority=ActionItemPriority.HIGH,
                    status=ActionItemStatus.VERIFICATION_NEEDED,
                    opportunity_name=opp.name,
                    source_url=str(opp.official_url) if opp.official_url else None,
                )
            )

        # 2. Eligibility Follow-ups
        for unk in cand.unknown_criteria:
            actions.append(
                ApplicationActionItem(
                    title=f"Clarify Eligibility Requirement: {unk[:60]}...",
                    reason=f"Evaluation could not be completed deterministically: {unk}",
                    priority=ActionItemPriority.HIGH,
                    status=ActionItemStatus.VERIFICATION_NEEDED,
                    opportunity_name=opp.name,
                    criterion_reference=unk,
                    source_url=str(opp.official_url) if opp.official_url else None,
                )
            )

        # 3. Disqualifying Criteria Review (for excluded or review items)
        for disq in cand.disqualifying_criteria:
            actions.append(
                ApplicationActionItem(
                    title=f"Review Disqualifying Criterion: {disq[:60]}...",
                    reason=f"Applicant does not currently satisfy mandatory requirement: {disq}",
                    priority=ActionItemPriority.CRITICAL,
                    status=ActionItemStatus.REQUIRED,
                    opportunity_name=opp.name,
                    criterion_reference=disq,
                )
            )

        # 4. Academic Profile Gaps
        if profile.academic_score is None:
            actions.append(
                ApplicationActionItem(
                    title="Obtain Official Academic Transcript and GPA Scale",
                    reason="Student profile lacks explicit numerical score and scale.",
                    priority=ActionItemPriority.HIGH,
                    status=ActionItemStatus.REQUIRED,
                )
            )

        # 5. Funding Verification
        if not opp.funding or opp.funding.funding_type == FundingType.UNKNOWN:
            actions.append(
                ApplicationActionItem(
                    title=f"Verify Financial Aid & Fee Requirements for {opp.name}",
                    reason="Funding amounts and coverage are unconfirmed on official pages.",
                    priority=ActionItemPriority.MEDIUM,
                    status=ActionItemStatus.VERIFICATION_NEEDED,
                    opportunity_name=opp.name,
                    source_url=str(opp.official_url) if opp.official_url else None,
                )
            )

        return actions

    def _summarize_funding(self, opp: OpportunityBase) -> str:
        """Concise funding summary."""
        if not opp.funding or opp.funding.funding_type == FundingType.UNKNOWN:
            return "Funding details unverified / unknown on official source."
        ft = opp.funding.funding_type.value.replace("_", " ").title()
        amt_str = f" ({opp.funding.amount} {opp.funding.currency or ''})" if opp.funding.amount else ""
        period_str = f" {opp.funding.period}" if opp.funding.period else ""
        return f"{ft} funding{amt_str}{period_str}."

    def _summarize_deadline(
        self,
        opp: OpportunityBase,
        status: DeadlineFeasibilityStatus,
        ref_time: datetime,
    ) -> str:
        """Concise deadline summary."""
        if not opp.deadline:
            return "Application deadline unverified on official source."
        d_str = opp.deadline.strftime("%Y-%m-%d")
        return f"Deadline: {d_str} (Status: {status.value.upper()})."
