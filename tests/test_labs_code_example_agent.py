from labs.agents.labs_code_example.agent import LabCodeExampleAgent
from labs.agents.labs_code_example.prompts import LabCodeExamplePrompt
from labs.agents.labs_code_example.schema import LabCodeExampleRequest


class _StructuredLLMStub:
    def __init__(self, response=None, raises: Exception | None = None):
        self.response = response
        self.raises = raises

    def invoke(self, _messages):
        if self.raises:
            raise self.raises
        return self.response


class _LLMStub:
    def __init__(self, response=None, raises: Exception | None = None):
        self.response = response
        self.raises = raises

    def with_structured_output(self, _schema):
        return _StructuredLLMStub(response=self.response, raises=self.raises)


class _GitHubProviderStub:
    def __init__(
        self,
        repositories=None,
        focus_paths=None,
        context="Repository: octocat/hello-world\nFile: app/main.py\ndef main(): pass",
        raises: Exception | None = None,
    ) -> None:
        self.repositories = repositories or []
        self.focus_paths = focus_paths or []
        self.context = context
        self.raises = raises
        self.fetch_calls = []

    def extract_repositories(self, _text):
        return self.repositories

    def extract_focus_paths(self, _text):
        return self.focus_paths

    def fetch_repo_context(self, repository, focus_paths):
        self.fetch_calls.append((repository, focus_paths))
        if self.raises:
            raise self.raises
        return self.context


def test_code_example_prompt_requires_examples_when_file_sections_exist() -> None:
    prompt = LabCodeExamplePrompt.build_system_prompt()

    assert "If any File section contains code, return at least one example." in prompt
    assert "Do not return examples=[] unless no File sections with code are present." in prompt
    assert "Each example.snippet must be copied or tightly excerpted" in prompt
    assert "A summary is not a substitute for examples" in prompt
    assert "Each examples item must include all fields" in prompt


def test_extract_examples_without_repositories_returns_warning() -> None:
    agent = LabCodeExampleAgent(
        llm=_LLMStub(response={}),
        github_provider=_GitHubProviderStub(repositories=[]),
    )

    response = agent.extract_examples(
        LabCodeExampleRequest(notes_context="No links here", repositories=[])
    )

    assert response.examples == []
    assert "repositories" in response.summary.lower()
    assert response.warnings


def test_extract_examples_successful_structured_response() -> None:
    github_provider = _GitHubProviderStub(
        repositories=["octocat/hello-world"],
        focus_paths=["app"],
    )
    agent = LabCodeExampleAgent(
        github_provider=github_provider,
        llm=_LLMStub(
            response={
                "examples": [
                    {
                        "repository": "octocat/hello-world",
                        "file_path": "app/main.py",
                        "language": "python",
                        "snippet": "def main():\n    return 'ok'",
                        "why_it_matters": "Shows main app flow",
                        "integration_hint": "Use it in architecture section",
                    }
                ],
                "summary": "One strong example found.",
                "warnings": [],
            }
        ),
    )

    response = agent.extract_examples(
        LabCodeExampleRequest(
            notes_context=(
                "https://github.com/octocat/hello-world\n"
                "# Focus on Github Folders:\n"
                "- app"
            ),
            repositories=[],
        )
    )

    assert len(response.examples) == 1
    assert response.examples[0].repository == "octocat/hello-world"
    assert response.summary == "One strong example found."
    assert github_provider.fetch_calls == [("octocat/hello-world", ["app"])]


def test_extract_examples_recovers_partial_structured_items() -> None:
    agent = LabCodeExampleAgent(
        github_provider=_GitHubProviderStub(
            repositories=["octocat/hello-world"],
            context=(
                "Repository: octocat/hello-world\n"
                "File: labs/agents/labs_code_example/agent.py\n"
                "class LabCodeExampleAgent:\n"
                "    pass"
            ),
        ),
        llm=_LLMStub(
            response={
                "examples": [
                    {
                        "snippet": "class LabCodeExampleAgent:\n    pass",
                        "integration_hint": "Use it in the architecture section.",
                    }
                ],
                "summary": "Partial item returned by model.",
                "warnings": [],
            }
        ),
    )

    response = agent.extract_examples(
        LabCodeExampleRequest(
            notes_context="https://github.com/octocat/hello-world", repositories=[]
        )
    )

    assert len(response.examples) == 1
    assert response.examples[0].repository == "octocat/hello-world"
    assert response.examples[0].file_path == "labs/agents/labs_code_example/agent.py"
    assert response.examples[0].language == "python"
    assert response.examples[0].why_it_matters


def test_extract_examples_structured_generation_failure_returns_fallback() -> None:
    agent = LabCodeExampleAgent(
        github_provider=_GitHubProviderStub(repositories=["octocat/hello-world"]),
        llm=_LLMStub(raises=RuntimeError("llm failed")),
    )

    response = agent.extract_examples(
        LabCodeExampleRequest(
            notes_context="https://github.com/octocat/hello-world", repositories=[]
        )
    )

    assert response.examples == []
    assert "Failed to generate" in response.summary
    assert any("Structured generation failed" in warning for warning in response.warnings)


def test_extract_examples_fetch_error_returns_warning() -> None:
    agent = LabCodeExampleAgent(
        github_provider=_GitHubProviderStub(
            repositories=["octocat/hello-world"],
            raises=RuntimeError("fetch failed"),
        ),
        llm=_LLMStub(response={}),
    )

    response = agent.extract_examples(
        LabCodeExampleRequest(
            notes_context="https://github.com/octocat/hello-world", repositories=[]
        )
    )

    assert response.examples == []
    assert response.summary == "Repository context could not be fetched."
    assert response.warnings == ["Unexpected fetch error for octocat/hello-world."]
