# GitHub Provider Extraction Plan

## Objective
- Move GitHub repository parsing, API access, file selection, and repository context formatting out of `LabCodeExampleAgent` and into the new `labs/providers/github/` package.
- Keep code-example extraction behavior unchanged while making GitHub integration reusable and easier to test.

## Source Spec
- `docs/specs/github-provider-extraction.md`

## Confirmed Decisions
- Use the new package layout:
  - `labs/providers/github/constants.py`
  - `labs/providers/github/github.py`
- Move GitHub constants into `labs/providers/github/constants.py`.
- Expose provider-level public methods such as `extract_repositories(...)`, `extract_focus_paths(...)`, and `fetch_repo_context(...)`.
- Keep lower-level helpers private unless tests need direct validation through public behavior.
- Add constructor arguments for provider timeout and user-agent, with defaults matching current behavior.
- Do not keep duplicate static GitHub wrappers on `LabCodeExampleAgent` unless needed as a temporary compatibility bridge.

## Implementation Steps
1. Define GitHub provider constants
   - Move `GITHUB_REPO_URL_PATTERN` from `labs/agents/labs_post_writer/constants.py` to `labs/providers/github/constants.py`.
   - Add provider defaults:
     - `DEFAULT_GITHUB_API_TIMEOUT = 10`
     - `DEFAULT_GITHUB_USER_AGENT = "labs-code-example-agent"`
   - Update any existing imports that still need `GITHUB_REPO_URL_PATTERN`.

2. Implement `GitHubProvider`
   - Add `GitHubProvider` in `labs/providers/github/github.py`.
   - Constructor signature should accept:
     - `timeout: int = DEFAULT_GITHUB_API_TIMEOUT`
     - `user_agent: str = DEFAULT_GITHUB_USER_AGENT`
   - Move GitHub-specific logic from `labs/agents/labs_code_example/agent.py`:
     - repository extraction
     - HTTP JSON GET with optional `GITHUB_TOKEN`
     - base64 file content decoding
     - source-file detection
     - focus-heading detection
     - focus-path parsing and normalization
     - test-path detection
     - focus path matching
     - candidate path selection
     - repository context fetching and formatting
     - language detection for context snippets

3. Keep the provider API narrow
   - Public methods:
     - `extract_repositories(text: str) -> list[str]`
     - `extract_focus_paths(text: str) -> list[str]`
     - `fetch_repo_context(repository: str, focus_paths: list[str] | None = None) -> str`
   - Private helpers:
     - `_http_get_json(...)`
     - `_decode_repo_file_content(...)`
     - `_select_candidate_paths(...)`
     - `_language_from_file_path(...)`
     - other parsing and filtering helpers
   - Preserve current context output formatting exactly.

4. Inject provider into `LabCodeExampleAgent`
   - Update `LabCodeExampleAgent.__init__(...)` to accept `github_provider: GitHubProvider | None = None`.
   - Default to `GitHubProvider()` when no provider is supplied.
   - Replace direct helper calls in `extract_examples(...)`:
     - `self.github_provider.extract_repositories(request.notes_context)`
     - `self.github_provider.extract_focus_paths(request.notes_context)`
     - `self.github_provider.fetch_repo_context(repository, focus_paths)`
   - Keep fetch exception handling in the agent so existing warning strings remain unchanged.

5. Clean up `LabCodeExampleAgent`
   - Remove GitHub-specific helper methods from `labs/agents/labs_code_example/agent.py`.
   - Remove unused imports:
     - `base64`
     - `json`
     - `os`
     - `re`
     - `Request`
     - `urlopen`
     - `GITHUB_REPO_URL_PATTERN`
   - Keep agent-owned methods for prompt formatting and response normalization.

6. Update provider tests
   - Create `tests/test_github_provider.py`.
   - Move GitHub helper assertions out of `tests/test_labs_code_example_agent.py`.
   - Cover:
     - token header behavior
     - missing token behavior
     - repository extraction and `.git` stripping
     - focus path parsing
     - focused candidate selection
     - generic candidate fallback
     - test file exclusion unless focused
     - repository context formatting with mocked GitHub responses

7. Update agent tests
   - Replace monkeypatches of agent private GitHub methods with a fake provider object.
   - Keep agent tests focused on:
     - no repositories warning
     - successful structured response
     - partial structured item normalization
     - fetch error warnings
     - structured output failure behavior
   - Keep prompt-related tests unchanged.

8. Validate and adjust imports
   - Run targeted provider and agent tests.
   - Run existing writer/service tests that depend on code-example extraction.
   - Run compile validation for `main.py`, `labs`, and `core`.

## Validation Commands
```bash
venv/bin/python -m pytest -q tests/test_github_provider.py
venv/bin/python -m pytest -q tests/test_labs_code_example_agent.py
venv/bin/python -m pytest -q tests/test_labs_post_writer_agent.py tests/test_service.py
python -m compileall main.py labs core
```

## Manual Check
1. Use notes containing a GitHub URL and focus paths:

```md
https://github.com/phablo200/blog-reviewer

# Focus on Github Folders:
- labs/agents/labs_code_example
- labs/agents/labs_post_metadata
```

2. Confirm `LabCodeExampleAgent` receives repository context with the same `Repository`, `File`, `Language`, and fenced `Snippet` sections as before.
3. Confirm final generated examples still include repository, file path, language, snippet, why-it-matters, and integration hint fields.
4. Confirm failures in GitHub fetching still produce warnings without breaking lab generation.

## Acceptance Checklist
- [ ] `labs/providers/github/constants.py` owns GitHub URL and provider default constants.
- [ ] `labs/providers/github/github.py` contains `GitHubProvider`.
- [ ] `GitHubProvider` accepts configurable timeout and user-agent constructor arguments.
- [ ] `LabCodeExampleAgent` uses injected provider methods for repository extraction, focus path extraction, and context fetching.
- [ ] `LabCodeExampleAgent` no longer contains GitHub HTTP, decoding, focus parsing, or candidate selection logic.
- [ ] Repository context formatting is unchanged.
- [ ] Existing public schemas and routes are unchanged.
- [ ] Provider tests cover GitHub integration behavior.
- [ ] Agent tests cover orchestration with a fake provider.
- [ ] Targeted tests and compile validation pass.

## Rollback Strategy
1. Revert `LabCodeExampleAgent` provider injection.
2. Move provider helper logic back into `labs/agents/labs_code_example/agent.py`.
3. Restore the original helper-focused tests in `tests/test_labs_code_example_agent.py`.
4. Keep the provider package unused until the migration can be retried.
