from types import SimpleNamespace

import labs.providers.github.github as github_module
from labs.providers.github.github import GitHubProvider


class _ResponseStub:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"ok": true}'


def test_http_get_json_uses_github_token_header(monkeypatch) -> None:
    captured_requests = []

    def _urlopen_stub(request, timeout):
        captured_requests.append((request, timeout))
        return _ResponseStub()

    monkeypatch.setenv("GITHUB_TOKEN", "github-token")
    monkeypatch.setattr(github_module, "urlopen", _urlopen_stub)

    response = GitHubProvider(timeout=12, user_agent="custom-agent")._http_get_json(
        "https://api.github.com/test"
    )

    assert response == {"ok": True}
    request, timeout = captured_requests[0]
    assert timeout == 12
    assert request.get_header("Authorization") == "Bearer github-token"
    assert request.get_header("Accept") == "application/vnd.github+json"
    assert request.get_header("User-agent") == "custom-agent"


def test_http_get_json_omits_authorization_without_github_token(monkeypatch) -> None:
    captured_requests = []

    def _urlopen_stub(request, timeout):
        captured_requests.append((request, timeout))
        return _ResponseStub()

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(github_module, "urlopen", _urlopen_stub)

    GitHubProvider()._http_get_json("https://api.github.com/test")

    request, _timeout = captured_requests[0]
    assert request.get_header("Authorization") is None


def test_extract_repositories_deduplicates_and_strips_git_suffix() -> None:
    provider = GitHubProvider()

    assert provider.extract_repositories(
        "https://github.com/octocat/hello-world.git and "
        "https://github.com/octocat/hello-world"
    ) == ["octocat/hello-world"]


def test_extract_focus_paths_from_supported_heading_variants() -> None:
    text = """
# Focus on Github Folders:
- labs/agents/labs_code_example
- `labs/agents/labs_post_writer/`
- /labs/helpers

## Other Section
- this/should/not/be/read
"""

    assert GitHubProvider().extract_focus_paths(text) == [
        "labs/agents/labs_code_example",
        "labs/agents/labs_post_writer",
        "labs/helpers",
    ]


def test_extract_focus_paths_ignores_unrelated_lists_and_urls() -> None:
    text = """
## Regular Links
- labs/agents/labs_code_example

## Focus GitHub Paths
- https://github.com/phablo200/blog-reviewer
- labs/agents/labs_reviewer
- labs/agents/labs_reviewer
"""

    assert GitHubProvider().extract_focus_paths(text) == [
        "labs/agents/labs_reviewer"
    ]


def test_select_candidate_paths_prioritizes_focus_paths() -> None:
    tree_items = [
        {"type": "blob", "path": "core/config.py"},
        {"type": "blob", "path": "core/llm_config.py"},
        {"type": "blob", "path": "labs/router.py"},
        {"type": "blob", "path": "labs/agents/labs_code_example/agent.py"},
        {"type": "blob", "path": "labs/agents/labs_code_example/schema.py"},
        {"type": "blob", "path": "labs/agents/labs_code_example/prompts.py"},
    ]

    selected = GitHubProvider._select_candidate_paths(
        tree_items, ["labs/agents/labs_code_example"]
    )

    assert selected == [
        "labs/agents/labs_code_example/agent.py",
        "labs/agents/labs_code_example/schema.py",
        "labs/agents/labs_code_example/prompts.py",
    ]


def test_select_candidate_paths_spreads_agent_files_across_focus_folders() -> None:
    tree_items = [
        {"type": "blob", "path": "core/config.py"},
        {"type": "blob", "path": "labs/agents/labs_code_example/agent.py"},
        {"type": "blob", "path": "labs/agents/labs_code_example/schema.py"},
        {"type": "blob", "path": "labs/agents/labs_post_metadata/agent.py"},
        {"type": "blob", "path": "labs/agents/labs_post_metadata/schema.py"},
        {"type": "blob", "path": "labs/agents/labs_post_translator/agent.py"},
        {"type": "blob", "path": "labs/agents/labs_reviewer/agent.py"},
    ]

    selected = GitHubProvider._select_candidate_paths(
        tree_items,
        [
            "labs/agents/labs_code_example",
            "labs/agents/labs_post_metadata",
            "labs/agents/labs_post_translator",
            "labs/agents/labs_reviewer",
        ],
    )

    assert selected == [
        "labs/agents/labs_code_example/agent.py",
        "labs/agents/labs_post_metadata/agent.py",
        "labs/agents/labs_post_translator/agent.py",
    ]


def test_select_candidate_paths_excludes_tests_unless_focused() -> None:
    tree_items = [
        {"type": "blob", "path": "tests/test_service.py"},
        {"type": "blob", "path": "labs/service.py"},
        {"type": "blob", "path": "main.py"},
    ]

    assert GitHubProvider._select_candidate_paths(tree_items, []) == [
        "labs/service.py",
        "main.py",
    ]
    assert GitHubProvider._select_candidate_paths(tree_items, ["tests"]) == [
        "tests/test_service.py",
        "labs/service.py",
        "main.py",
    ]


def test_fetch_repo_context_formats_file_sections_for_extraction(monkeypatch) -> None:
    provider = GitHubProvider(logger=SimpleNamespace(info=lambda *args, **kwargs: None))

    def _http_get_json_stub(url):
        if url == "https://api.github.com/repos/octocat/hello-world":
            return {
                "description": "Demo repo",
                "language": "Python",
                "default_branch": "main",
            }
        if url.endswith("/git/trees/main?recursive=1"):
            return {
                "tree": [
                    {"type": "blob", "path": "labs/agents/demo/agent.py"},
                ]
            }
        if url.endswith("/contents/labs/agents/demo/agent.py"):
            return {
                "content": "Y2xhc3MgRGVtb0FnZW50OgogICAgcGFzcwo=",
            }
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(provider, "_http_get_json", _http_get_json_stub)

    context = provider.fetch_repo_context(
        "octocat/hello-world", ["labs/agents/demo"]
    )

    assert "File: labs/agents/demo/agent.py" in context
    assert "Language: python" in context
    assert "Snippet:\n```" in context
    assert "class DemoAgent:" in context
