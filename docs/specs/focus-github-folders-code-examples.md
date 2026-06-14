# Focus GitHub Folders for Code Example Extraction

## Title
Focus GitHub Folders for Code Example Extraction

## Objective
- Improve `labs_post_writer` output quality by letting user notes declare GitHub folders/files that `LabCodeExampleAgent` should prioritize when fetching repository code examples.
- Make repository-backed examples more deterministic by preferring user-specified paths before generic file heuristics.

## Background
- `LabPostWriterAgent.organize_notes(...)` calls `LabCodeExampleAgent.extract_examples(...)` before generating the initial draft.
- `LabCodeExampleAgent` currently extracts GitHub repositories from `notes_context`, fetches the GitHub tree, selects up to `MAX_FILES_PER_REPO = 3` files, and sends those excerpts to the LLM.
- Current file selection is based on generic filename keywords: `main`, `app`, `router`, `route`, `service`, `handler`, and `config`.
- This misses relevant folders such as `labs/agents/labs_code_example`, because `agent.py`, `schema.py`, and `prompts.py` do not match the current keyword filter.
- User notes may include a section such as:

```md
# Focus on Github Folders:
- labs/agents/labs_code_example
- labs/agents/labs_post_metadata
- labs/agents/labs_post_translator
- labs/agents/labs_reviewer
```

- That section is sufficient to drive better selection, but the current implementation does not parse or use it.

## Scope
### In Scope
- Parse focus path sections from uploaded notes.
- Support similar heading variants, including:
  - `Focus Github Folders`
  - `Focus on Github Folders`
  - `GitHub Focus Folders`
  - `Focus GitHub Paths`
- Accept markdown bullet lists under the heading.
- Treat listed values as repository-relative folder or file paths.
- Prioritize source files under focus folders before generic candidates.
- Preserve existing behavior when no focus section is present.
- Add unit tests for focus path parsing and prioritized file selection.

### Out of Scope
- Supporting private GitHub repositories or authenticated GitHub API access.
- Supporting non-GitHub repository providers.
- Adding a new public API field for focus paths.
- Changing the writer/reviewer/translator prompt contracts beyond including better code context.
- Fetching every file in large repositories without limits.

## Proposed Approach
- Add focus-path extraction to `labs/agents/labs_code_example/agent.py`.
- Keep the input format user-friendly by parsing paths from `notes_context`; no route or request schema change is required for the first iteration.
- Introduce a helper such as `_extract_focus_paths(text: str) -> list[str]`.
- Parse the markdown section by:
  - matching headings whose normalized text contains `focus`, `github`, and one of `folder`, `folders`, `path`, or `paths`;
  - reading following markdown bullet lines until the next heading or non-list content block;
  - normalizing values by trimming whitespace, backticks, leading slashes, and trailing slashes;
  - ignoring empty values and full GitHub URLs.
- Introduce a helper such as `_select_candidate_paths(tree_items: list[dict], focus_paths: list[str]) -> list[str]`.
- Selection order:
  1. source files under explicitly listed focus folders;
  2. explicitly listed source files;
  3. generic candidate source files using the existing heuristic;
  4. deduplicated and capped by `MAX_FILES_PER_REPO`.
- Increase `MAX_FILES_PER_REPO` from `3` to `8` to allow multi-agent folders to be represented without excessive context growth.
- Update `_fetch_repo_context(...)` to receive `focus_paths` and use the new selector.
- Update `extract_examples(...)` to parse focus paths once from `request.notes_context` and pass them into each repository fetch.
- Add selected focus paths to `_format_human_context(...)` so LangSmith traces show why specific files were included.

Impacted files:
- `labs/agents/labs_code_example/agent.py`
- `tests/test_labs_code_example_agent.py`
- Optional: `labs/agents/labs_code_example/schema.py` if a future explicit `focus_paths` request field is desired.

## Milestones
1. Implement focus path parser
   - Add `_extract_focus_paths(...)`.
   - Cover heading variants and bullet-list parsing with unit tests.
2. Implement priority file selection
   - Add `_select_candidate_paths(...)`.
   - Prefer focus-folder files before generic candidates.
   - Preserve generic fallback behavior.
3. Wire parser into repository fetch
   - Pass focus paths from `extract_examples(...)` into `_fetch_repo_context(...)`.
   - Include selected focus paths in the LLM human context.
4. Validate writer integration
   - Ensure `LabPostWriterAgent` still appends `Code Examples Context` only when examples exist.
   - Confirm no route or service contract changes are required.

## Edge Cases
- Focus heading exists but has no bullet items.
- Focus paths include leading `/`, trailing `/`, or inline backticks.
- Focus path points to a file instead of a folder.
- Focus path does not exist in the repository.
- Focus paths match too many files.
- Repository tree fetch fails.
- No focus section is present.
- Multiple GitHub repositories are referenced in the same notes.
- The same file is selected by both focus and generic heuristics.

## Acceptance Criteria
- [ ] Notes containing `# Focus on Github Folders:` cause matching repository files under those folders to be selected before `core/config.py`, `core/llm_config.py`, or `labs/router.py`.
- [ ] For `https://github.com/phablo200/blog-reviewer` with focus paths for `labs/agents/labs_code_example` and related agent folders, selected files include relevant `agent.py`, `schema.py`, or `prompts.py` files from those folders.
- [ ] Notes without focus paths continue to use the existing generic selection behavior.
- [ ] Duplicate selected files are removed while preserving priority order.
- [ ] Invalid or missing focus paths do not fail the request; they fall back to generic candidates and emit at most a non-fatal warning.
- [ ] The code-example LLM receives the selected file excerpts in `Fetched repository context`.

## Test Plan
- Unit:
  - Test `_extract_focus_paths(...)` with `Focus on Github Folders`, `Focus Github Folders`, and `Focus GitHub Paths` headings.
  - Test parser ignores unrelated bullet lists.
  - Test parser normalizes backticks, leading slashes, and trailing slashes.
  - Test `_select_candidate_paths(...)` prioritizes files under focus folders.
  - Test `_select_candidate_paths(...)` deduplicates files selected by focus and generic rules.
  - Test fallback generic selection when focus paths are empty.
- Integration:
  - Update `tests/test_labs_code_example_agent.py` to simulate a GitHub tree containing `core/config.py`, `labs/router.py`, and `labs/agents/.../agent.py`, then assert focus files are selected first.
  - Keep existing structured-output success/failure tests passing.
- Manual verification:
  - Run a local request using a markdown note containing `https://github.com/phablo200/blog-reviewer` and a `Focus on Github Folders` section.
  - Confirm logs or LangSmith traces show focused agent files in the fetched repository context.
  - Confirm final generated markdown contains code examples relevant to the focused folders.

## Risks and Mitigations
- Risk: Heading parsing becomes too permissive and captures unrelated lists.
  - Mitigation: Require heading text to contain both `focus` and `github`, plus `folder` or `path`.
- Risk: Focus folders select too many files and exceed context limits.
  - Mitigation: Keep `MAX_FILES_PER_REPO` capped and excerpt each file with `MAX_FILE_EXCERPT_CHARS`.
- Risk: User-provided paths include stale or incorrect folders.
  - Mitigation: Skip unmatched focus paths and fall back to generic candidates.
- Risk: Generic fallback still selects low-value config/test files.
  - Mitigation: Prefer focus paths first and consider a later ranking pass that deprioritizes `tests/` and config-only files.

## Open Questions
- Should focus paths also be exposed as an explicit API/request field later, or is markdown parsing enough?
- Should `MAX_FILES_PER_REPO` be configurable by environment variable? Not for now 3 is enough for testing purposes.
- Should test files be excluded by default unless explicitly listed in focus paths? Yes, unless they're in focus paths you can exclude them.
