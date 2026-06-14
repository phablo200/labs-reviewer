from types import SimpleNamespace

from labs.agents.labs_reviewer.agent import LabReviewerAgent
from labs.agents.labs_reviewer.helper import (
    extract_markdown_section,
    normalize_list_field,
)
from labs.agents.labs_reviewer.schema import LabReviewerRequest


class _MarkdownLLMStub:
    def invoke(self, _messages):
        return SimpleNamespace(
            content="""## Revised Post
# Better Post

Improved body.

## Errors Found
- Original text was redundant.
- One heading was unclear.

## Improvement Tips
- Keep examples concrete.
- Remove stale endpoint names.

## Next Revision Checklist
- Confirm routes match the code.
- Run pytest.
"""
        )


class _PlainTextLLMStub:
    def invoke(self, _messages):
        return SimpleNamespace(content="# Plain revision\n\nNo sections.")


class _FailingLLMStub:
    def invoke(self, _messages):
        raise RuntimeError("provider failed")


def test_revise_parses_markdown_sections() -> None:
    agent = LabReviewerAgent(llm=_MarkdownLLMStub())

    response = agent.revise(LabReviewerRequest(content="# Draft"))

    assert response.revised_post == "# Better Post\n\nImproved body."
    assert response.errors_found == [
        "Original text was redundant.",
        "One heading was unclear.",
    ]
    assert response.improvement_tips == [
        "Keep examples concrete.",
        "Remove stale endpoint names.",
    ]
    assert response.next_revision_checklist == [
        "Confirm routes match the code.",
        "Run pytest.",
    ]


def test_revise_uses_raw_text_when_sections_are_missing() -> None:
    agent = LabReviewerAgent(llm=_PlainTextLLMStub())

    response = agent.revise(LabReviewerRequest(content="# Draft"))

    assert response.revised_post == "# Plain revision\n\nNo sections."
    assert response.errors_found == []
    assert response.improvement_tips == []
    assert response.next_revision_checklist == []


def test_revise_uses_original_content_when_generation_fails() -> None:
    agent = LabReviewerAgent(llm=_FailingLLMStub())

    response = agent.revise(LabReviewerRequest(content="# Draft"))

    assert response.revised_post == "# Draft"
    assert response.errors_found == []
    assert response.improvement_tips == []
    assert response.next_revision_checklist == []


def test_reviewer_helper_extracts_sections_and_normalizes_lists() -> None:
    raw_text = """## Revised Post
# Title

## Errors Found
* First issue
- Second issue
"""

    assert extract_markdown_section(raw_text, "Revised Post") == "# Title"
    assert normalize_list_field(
        extract_markdown_section(raw_text, "Errors Found")
    ) == ["First issue", "Second issue"]
