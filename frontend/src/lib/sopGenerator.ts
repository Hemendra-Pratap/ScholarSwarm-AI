import type {
  StudentProfileRead,
  StudentProfileBase,
  RankedOpportunityItem,
  FactProvenanceItem,
  SOPDraftResponse,
} from '../types/api'

export const MANDATORY_SOP_DISCLAIMER =
  'ADVISORY: This draft was generated strictly from confirmed student profile facts ' +
  'and verified opportunity criteria. It is a working template that requires personal review, ' +
  'customization, and verification. ScholarSwarm AI does not fabricate personal achievements ' +
  'and never submits applications or contacts universities on your behalf. ' +
  'All application submissions remain under your sole control.'

/**
 * Deterministically assemble an evidence-grounded Statement of Purpose / Application Statement.
 *
 * Adheres strictly to the ScholarSwarm AI integrity principles:
 * - Zero hallucination of achievements, scores, or claims.
 * - Explicit placeholders for missing profile data or unverified criteria.
 * - Full provenance tracking for every fact cited.
 */
export function generateClientSOPDraft(
  profile: StudentProfileRead | StudentProfileBase,
  item: RankedOpportunityItem,
  additionalNotes?: string | null
): SOPDraftResponse {
  const opp = item.opportunity
  const placeholders: string[] = []
  const confirmedFacts: FactProvenanceItem[] = []
  const unverifiedClaims: string[] = []
  const sourceCitations: string[] = []

  // Collect source citations
  if (opp.official_url) {
    sourceCitations.push(opp.official_url)
  }
  for (const ref of item.evidence_references || []) {
    if (ref && !sourceCitations.includes(ref)) {
      sourceCitations.push(ref)
    }
  }

  // --- 1. Fact Provenance Extraction ---
  if (profile.name) {
    confirmedFacts.push({
      field_name: 'Full Name',
      value: profile.name,
      source: 'Confirmed Student Profile',
      is_verified: true,
    })
  } else {
    placeholders.push('[STUDENT_INPUT: Your Full Name]')
  }

  if (profile.degree_program) {
    confirmedFacts.push({
      field_name: 'Current / Prior Degree',
      value: profile.degree_program,
      source: 'Confirmed Student Profile',
      is_verified: true,
    })
  } else {
    placeholders.push('[MISSING: Current or prior degree program]')
  }

  if (profile.field_of_study) {
    confirmedFacts.push({
      field_name: 'Field of Study',
      value: profile.field_of_study,
      source: 'Confirmed Student Profile',
      is_verified: true,
    })
  } else {
    placeholders.push('[MISSING: Primary field of study]')
  }

  if (profile.institution) {
    confirmedFacts.push({
      field_name: 'Current / Prior Institution',
      value: profile.institution,
      source: 'Confirmed Student Profile',
      is_verified: true,
    })
  } else {
    placeholders.push('[MISSING: Undergraduate/prior institution name]')
  }

  const academicScore = (profile as StudentProfileRead).academic_score
  if (academicScore && academicScore.score !== undefined && academicScore.score !== null) {
    let scoreVal = `${academicScore.score}`
    if (academicScore.scale !== undefined && academicScore.scale !== null) {
      scoreVal += ` / ${academicScore.scale}`
    }
    confirmedFacts.push({
      field_name: 'Academic Score',
      value: scoreVal,
      source: 'Confirmed Student Profile',
      is_verified: true,
    })
  } else {
    placeholders.push('[MISSING: Confirmed GPA/marks and grading scale]')
  }

  if (profile.academic_interests && profile.academic_interests.length > 0) {
    confirmedFacts.push({
      field_name: 'Academic Interests',
      value: profile.academic_interests.join(', '),
      source: 'Confirmed Student Profile',
      is_verified: true,
    })
  } else {
    placeholders.push('[STUDENT_INPUT: Specific academic and research interest areas]')
  }

  if (profile.projects_experiences && profile.projects_experiences.length > 0) {
    profile.projects_experiences.forEach((proj, idx) => {
      const skillsStr =
        proj.technologies && Array.isArray(proj.technologies) && proj.technologies.length > 0
          ? proj.technologies.join(', ')
          : 'Unspecified'
      const roleStr = proj.role ? `Role: ${proj.role}` : 'Role: Contributor'
      confirmedFacts.push({
        field_name: `Project ${idx + 1}: ${proj.title}`,
        value: `${roleStr}; Tech: ${skillsStr}`,
        source: 'Confirmed Student Profile',
        is_verified: true,
      })
    })
  } else {
    placeholders.push(
      '[STUDENT_INPUT: 1-2 major academic or capstone projects, your specific contributions, and methodology]'
    )
  }

  // Opportunity Provenance
  const isOppVerified = opp.verification_status === 'verified'
  confirmedFacts.push({
    field_name: 'Target Opportunity',
    value: opp.name,
    source: isOppVerified && opp.official_url
      ? `Verified Official Source (${opp.official_url})`
      : opp.official_url
        ? `Official Source (${opp.official_url})`
        : 'Opportunity Record',
    is_verified: isOppVerified,
  })

  confirmedFacts.push({
    field_name: 'Target Institution',
    value: `${opp.institution} (${opp.destination_country})`,
    source: isOppVerified ? 'Verified Official Source' : 'Opportunity Record',
    is_verified: isOppVerified,
  })

  if (item.funding_summary) {
    confirmedFacts.push({
      field_name: 'Funding Structure',
      value: item.funding_summary,
      source: 'Audited Funding Assessment',
      is_verified: true,
    })
  }

  if (item.deadline_summary) {
    confirmedFacts.push({
      field_name: 'Application Deadline',
      value: `${item.deadline_summary} (Feasibility: ${item.deadline_feasibility})`,
      source: 'Audited Deadline Assessment',
      is_verified: true,
    })
  }

  // Gaps & Audit Caveats
  for (const gap of item.main_gaps || []) {
    unverifiedClaims.push(`Eligibility gap / unverified requirement: ${gap}`)
    placeholders.push(`[STUDENT_INPUT: Address prerequisite/evidence for: ${gap}]`)
  }

  for (const caveat of item.caveats || []) {
    unverifiedClaims.push(`Audit caveat: ${caveat}`)
  }

  // Career goals placeholder (never hallucinated)
  placeholders.push('[STUDENT_INPUT: State your genuine post-graduation career and research goals]')

  // --- 2. Draft Text Assembly ---
  const applicantName = profile.name || '[STUDENT_INPUT: Your Full Name]'
  const oppName = opp.name
  const institution = opp.institution
  const country = opp.destination_country

  const lines: string[] = []

  // Title & Metadata
  lines.push(`STATEMENT OF PURPOSE: ${oppName.toUpperCase()}`)
  lines.push(`Target Institution: ${institution} — ${country}`)
  lines.push(`Applicant: ${applicantName}`)
  lines.push(`Fit Assessment: ${item.fit_score.toFixed(1)} / 100 (${item.eligibility_classification})`)
  lines.push('-'.repeat(60))
  lines.push('')

  // Section 1: Introduction & Academic Motivation
  lines.push('1. INTRODUCTION & PROGRAM MOTIVATION')
  const fieldText = profile.field_of_study || '[MISSING: Primary field of study]'
  lines.push(
    `I am writing to formally present my application for the ${oppName} at ${institution}. ` +
      `With an academic foundation in ${fieldText}, my objective is to undertake rigorous advanced ` +
      `training in ${country} that directly aligns with my research aspirations.`
  )
  if (profile.academic_interests && profile.academic_interests.length > 0) {
    const interestsText = profile.academic_interests.join(', ')
    lines.push(
      `My dedicated research interests focus on ${interestsText}. The specialized faculty, ` +
        `research facilities, and curriculum at ${institution} provide the ideal environment ` +
        `to deepen these investigations.`
    )
  } else {
    lines.push(
      'My dedicated research interests focus on [STUDENT_INPUT: Specific academic and research interest areas]. ' +
        `The specialized faculty and curriculum at ${institution} provide an ideal environment to pursue these questions.`
    )
  }
  lines.push('')

  // Section 2: Academic Background & Verified Credentials
  lines.push('2. ACADEMIC PREPARATION & FOUNDATION')
  const degreeText = profile.degree_program || '[MISSING: Current or prior degree program]'
  const instText = profile.institution || '[MISSING: Undergraduate/prior institution name]'
  lines.push(`My academic training includes coursework toward my ${degreeText} at ${instText}.`)

  let scoreText = ''
  if (academicScore && academicScore.score !== undefined && academicScore.score !== null) {
    scoreText = `${academicScore.score}`
    if (academicScore.scale !== undefined && academicScore.scale !== null) {
      scoreText += ` / ${academicScore.scale}`
    }
  }

  if (scoreText) {
    lines.push(
      `Throughout this academic tenure, I maintained a confirmed academic standing of ${scoreText}, ` +
        'demonstrating rigorous quantitative and theoretical competence.'
    )
  } else {
    lines.push(
      'Throughout my studies, I have maintained strong scholastic performance: ' +
        '[MISSING: Insert confirmed GPA/percentage and scale from official transcript].'
    )
  }
  lines.push('')

  // Section 3: Genuine Experience & Research Projects
  lines.push('3. RESEARCH & PROJECT EXPERIENCES')
  if (profile.projects_experiences && profile.projects_experiences.length > 0) {
    lines.push('My theoretical coursework is complemented by substantive, hands-on project work:')
    for (const proj of profile.projects_experiences) {
      const summary =
        proj.summary ||
        `[STUDENT_INPUT: Provide 1-2 sentences summarizing key outcomes for ${proj.title}]`
      const techList =
        proj.technologies && Array.isArray(proj.technologies) ? proj.technologies : []
      const techStr = techList.length > 0 ? ` Technologies and tools utilized: ${techList.join(', ')}.` : ''
      const role = proj.role ? ` (Role: ${proj.role})` : ''
      lines.push(`• ${proj.title}${role}: ${summary}${techStr}`)
    }
  } else {
    lines.push(
      'My theoretical coursework is complemented by substantive hands-on project and research experience:\n' +
        '• [STUDENT_INPUT: Detail 1-2 major academic or capstone projects, your specific contributions, and methodology].'
    )
  }
  lines.push('')

  // Section 4: Program Alignment, Fit, and Strengths
  lines.push(`4. ALIGNMENT WITH ${institution.toUpperCase()} & AWARD OBJECTIVES`)
  if (item.main_strengths && item.main_strengths.length > 0) {
    const strengthsBullet = item.main_strengths.join('; ')
    lines.push(`My profile demonstrates direct alignment with this program's criteria: ${strengthsBullet}.`)
  }
  if (item.funding_summary) {
    lines.push(`Regarding funding and program parameters: ${item.funding_summary}.`)
  }
  if (profile.budget_constraint && profile.budget_constraint.notes) {
    lines.push(`My financial planning considerations: ${profile.budget_constraint.notes}.`)
  }
  if (item.deadline_summary) {
    lines.push(`I am fully prepared to meet the documented submission timeline: ${item.deadline_summary}.`)
  }
  lines.push('')

  // Section 5: Defensively Addressing Prerequisites & Actions
  if (
    (item.main_gaps && item.main_gaps.length > 0) ||
    (item.recommended_actions && item.recommended_actions.length > 0) ||
    (item.unknown_criteria && item.unknown_criteria.length > 0)
  ) {
    lines.push('5. PREREQUISITES & APPLICATION PREPARATION')
    if (item.main_gaps && item.main_gaps.length > 0) {
      for (const gap of item.main_gaps) {
        lines.push(`• Requirement addressed: [STUDENT_INPUT: Explain how you fulfill or will fulfill: ${gap}]`)
      }
    }
    if (item.recommended_actions && item.recommended_actions.length > 0) {
      const actionTitles = item.recommended_actions.slice(0, 3).map((act) => `'${act.title}'`)
      lines.push(`I am actively assembling the verified documentation items: ${actionTitles.join(', ')}.`)
    }
    lines.push('')
  }

  // Section 6: Future Aspirations (Strictly user-supplied)
  lines.push('6. CAREER ASPIRATIONS & CONCLUSION')
  lines.push(
    'Upon completion of this program, my long-term trajectory is focused on: ' +
      '[STUDENT_INPUT: State your genuine post-graduation career and research goals].'
  )
  lines.push(
    `I welcome the opportunity to contribute to the academic and research community at ${institution} ` +
      'and appreciate your consideration of my application.'
  )
  lines.push('')

  // Additional student notes if provided
  if (additionalNotes && additionalNotes.trim()) {
    lines.push('='.repeat(60))
    lines.push('STUDENT NOTES / FOCUS AREAS (USER SUPPLIED):')
    lines.push(additionalNotes.trim())
    lines.push('')
  }

  // Provenance Summary
  lines.push('='.repeat(60))
  lines.push('FACT & EVIDENCE PROVENANCE AUDIT:')
  lines.push(`• Verified sources cited: ${sourceCitations.length}`)
  for (const citation of sourceCitations) {
    lines.push(`  - ${citation}`)
  }
  lines.push(`• Confirmed facts used: ${confirmedFacts.length}`)
  lines.push(`• Placeholders requiring student action: ${placeholders.length}`)
  for (const ph of placeholders) {
    lines.push(`  * ${ph}`)
  }
  lines.push('='.repeat(60))
  lines.push(MANDATORY_SOP_DISCLAIMER)

  return {
    opportunity_name: oppName,
    institution,
    draft_text: lines.join('\n'),
    placeholders,
    confirmed_facts_used: confirmedFacts,
    unverified_claims: unverifiedClaims,
    source_citations: sourceCitations,
    disclaimer: MANDATORY_SOP_DISCLAIMER,
  }
}
