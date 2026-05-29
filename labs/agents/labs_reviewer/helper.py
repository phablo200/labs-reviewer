"""Helpers for parsing reviewer Markdown responses."""

import re

from .schema import LabReviewerResponse


def normalize_list_field(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        normalized: list[str] = []
        for line in lines:
            cleaned = re.sub(r"^[-*]\s*", "", line).strip()
            if cleaned:
                normalized.append(cleaned)
        return normalized
    return []


def extract_markdown_section(raw_text: str, heading: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, raw_text, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return ""

    next_heading = re.search(
        r"^##\s+.+$",
        raw_text[match.end() :],
        flags=re.MULTILINE,
    )
    end = match.end() + next_heading.start() if next_heading else len(raw_text)
    return raw_text[match.end() : end].strip()


def parse_markdown_response(
    raw_text: str, fallback_content: str
) -> LabReviewerResponse:
    revised_post = extract_markdown_section(raw_text, "Revised Post")
    errors_found = extract_markdown_section(raw_text, "Errors Found")
    improvement_tips = extract_markdown_section(raw_text, "Improvement Tips")
    next_revision_checklist = extract_markdown_section(
        raw_text, "Next Revision Checklist"
    )

    return LabReviewerResponse(
        revised_post=revised_post or raw_text.strip() or fallback_content,
        errors_found=normalize_list_field(errors_found),
        improvement_tips=normalize_list_field(improvement_tips),
        next_revision_checklist=normalize_list_field(next_revision_checklist),
    )
