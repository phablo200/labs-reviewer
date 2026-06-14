# Focus GitHub Folders for Code Example Extraction Plan

## Objective
- Implement markdown-driven focus folders so `LabCodeExampleAgent` prioritizes user-specified repository paths when selecting code excerpts for `LabPostWriterAgent`.

## Source Spec
- `docs/specs/focus-github-folders-code-examples.md`

## Decisions
- Parse focus folders from markdown notes instead of adding a new API field.
- Keep `MAX_FILES_PER_REPO = 3` for now.
- Exclude test files by default unless they are explicitly listed in focus paths.
- Preserve current generic fallback behavior when no focus section exists.

## Implementation Steps
1. Add focus heading detection
   - Add `_is_focus_heading(line: str) -> bool` in `labs/agents/labs_code_example/agent.py`.
   - Match markdown headings containing `focus`, `github`, and either `folder` or `path`.
   - Support variants such as `Focus Github Folders`, `Focus on Github Folders`, `GitHub Focus Folders`, and `Focus GitHub Paths`.

2. Add focus path parsing
   - Add `_extract_focus_paths(text: str) -> list[str]`.
   - Read bullet items after a focus heading until the next heading or non-list block.
   - Normalize paths by trimming whitespace, bullets, backticks, leading `/`, and trailing `/`.
   - Ignore empty items and full GitHub URLs.
   - Deduplicate paths while preserving order.

3. Add source-file helpers
   - Keep the existing source extension filter.
   - Add `_is_test_path(path: str) -> bool`.
   - Add `_matches_focus_path(path: str, focus_path: str) -> bool`.
   - Treat focus paths as either exact files or folder prefixes.

4. Add prioritized selection
   - Add `_select_candidate_paths(tree_items: list[dict], focus_paths: list[str]) -> list[str]`.
   - Selection order:
     1. source files matching focus paths, including tests if explicitly focused;
     2. generic candidate source files, excluding tests;
     3. deduplicated and capped at `MAX_FILES_PER_REPO`.
   - Do not increase the file cap in this implementation.

5. Wire focus paths into fetch flow
   - Parse focus paths once in `extract_examples(...)`.
   - Pass focus paths into `_fetch_repo_context(...)`.
   - Use `_select_candidate_paths(...)` instead of inline candidate filtering.
   - Include selected focus paths in the formatted human context for traceability.

6. Update tests
   - Add parser tests in `tests/test_labs_code_example_agent.py`.
   - Add selection tests proving focus paths outrank `core/config.py`, `core/llm_config.py`, and `labs/router.py`.
   - Add tests proving generic selection excludes tests unless explicitly focused.
   - Keep existing success/failure structured-output tests passing.

## Validation Commands
```bash
venv/bin/python -m pytest -q tests/test_labs_code_example_agent.py
venv/bin/python -m pytest -q tests/test_labs_post_writer_agent.py tests/test_service.py
```

## Manual Check
1. Upload a markdown note containing:

```md
https://github.com/phablo200/blog-reviewer

# Focus on Github Folders:
- labs/agents/labs_code_example
- labs/agents/labs_post_metadata
- labs/agents/labs_post_translator
- labs/agents/labs_reviewer
```

2. Confirm the fetched repository context includes files under the focused folders before generic config/router files.
3. Confirm the final markdown contains code examples relevant to the focused folders.
4. Confirm LangSmith traces show the focused selected files in the code-example agent input.

## Acceptance Checklist
- [ ] Focus headings are detected across supported title variants.
- [ ] Focus paths are parsed and normalized from markdown bullets.
- [ ] Focused source files are selected before generic candidates.
- [ ] Generic fallback still works when no focus section exists.
- [ ] Test files are excluded by default unless explicitly focused.
- [ ] Selection remains capped by `MAX_FILES_PER_REPO = 3`.
- [ ] Writer still appends `Code Examples Context` only when examples are returned.
