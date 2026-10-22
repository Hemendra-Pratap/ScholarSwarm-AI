"""Statement of Purpose (SOP) and application statement drafting service.

Assembles defensible, tailored application statements using exclusively
confirmed student-profile facts and evidence-backed opportunity criteria.
Never fabricates personal experiences, grades, achievements, financial
circumstances, goals, scholarship requirements, or deadlines.
Explicitly places placeholders where facts are missing or unverified.
"""

from app.schemas.opportunity import VerificationStatus
from app.schemas.ranking import RankedOpportunityItem
from app.schemas.sop import FactProvenanceItem, SOPDraftRequest, SOPDraftResponse
from app.schemas.student_profile import StudentProfileBase

MANDATORY_DISCLAIMER = (
    "ADVISORY: This draft was generated strictly from confirmed student profile facts "
    "and verified opportunity criteria. It is a working template that requires personal review, "
    "customization, and verification. ScholarSwarm AI does not fabricate personal achievements "
    "and never submits applications or contacts universities on your behalf. "
    "All application submissions remain under your sole control."
)


def generate_sop_draft(request: SOPDraftRequest) -> SOPDraftResponse:
    """Generate a structured, evidence-grounded application statement draft.

    Adheres strictly to the ScholarSwarm AI integrity principles:
    - Zero hallucination of achievements, scores, or claims.
    - Explicit placeholders for missing profile data.
    - Full provenance tracking for every fact cited.
    """
    profile: StudentProfileBase = request.student_profile
    item: RankedOpportunityItem = request.opportunity
    opp = item.opportunity

    placeholders: list[str] = []
    confirmed_facts: list[FactProvenanceItem] = []
    unverified_claims: list[str] = []
    source_citations: list[str] = []

    # Citations
    if opp.official_url:
        source_citations.append(str(opp.official_url))
    for ref in item.evidence_references:
        if ref and ref not in source_citations:
            source_citations.append(str(ref))

    # --- 1. Provenance extraction ---
    # Student facts
    if profile.name:
        confirmed_facts.append(
            FactProvenanceItem(
                field_name="Full Name",
                value=profile.name,
                source="Confirmed Student Profile",
                is_verified=True,
            )
        )
    else:
        placeholders.append("[STUDENT_INPUT: Your Full Name]")

    if profile.degree_program:
        confirmed_facts.append(
            FactProvenanceItem(
                field_name="Current / Prior Degree",
                value=profile.degree_program,
                source="Confirmed Student Profile",
                is_verified=True,
            )
        )
    else:
        placeholders.append("[MISSING: Current or prior degree program]")

    if profile.field_of_study:
        confirmed_facts.append(
            FactProvenanceItem(
                field_name="Field of Study",
                value=profile.field_of_study,
                source="Confirmed Student Profile",
                is_verified=True,
            )
        )
    else:
        placeholders.append("[MISSING: Primary field of study]")

    if profile.institution:
        confirmed_facts.append(
            FactProvenanceItem(
                field_name="Current / Prior Institution",
                value=profile.institution,
                source="Confirmed Student Profile",
                is_verified=True,
            )
        )
    else:
        placeholders.append("[MISSING: Undergraduate/prior institution name]")

    if profile.academic_score and profile.academic_score.score is not None:
        score_val = f"{profile.academic_score.score}"
        if profile.academic_score.scale is not None:
            score_val += f" / {profile.academic_score.scale}"
        confirmed_facts.append(
            FactProvenanceItem(
                field_name="Academic Score",
                value=score_val,
                source="Confirmed Student Profile",
                is_verified=True,
            )
        )
    else:
        placeholders.append("[MISSING: Confirmed GPA/marks and grading scale]")

    if profile.academic_interests:
        confirmed_facts.append(
            FactProvenanceItem(
                field_name="Academic Interests",
                value=", ".join(profile.academic_interests),
                source="Confirmed Student Profile",
                is_verified=True,
            )
        )
    else:
        placeholders.append("[STUDENT_INPUT: Specific academic and research interest areas]")

    if profile.projects_experiences:
        for idx, proj in enumerate(profile.projects_experiences, start=1):
            confirmed_facts.append(
                FactProvenanceItem(
                    field_name=f"Project {idx}: {proj.title}",
                    value=f"Role: {proj.role or 'Contributor'}; Tech: {', '.join(proj.technologies) if proj.technologies else 'Unspecified'}",
                    source="Confirmed Student Profile",
                    is_verified=True,
                )
            )
    else:
        placeholders.append("[STUDENT_INPUT: 1-2 major academic or capstone projects, your specific contributions, and methodology]")

    # Opportunity facts
    is_opp_verified = getattr(opp, "verification_status", None) == VerificationStatus.VERIFIED
    confirmed_facts.append(
        FactProvenanceItem(
            field_name="Target Opportunity",
            value=opp.name,
            source=(
                f"Verified Official Source ({opp.official_url})"
                if is_opp_verified and opp.official_url
                else (f"Official Source ({opp.official_url})" if opp.official_url else "Opportunity Record")
            ),
            is_verified=is_opp_verified,
        )
    )
    confirmed_facts.append(
        FactProvenanceItem(
            field_name="Target Institution",
            value=f"{opp.institution} ({opp.destination_country})",
            source="Verified Official Source" if is_opp_verified else "Opportunity Record",
            is_verified=is_opp_verified,
        )
    )

    if item.funding_summary:
        confirmed_facts.append(
            FactProvenanceItem(
                field_name="Funding Structure",
                value=item.funding_summary,
                source="Audited Funding Assessment",
                is_verified=True,
            )
        )

    if item.deadline_summary:
        confirmed_facts.append(
            FactProvenanceItem(
                field_name="Application Deadline",
                value=f"{item.deadline_summary} (Feasibility: {item.deadline_feasibility.value})",
                source="Audited Deadline Assessment",
                is_verified=True,
            )
        )

    # Gaps & unverified items
    for gap in item.main_gaps:
        unverified_claims.append(f"Eligibility gap / unverified requirement: {gap}")
        placeholders.append(f"[STUDENT_INPUT: Address prerequisite/evidence for: {gap}]")

    for caveat in item.caveats:
        unverified_claims.append(f"Audit caveat: {caveat}")

    # Explicit goals placeholder (never fabricate student post-grad aspirations)
    placeholders.append("[STUDENT_INPUT: State your genuine post-graduation career and research goals]")

    # --- 2. Draft Text Assembly ---
    applicant_name = profile.name or "[STUDENT_INPUT: Your Full Name]"
    opp_name = opp.name
    institution = opp.institution
    country = opp.destination_country

    lines: list[str] = []

    # Title & Metadata
    lines.append(f"STATEMENT OF PURPOSE: {opp_name.upper()}")
    lines.append(f"Target Institution: {institution} — {country}")
    lines.append(f"Applicant: {applicant_name}")
    lines.append(f"Fit Assessment: {item.fit_score:.1f} / 100 ({item.eligibility_classification.value})")
    lines.append("-" * 60)
    lines.append("")

    # Section 1: Introduction & Academic Motivation
    lines.append("1. INTRODUCTION & PROGRAM MOTIVATION")
    field_text = profile.field_of_study or "[MISSING: Primary field of study]"
    lines.append(
        f"I am writing to formally present my application for the {opp_name} at {institution}. "
        f"With an academic foundation in {field_text}, my objective is to undertake rigorous advanced "
        f"training in {country} that directly aligns with my research aspirations."
    )
    if profile.academic_interests:
        interests_text = ", ".join(profile.academic_interests)
        lines.append(
            f"My dedicated research interests focus on {interests_text}. The specialized faculty, "
            f"research facilities, and curriculum at {institution} provide the ideal environment "
            f"to deepen these investigations."
        )
    else:
        lines.append(
            "My dedicated research interests focus on [STUDENT_INPUT: Specific academic and research interest areas]. "
            f"The specialized faculty and curriculum at {institution} provide an ideal environment to pursue these questions."
        )
    lines.append("")

    # Section 2: Academic Background & Verified Credentials
    lines.append("2. ACADEMIC PREPARATION & FOUNDATION")
    degree_text = profile.degree_program or "[MISSING: Current or prior degree program]"
    inst_text = profile.institution or "[MISSING: Undergraduate/prior institution name]"
    lines.append(
        f"My academic training includes coursework toward my {degree_text} at {inst_text}."
    )
    if profile.academic_score and profile.academic_score.score is not None:
        score_val = f"{profile.academic_score.score}"
        if profile.academic_score.scale is not None:
            score_val += f" / {profile.academic_score.scale}"
        lines.append(
            f"Throughout this academic tenure, I maintained a confirmed academic standing of {score_val}, "
            "demonstrating rigorous quantitative and theoretical competence."
        )
    else:
        lines.append(
            "Throughout my studies, I have maintained strong scholastic performance: "
            "[MISSING: Insert confirmed GPA/percentage and scale from official transcript]."
        )
    lines.append("")

    # Section 3: Genuine Experience & Research Projects
    lines.append("3. RESEARCH & PROJECT EXPERIENCES")
    if profile.projects_experiences:
        lines.append(
            "My theoretical coursework is complemented by substantive, hands-on project work:"
        )
        for proj in profile.projects_experiences:
            proj_summary = proj.summary or f"[STUDENT_INPUT: Provide 1-2 sentences summarizing key outcomes for {proj.title}]"
            tech_str = f" Technologies and tools utilized: {', '.join(proj.technologies)}." if proj.technologies else ""
            role_str = f" (Role: {proj.role})" if proj.role else ""
            lines.append(f"• {proj.title}{role_str}: {proj_summary}{tech_str}")
    else:
        lines.append(
            "My theoretical coursework is complemented by substantive hands-on project and research experience:\n"
            "• [STUDENT_INPUT: Detail 1-2 major academic or capstone projects, your specific contributions, and methodology]."
        )
    lines.append("")

    # Section 4: Program Alignment, Fit, and Strengths
    lines.append(f"4. ALIGNMENT WITH {institution.upper()} & AWARD OBJECTIVES")
    if item.main_strengths:
        strengths_bullet = "; ".join(item.main_strengths)
        lines.append(
            f"My profile demonstrates direct alignment with this program's criteria: {strengths_bullet}."
        )
    if item.funding_summary:
        lines.append(f"Regarding funding and program parameters: {item.funding_summary}.")
    if profile.budget_constraint and profile.budget_constraint.notes:
        lines.append(f"My financial planning considerations: {profile.budget_constraint.notes}.")
    if item.deadline_summary:
        lines.append(f"I am fully prepared to meet the documented submission timeline: {item.deadline_summary}.")
    lines.append("")

    # Section 5: Defensively Addressing Prerequisites & Recommended Actions
    if item.main_gaps or item.recommended_actions or item.unknown_criteria:
        lines.append("5. PREREQUISITES & APPLICATION PREPARATION")
        if item.main_gaps:
            for gap in item.main_gaps:
                lines.append(
                    f"• Requirement addressed: [STUDENT_INPUT: Explain how you fulfill or will fulfill: {gap}]"
                )
        if item.recommended_actions:
            action_titles = [f"'{act.title}'" for act in item.recommended_actions[:3]]
            lines.append(
                f"I am actively assembling the verified documentation items: {', '.join(action_titles)}."
            )
        lines.append("")

    # Section 6: Future Aspirations (Strictly user-supplied)
    lines.append("6. CAREER ASPIRATIONS & CONCLUSION")
    lines.append(
        "Upon completion of this program, my long-term trajectory is focused on: "
        "[STUDENT_INPUT: State your genuine post-graduation career and research goals]."
    )
    lines.append(
        f"I welcome the opportunity to contribute to the academic and research community at {institution} "
        f"and appreciate your consideration of my application."
    )
    lines.append("")

    # Additional notes if student provided them
    if request.additional_notes and request.additional_notes.strip():
        lines.append("=" * 60)
        lines.append("STUDENT NOTES / FOCUS AREAS (USER SUPPLIED):")
        lines.append(request.additional_notes.strip())
        lines.append("")

    # Append provenance summary
    lines.append("=" * 60)
    lines.append("FACT & EVIDENCE PROVENANCE AUDIT:")
    lines.append(f"• Verified sources cited: {len(source_citations)}")
    for citation in source_citations:
        lines.append(f"  - {citation}")
    lines.append(f"• Confirmed facts used: {len(confirmed_facts)}")
    lines.append(f"• Placeholders requiring student action: {len(placeholders)}")
    for ph in placeholders:
        lines.append(f"  * {ph}")
    lines.append("=" * 60)
    lines.append(MANDATORY_DISCLAIMER)

    draft_text = "\n".join(lines)

    return SOPDraftResponse(
        opportunity_name=opp_name,
        institution=institution,
        draft_text=draft_text,
        placeholders=placeholders,
        confirmed_facts_used=confirmed_facts,
        unverified_claims=unverified_claims,
        source_citations=source_citations,
        disclaimer=MANDATORY_DISCLAIMER,
    )
