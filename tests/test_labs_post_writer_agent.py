from types import SimpleNamespace

import labs.agents.labs_post_writer.agent as writer_module
from labs.agents.labs_post_writer.agent import LabPostWriterAgent
from labs.agents.labs_post_writer.helper import build_code_examples_context
from labs.agents.labs_post_writer.schema import LabPostWriterRequest


class _LLMStub:
    def __init__(self):
        self.human_messages: list[str] = []

    def invoke(self, messages):
        self.human_messages.append(str(messages[1].content))
        return SimpleNamespace(content="# Generated Post\n\nBody")


class _ReviewerStub:
    def revise(self, request):
        return SimpleNamespace(
            revised_post=request.content,
            errors_found=[],
            improvement_tips=[],
            next_revision_checklist=[],
        )


class _CodeExampleAgentStub:
    def extract_examples(self, _request):
        return SimpleNamespace(
            summary="Useful examples for this repo.",
            warnings=[],
            examples=[
                SimpleNamespace(
                    repository="octocat/hello-world",
                    file_path="app/main.py",
                    language="python",
                    snippet="def handler():\n    return 'ok'",
                    why_it_matters="Shows request handling",
                    integration_hint="Use this when explaining service flow",
                )
            ],
        )


def test_organize_notes_includes_code_examples_context(monkeypatch) -> None:
    llm = _LLMStub()

    monkeypatch.setattr(writer_module.LLMConfig, "build_chat_model_for_agent", lambda _role: llm)
    monkeypatch.setattr(
        writer_module,
        "enrich_context_with_repositories",
        lambda context, _logger: context + "\n\nRepo context",
    )

    agent = LabPostWriterAgent()
    agent.blog_reviwer = _ReviewerStub()
    agent.code_example_agent = _CodeExampleAgentStub()

    response = agent.organize_notes(
        LabPostWriterRequest(context="notes https://github.com/octocat/hello-world")
    )

    assert response.reviewed_markdown
    assert llm.human_messages
    first_prompt = llm.human_messages[0]
    assert "## Code Examples Context" in first_prompt
    assert "Repository: octocat/hello-world" in first_prompt
    assert "```" in first_prompt


def test_build_code_examples_context_formats_and_truncates_snippets() -> None:
    long_snippet = "x" * 1300
    examples_response = SimpleNamespace(
        summary="Useful examples.",
        examples=[
            SimpleNamespace(
                repository="octocat/hello-world",
                file_path="app/main.py",
                language="python",
                snippet=long_snippet,
                why_it_matters="Shows request handling",
                integration_hint="Use this when explaining service flow",
            )
        ],
    )

    context = build_code_examples_context(examples_response)

    assert "## Code Examples Context" in context
    assert "- Repository: octocat/hello-world" in context
    assert "- File: app/main.py" in context
    assert "x" * 1200 in context
    assert "\n..." in context


def test_build_code_examples_context_returns_empty_without_examples() -> None:
    examples_response = SimpleNamespace(summary="No examples.", examples=[])

    assert build_code_examples_context(examples_response) == ""
