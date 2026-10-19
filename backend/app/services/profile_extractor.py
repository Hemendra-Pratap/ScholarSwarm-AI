import re
from app.schemas.ingestion import (
    DocumentType,
    IngestionStatus,
    FieldProvenance,
    ConflictingField,
    IngestionResponse,
)
from app.schemas.student_profile import (
    StudentProfileBase,
    AcademicScore,
    ProjectExperience,
)
from app.services.document_parser import DocumentExtractionResult


ALL_PROFILE_FIELDS = [
    "name",
    "degree_program",
    "field_of_study",
    "institution",
    "country",
    "academic_stage",
    "academic_score",
    "target_destinations",
    "academic_interests",
    "projects_experiences",
    "budget_constraint",
    "public_profile_urls",
]


class ProfileExtractor:
    """Conservative, deterministic extractor for student profile fields from document text."""

    @classmethod
    def extract(cls, extraction_result: DocumentExtractionResult, document_type: DocumentType) -> IngestionResponse:
        provenance: dict[str, FieldProvenance] = {}
        conflicts: list[ConflictingField] = []
        warnings: list[str] = []

        # Candidate fields
        name: str | None = None
        degree_program: str | None = None
        field_of_study: str | None = None
        institution: str | None = None
        country: str | None = None
        academic_stage: str | None = None
        academic_score: AcademicScore | None = None
        projects_experiences: list[ProjectExperience] = []
        public_profile_urls: list = []

        segments = extraction_result.segments

        # 1. Name extraction (typically first prominent header in a resume/transcript)
        for seg in segments[:3]:
            # Look for lines with Name: <val> or a clean header line with 2-4 words
            lines = [l.strip() for l in seg.text.split("\n") if l.strip()]
            for line in lines:
                name_match = re.match(r"^(?:Name|Student\s*Name|Candidate\s*Name)[:\-]?\s*([A-Za-z\s\.\-]{3,50})$", line, re.I)
                if name_match:
                    cand_name = name_match.group(1).strip()
                    if name is None:
                        name = cand_name
                        provenance["name"] = FieldProvenance(
                            field_name="name",
                            extracted_value=cand_name,
                            source_document_type=document_type,
                            source_location=seg.location,
                            excerpt=line,
                        )
                    elif name.lower() != cand_name.lower():
                        conflicts.append(ConflictingField(
                            field_name="name",
                            conflicting_values=[name, cand_name],
                            reason="Multiple conflicting candidate names observed.",
                        ))
                    break
                # If first line looks like a person's name (e.g. "Sarah Chen" or "Elena Rostova")
                if not name and re.match(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}$", line) and len(line) < 40:
                    if not any(keyword in line.lower() for keyword in ["curriculum", "resume", "transcript", "university", "education"]):
                        name = line
                        provenance["name"] = FieldProvenance(
                            field_name="name",
                            extracted_value=line,
                            source_document_type=document_type,
                            source_location=seg.location,
                            excerpt=line,
                        )
                        break
            if name:
                break

        # 2. Institution extraction
        institution_patterns = [
            r"^(?:University|Institute|College|Institution)[:\-]?\s*([A-Za-z0-9\s,\.\-&]{4,100})$",
            r"([A-Za-z0-9\s,\.\-&]*(?:University|Institute of Technology|College of Engineering)[A-Za-z0-9\s,\.\-&]*)",
        ]
        found_institutions: list[tuple[str, str, str]] = []
        for seg in segments:
            for line in seg.text.split("\n"):
                line_s = line.strip()
                for pat in institution_patterns:
                    m = re.search(pat, line_s, re.I)
                    if m:
                        inst_cand = m.group(1).strip()
                        # Avoid matching sentences or long sections
                        if 5 <= len(inst_cand) <= 80 and not any(k in inst_cand.lower() for k in ["admissions", "degree in", "department of"]):
                            if not any(inst_cand.lower() == existing[0].lower() for existing in found_institutions):
                                found_institutions.append((inst_cand, seg.location, line_s))
                        break

        if len(found_institutions) == 1:
            institution = found_institutions[0][0]
            provenance["institution"] = FieldProvenance(
                field_name="institution",
                extracted_value=institution,
                source_document_type=document_type,
                source_location=found_institutions[0][1],
                excerpt=found_institutions[0][2],
            )
        elif len(found_institutions) > 1:
            # Check if one is a primary institution or conflict
            first_inst = found_institutions[0][0]
            other_insts = [inst[0] for inst in found_institutions[1:]]
            conflicts.append(ConflictingField(
                field_name="institution",
                conflicting_values=[first_inst] + other_insts,
                reason="Multiple institutions mentioned in document; human confirmation needed.",
            ))
            # Set to first for candidate preview, but flagged in conflicts
            institution = first_inst
            provenance["institution"] = FieldProvenance(
                field_name="institution",
                extracted_value=institution,
                source_document_type=document_type,
                source_location=found_institutions[0][1],
                excerpt=found_institutions[0][2],
            )

        # 3. Degree / Program & Field of Study
        degree_patterns = [
            r"\b(B\.?Tech|Bachelor of Technology|B\.?S(?:c)?\.?|Bachelor of Science|B\.?E\.?|Bachelor of Engineering|M\.?Tech|M\.?S(?:c)?\.?|Master of Science|Master of Technology)\b(?:\s+(?:in|of)\s+([A-Za-z\s&,\-]{3,60}))?",
            r"\b(Degree|Program)[:\-]?\s*([A-Za-z\s&,\.\-]{3,60})\b",
        ]
        for seg in segments:
            for line in seg.text.split("\n"):
                line_s = line.strip()
                m = re.search(degree_patterns[0], line_s, re.I)
                if m:
                    deg_cand = m.group(1).strip()
                    if not degree_program:
                        degree_program = deg_cand
                        provenance["degree_program"] = FieldProvenance(
                            field_name="degree_program",
                            extracted_value=deg_cand,
                            source_document_type=document_type,
                            source_location=seg.location,
                            excerpt=line_s,
                        )
                    if m.group(2) and not field_of_study:
                        field_cand = m.group(2).strip()
                        # Clean trailing commas or dates
                        field_cand = re.sub(r"[\s,\.\-]+$", "", field_cand)
                        if len(field_cand) >= 2:
                            field_of_study = field_cand
                            provenance["field_of_study"] = FieldProvenance(
                                field_name="field_of_study",
                                extracted_value=field_cand,
                                source_document_type=document_type,
                                source_location=seg.location,
                                excerpt=line_s,
                            )
                    break
            if degree_program and field_of_study:
                break

        # Check explicit Field of Study if not captured
        if not field_of_study:
            for seg in segments:
                for line in seg.text.split("\n"):
                    m = re.search(r"(?:Field of Study|Major|Specialization)[:\-]?\s*([A-Za-z\s&,\.\-]{3,60})", line, re.I)
                    if m:
                        field_of_study = m.group(1).strip()
                        provenance["field_of_study"] = FieldProvenance(
                            field_name="field_of_study",
                            extracted_value=field_of_study,
                            source_document_type=document_type,
                            source_location=seg.location,
                            excerpt=line.strip(),
                        )
                        break
                if field_of_study:
                    break

        # 4. Academic Score (CGPA / GPA / Percentage)
        # Never invent a score scale if not present!
        score_patterns = [
            # CGPA: 8.5 / 10.0 or GPA: 3.8/4.0
            r"\b(?:CGPA|GPA|Academic Score)[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:/|\s+out\s+of\s+)\s*([0-9]+(?:\.[0-9]+)?)\b",
            # CGPA: 8.5 (without explicit scale)
            r"\b(?:CGPA|GPA|Grade Point Average)[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\b",
            # Percentage: 85%
            r"\b(?:Percentage|Aggregate)[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*%",
        ]
        found_scores: list[tuple[AcademicScore, str, str]] = []
        for seg in segments:
            for line in seg.text.split("\n"):
                line_s = line.strip()
                # Pattern 1: score with scale
                m1 = re.search(score_patterns[0], line_s, re.I)
                if m1:
                    try:
                        sc = float(m1.group(1))
                        scale = float(m1.group(2))
                        found_scores.append((AcademicScore(score=sc, scale=scale), seg.location, line_s))
                        continue
                    except ValueError:
                        pass
                # Pattern 2: score without scale
                m2 = re.search(score_patterns[1], line_s, re.I)
                if m2:
                    try:
                        sc = float(m2.group(1))
                        # Do NOT invent scale! scale=None
                        found_scores.append((AcademicScore(score=sc, scale=None), seg.location, line_s))
                        continue
                    except ValueError:
                        pass

        if len(found_scores) == 1:
            academic_score = found_scores[0][0]
            val_str = f"{academic_score.score}" + (f"/{academic_score.scale}" if academic_score.scale else "")
            provenance["academic_score"] = FieldProvenance(
                field_name="academic_score",
                extracted_value=val_str,
                source_document_type=document_type,
                source_location=found_scores[0][1],
                excerpt=found_scores[0][2],
            )
        elif len(found_scores) > 1:
            first_score = found_scores[0][0]
            other_scores = [f"{s[0].score}" for s in found_scores[1:]]
            conflicts.append(ConflictingField(
                field_name="academic_score",
                conflicting_values=[f"{first_score.score}"] + other_scores,
                reason="Multiple academic score candidates observed; human confirmation required.",
            ))
            academic_score = first_score
            val_str = f"{academic_score.score}" + (f"/{academic_score.scale}" if academic_score.scale else "")
            provenance["academic_score"] = FieldProvenance(
                field_name="academic_score",
                extracted_value=val_str,
                source_document_type=document_type,
                source_location=found_scores[0][1],
                excerpt=found_scores[0][2],
            )

        # 5. Projects and Relevant Experience (for resume or transcript)
        # Look for sections like Projects or Experience
        for seg in segments:
            lines = seg.text.split("\n")
            in_projects = False
            for line in lines:
                line_s = line.strip()
                if re.match(r"^(?:Academic\s+)?Projects(?:\s*&|\s+and)?(?:\s+Experience)?[:\-]?$", line_s, re.I):
                    in_projects = True
                    continue
                if in_projects and re.match(r"^[A-Z][A-Za-z\s]{2,20}:?$", line_s) and any(k in line_s.lower() for k in ["skills", "education", "awards", "interests"]):
                    in_projects = False
                    continue
                if in_projects:
                    # Look for bullet points or titled project items: e.g. "Project Name: summary" or "- Title: summary"
                    proj_match = re.match(r"^[\*\-•]?\s*([A-Za-z0-9\s,\.\-]{3,50})[:\-]\s*(.+)$", line_s)
                    if proj_match:
                        p_title = proj_match.group(1).strip()
                        p_summary = proj_match.group(2).strip()
                        if len(projects_experiences) < 5:
                            projects_experiences.append(ProjectExperience(
                                title=p_title,
                                summary=p_summary,
                            ))

        if projects_experiences:
            provenance["projects_experiences"] = FieldProvenance(
                field_name="projects_experiences",
                extracted_value=f"{len(projects_experiences)} project(s) extracted",
                source_document_type=document_type,
                source_location=segments[0].location if segments else "Document",
                excerpt="; ".join(p.title for p in projects_experiences),
            )

        # 6. Public Profile URLs (e.g. GitHub / LinkedIn mentioned in text)
        for seg in segments:
            for word in seg.text.split():
                clean_url = word.strip("(),;\"'")
                if re.match(r"^https?://(?:www\.)?(?:github\.com|linkedin\.com)/[A-Za-z0-9_\-\./]+$", clean_url):
                    if clean_url not in public_profile_urls and len(public_profile_urls) < 5:
                        public_profile_urls.append(clean_url)

        if public_profile_urls:
            provenance["public_profile_urls"] = FieldProvenance(
                field_name="public_profile_urls",
                extracted_value=", ".join(public_profile_urls),
                source_document_type=document_type,
                source_location=segments[0].location if segments else "Document",
                excerpt=", ".join(public_profile_urls),
            )

        # Build Candidate Profile
        candidate_profile = StudentProfileBase(
            name=name,
            degree_program=degree_program,
            field_of_study=field_of_study,
            institution=institution,
            country=country,
            academic_stage=academic_stage,
            academic_score=academic_score,
            target_destinations=[],
            academic_interests=[],
            projects_experiences=projects_experiences,
            budget_constraint=None,
            public_profile_urls=public_profile_urls,
        )

        # Determine missing fields
        missing_fields = []
        for f in ALL_PROFILE_FIELDS:
            val = getattr(candidate_profile, f)
            if val is None or val == [] or val == {}:
                missing_fields.append(f)

        # Determine status
        populated_count = len(ALL_PROFILE_FIELDS) - len(missing_fields)
        if populated_count == 0:
            status = IngestionStatus.UNREADABLE
            warnings.append("No recognizable student profile fields could be extracted from document text.")
        elif len(conflicts) > 0 or len(missing_fields) > 4:
            status = IngestionStatus.PARTIAL
        else:
            status = IngestionStatus.SUCCESS

        return IngestionResponse(
            status=status,
            document_type=document_type,
            candidate_profile=candidate_profile,
            provenance=provenance,
            missing_fields=missing_fields,
            conflicts=conflicts,
            warnings=warnings,
            requires_human_review=True,
        )
