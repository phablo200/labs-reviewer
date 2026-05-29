# GitHub Provider Extraction

## Title
GitHub Provider Extraction

## Objective
- Isolate GitHub repository discovery, API access, file selection, and context formatting in `labs/providers/github.py`.
- Keep `LabCodeExampleAgent` focused on code-example orchestration, LLM prompting, response normalization, and warning handling.
- Preserve the current behavior and public API of code-example extraction.

## Background
- `labs/agents/labs_code_example/agent.py` currently mixes two responsibilities:
  - LLM agent orchestration through `extract_examples(...)`, `_format_human_context(...)`, and response normalization.
  - GitHub integration through repository URL parsing, `GITHUB_TOKEN` header handling, GitHub API calls, repository tree traversal, file decoding, focus-path parsing, candidate file ranking, and repository context formatting.
- `labs/providers/github.py` exists but is empty.
- Existing tests in `tests/test_labs_code_example_agent.py` validate GitHub-specific helpers directly on `LabCodeExampleAgent`, including `_http_get_json(...)`, `_extract_focus_paths(...)`, `_select_candidate_paths(...)`, and `_fetch_repo_context(...)`.
- The current implementation depends on:
  - `labs.agents.labs_post_writer.constants.GITHUB_REPO_URL_PATTERN`
  - `urllib.request.Request`
  - `urllib.request.urlopen`
  - `GITHUB_TOKEN`
  - GitHub REST API endpoints under `https://api.github.com/repos/{owner}/{repo}`

## Scope
### In Scope
- Move GitHub-specific constants, helpers, and fetch logic from `labs/agents/labs_code_example/agent.py` to `labs/providers/github.py`.
- Provide a cohesive provider API that the code-example agent can call.
- Preserve the exact repository context text shape consumed by the LLM:
  - `Repository: ...`
  - `Description: ...`
  - `Language: ...`
  - `Default branch: ...`
  - `File: ...`
  - `Language: ...`
  - fenced `Snippet` blocks
- Preserve current limits:
  - `MAX_FILE_EXCERPT_CHARS = 2500`
  - `MAX_FILES_PER_REPO = 3`
  - existing focused filename priority order
- Preserve warning behavior in `LabCodeExampleAgent.extract_examples(...)` for `HTTPError`, `URLError`, `TimeoutError`, and unexpected exceptions.
- Update tests so GitHub provider behavior is tested through `labs.providers.github`.
- Keep `LabCodeExampleAgent` backward-compatible for production call sites.

### Out of Scope
- Adding support for GitHub GraphQL.
- Adding support for other Git providers.
- Changing route, service, or request/response schemas.
- Changing LLM prompts or structured output schemas.
- Changing authentication beyond reusing the current optional `GITHUB_TOKEN`.
- Adding retries, caching, pagination, or rate-limit handling.

## Proposed Approach
- Implement `GitHubProvider` in `labs/providers/github.py`.
- Move these responsibilities into the provider:
  - `GITHUB_REPO_URL_PATTERN` usage for repository extraction.
  - GitHub HTTP GET JSON requests with `Accept`, `User-Agent`, and optional `Authorization` headers.
  - Base64 content decoding.
  - Source-file and candidate-file detection.
  - Focus heading and focus path parsing.
  - Test path detection and focus path matching.
  - Candidate path selection from GitHub tree API results.
  - Repository context fetching and formatting.
  - Language detection from file paths, if needed for context formatting.
- Keep code-example-specific response normalization in `LabCodeExampleAgent`.
- Update `LabCodeExampleAgent.__init__(...)` to accept an optional provider dependency:

```python
def __init__(
    self,
    llm: BaseChatModel | None = None,
    github_provider: GitHubProvider | None = None,
) -> None:
    ...
```

- In `extract_examples(...)`, replace direct helper calls with provider calls:
  - `self.github_provider.extract_repositories(request.notes_context)`
  - `self.github_provider.extract_focus_paths(request.notes_context)`
  - `self.github_provider.fetch_repo_context(repository, focus_paths)`
- Keep `_format_human_context(...)`, `_extract_context_file_paths(...)`, `_normalize_response_data(...)`, and `_language_from_file_path(...)` in the agent unless provider language detection is reused directly.
- Prefer one of these compatibility paths:
  - Recommended: update tests and internal call sites to use the provider directly for GitHub helper behavior, without keeping duplicate static wrappers on the agent.
  - Temporary alternative: keep deprecated thin wrappers on `LabCodeExampleAgent` only if too many tests or call sites rely on private helper methods.

Impacted files:
- `labs/providers/github.py`
- `labs/agents/labs_code_example/agent.py`
- `tests/test_labs_code_example_agent.py`
- Optional: `tests/test_github_provider.py`

## Milestones
1. Build the provider module
   - Add `GitHubProvider` to `labs/providers/github.py`.
   - Move GitHub constants and helper methods from `LabCodeExampleAgent`.
   - Keep method names close to existing private helpers where that lowers migration risk.
2. Inject provider into the code-example agent
   - Add `github_provider` construction in `LabCodeExampleAgent.__init__(...)`.
   - Replace direct GitHub helper calls in `extract_examples(...)`.
   - Replace `_fetch_repo_context(...)` usage with `GitHubProvider.fetch_repo_context(...)`.
3. Clean up agent responsibilities
   - Remove unused imports from `agent.py`: `base64`, `json`, `os`, `re`, `Request`, `urlopen`, and GitHub-specific constants if no longer used.
   - Keep `HTTPError` and `URLError` imports in the agent if exception-specific warnings remain there.
4. Migrate tests
   - Move GitHub helper tests to a provider-focused test module.
   - Update agent tests to mock or stub `github_provider` instead of monkeypatching agent private GitHub methods.
   - Keep one agent integration-style unit test proving `extract_examples(...)` passes repositories, focus paths, and fetched context into the prompt flow.
5. Validate behavior
   - Run focused tests for code-example extraction and provider behavior.
   - Run syntax validation across `main.py`, `labs`, and `core`.

## Edge Cases
- Notes include duplicate GitHub repository URLs.
- Repository URL ends in `.git`.
- `GITHUB_TOKEN` is unset or blank.
- GitHub repo metadata fetch succeeds but recursive tree fetch fails.
- Tree contains only tests or non-source files.
- Focus paths include leading slashes, trailing slashes, backticks, duplicate entries, URLs, or missing paths.
- GitHub content API returns empty content.
- File content contains invalid UTF-8 bytes.
- Individual file fetch fails after repository metadata succeeds.
- Provider raises `HTTPError`, `URLError`, `TimeoutError`, or unexpected exceptions.

## Acceptance Criteria
- [ ] `labs/providers/github.py` contains the GitHub integration logic currently embedded in `LabCodeExampleAgent`.
- [ ] `LabCodeExampleAgent` no longer imports or directly uses `base64`, `json`, `os`, `re`, `Request`, `urlopen`, or `GITHUB_REPO_URL_PATTERN`.
- [ ] `LabCodeExampleAgent.extract_examples(...)` still returns the existing no-repository warning when no GitHub repositories are detected.
- [ ] `LabCodeExampleAgent.extract_examples(...)` still catches GitHub fetch errors and appends the same user-facing warning strings.
- [ ] Provider repository extraction still deduplicates URLs and strips `.git` suffixes.
- [ ] Provider focus path extraction still supports the existing heading variants and normalization rules.
- [ ] Provider candidate selection still prioritizes focused files, excludes tests from generic fallback, deduplicates paths, and caps selection at three files.
- [ ] Provider context formatting remains compatible with `_extract_context_file_paths(...)` by preserving `File: ...` lines.
- [ ] Existing public request and response schemas remain unchanged.

## Test Plan
- Unit:
  - Add or move tests for `GitHubProvider.http_get_json(...)` header behavior with and without `GITHUB_TOKEN`.
  - Add or move tests for `GitHubProvider.extract_repositories(...)`.
  - Add or move tests for `GitHubProvider.extract_focus_paths(...)`.
  - Add or move tests for `GitHubProvider.select_candidate_paths(...)`.
  - Add or move tests for `GitHubProvider.fetch_repo_context(...)` using monkeypatched HTTP responses.
  - Update agent tests to use a fake provider for success, no repository, and fetch-error paths.
- Integration:
  - Keep `test_extract_examples_successful_structured_response` or equivalent to prove fetched context still reaches the LLM flow.
  - Keep structured-output failure and partial-response normalization tests passing.
- Manual verification:
  - Run `python -m compileall main.py labs core`.
  - Run `pytest tests/test_labs_code_example_agent.py`.
  - If a provider test module is added, run `pytest tests/test_github_provider.py`.

## Risks and Mitigations
- Risk: Moving private helpers breaks tests that assert directly against `LabCodeExampleAgent`.
  - Mitigation: Move those assertions to provider tests and keep agent tests focused on orchestration.
- Risk: Context formatting changes cause poorer LLM extraction or response normalization fallback issues.
  - Mitigation: Preserve the current context string format exactly and add assertions for `File:`, `Language:`, `Snippet:`, and fenced code blocks.
- Risk: Exception handling moves too far into the provider, changing warning strings.
  - Mitigation: Let provider raise fetch exceptions and keep current warning construction in `LabCodeExampleAgent.extract_examples(...)`.
- Risk: Introducing a provider class makes tests harder to stub.
  - Mitigation: Inject provider through the agent constructor and use a simple fake object in agent tests.

## Open Questions
- Should `GITHUB_REPO_URL_PATTERN` move from `labs/agents/labs_post_writer/constants.py` into `labs/providers/github.py`, or should the provider import the existing constant to avoid touching writer constants? Yes I have just created a folder `labs/providers/github`, now you have `labs/providers/github/constants.py` and `labs/providers/github/github.py`, migrate constants to constants.
- Should provider methods be public names such as `extract_repositories(...)` and `fetch_repo_context(...)`, while lower-level helpers remain private? Yes
- Should `GitHubProvider` accept timeout and user-agent constructor arguments now, or keep the current hard-coded values until a configuration need appears? Please, provide arguments now.
