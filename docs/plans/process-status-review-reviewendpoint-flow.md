# Process Status Review Endpoint Flow Plan

## Source Spec

Implementation source of truth:

```text
docs/specs/process-status-review-reviewendpoint-flow.md
```

This plan changes the review workflow from a direct file upload to a process-first flow: create a `ProcessStatus`, upload `.md` or `.txt` note files into `ProcessStatusNote`, then start review with `/labs/review/{process_status_id}` using all notes for that process.

## Decisions To Preserve

- The note upload endpoint is:

```text
POST /labs/files-note/{process_status_id}
```

- The review start endpoint is:

```text
POST /labs/review/{process_status_id}
```

- Remove the old `POST /labs/review` route immediately. Do not keep a deprecated compatibility route.
- The note upload endpoint accepts exactly one multipart `file`.
- Accepted file suffixes are `.md` and `.txt`, case-insensitive.
- Unsupported file suffixes return `400`.
- Invalid UTF-8 returns `400`.
- Empty uploaded files return `422`.
- Uploaded files larger than `10 KiB` return `422`.
- Uploaded file text is stored exactly as decoded in `ProcessStatusNote.description`; do not trim or transform it.
- The target `ProcessStatus` must exist and belong to the authenticated user before a note can be created or a review can start.
- Non-owned or missing processes return `404`.
- Review context is built from all notes for the process, in deterministic order, joined with:

```python
"\n\n"
```

- `POST /labs/review/{process_status_id}` must use the existing `ProcessStatus.id`; it must not create a new `ProcessStatus`.
- Existing JSON note behavior at `POST /labs/processes/notes` remains supported.

## Phase 1: Process-Scoped Note Repository

Files:

```text
labs/process_status/repository.py
tests/test_process_status_repository.py
```

Steps:

1. Add `ProcessStatusNoteRepository.list_by_process_status_id(process_status_id: UUID) -> list[ProcessStatusNote]`.
2. Query only notes where `ProcessStatusNote.process_status_id == process_status_id`.
3. Sort notes for review context in deterministic creation order:

```text
created_at ascending, then updated_at ascending
```

4. Keep the existing `list_by_process_status_ids` method unchanged for `GET /labs/process/notes`.
5. Add repository tests that assert:
   - the single-process query filters by `process_status_id`,
   - sort order is ascending by `created_at` then `updated_at`,
   - existing multi-process note listing behavior still works.

Deliverable:

- Service code can fetch the exact notes used to start one process review without changing global note listing.

## Phase 2: Process Status Service Note Helpers

Files:

```text
labs/process_status/service.py
tests/test_process_status_service.py
```

Steps:

1. Add a service method for creating a note from uploaded text, for example:

```python
async def create_note_from_file(
    self,
    *,
    process_status_id: UUID,
    user_id: UUID,
    description: str,
) -> ProcessStatusNoteResponse | None:
```

2. In that method, verify ownership with:

```python
ProcessStatusRepository.get_by_id(process_id=process_status_id, user_id=user_id)
```

3. Return `None` when the process is missing or not owned by the user.
4. Create a `ProcessStatusNote` with the exact decoded text as `description`.
5. Return `ProcessStatusNoteResponse.from_process_status_note(note)`.
6. Add a process-scoped note listing method, for example:

```python
async def list_notes_for_process(
    self,
    *,
    process_status_id: UUID,
    user_id: UUID,
) -> list[ProcessStatusNote] | None:
```

7. Verify process ownership before listing notes.
8. Return `None` for missing or non-owned processes.
9. Return repository note documents, not response schemas, when the caller needs `description` for agent context.
10. Add service tests for:
    - successful file-note creation,
    - missing process returns `None`,
    - non-owned process returns `None`,
    - raw text is not stripped,
    - process-scoped note listing calls the repository only after ownership verification.

Deliverable:

- Ownership checks and note persistence stay centralized in `ProcessStatusService`.

## Phase 3: File Note Upload Endpoint

Files:

```text
labs/agents/router.py
labs/process_status/schemas.py
tests/test_auth_routes.py
tests/test_process_status_router.py or tests/test_agents_router.py
```

Steps:

1. Add `POST /labs/files-note/{process_status_id}` to the authenticated Labs router.
2. Accept:

```python
process_status_id: UUID
file: UploadFile = File(...)
user: AuthenticatedUser = Depends(get_current_user)
```

3. Validate the filename:
   - missing or empty filename returns `400`,
   - suffix not in `{".md", ".txt"}` returns `400`,
   - suffix check is case-insensitive.
4. Read uploaded bytes.
5. Enforce size and content validation:
   - `len(raw_content) == 0` returns `422`,
   - `len(raw_content) > 10 * 1024` returns `422`.
6. Decode UTF-8:
   - `UnicodeDecodeError` returns `400`.
7. Call `ProcessStatusService.create_note_from_file(...)`.
8. If the service returns `None`, raise `404` with a message such as:

```text
Process status not found.
```

9. Return `ProcessStatusNoteResponse`.
10. Add route tests for:
    - `.md` upload success,
    - `.txt` upload success,
    - uppercase suffix success,
    - unsupported suffix returns `400`,
    - missing filename returns `400`,
    - invalid UTF-8 returns `400`,
    - empty file returns `422`,
    - oversized file returns `422`,
    - missing/non-owned process returns `404`,
    - unauthenticated request returns `401`.

Deliverable:

- Users can attach one-page note files to an existing process with strict validation and ownership checks.

## Phase 4: Review Service Refactor

Files:

```text
labs/agents/service.py
tests/test_service.py
```

Steps:

1. Add a service method for the new review flow, for example:

```python
async def enqueue_markdown_organization_for_process(
    self,
    *,
    background_tasks: BackgroundTasks,
    process_status_id: UUID,
    user_id: UUID,
) -> dict[str, str]:
```

2. Verify process ownership and fetch notes through `ProcessStatusService`.
3. If the process is missing or not owned by the user, raise `404`.
4. If the process has no notes, raise `400` with:

```text
Process status has no notes to review.
```

5. Build `context` with:

```python
"\n\n".join(note.description for note in notes)
```

6. Derive a safe output filename without relying on an uploaded review file:
   - use a sanitized base from `ProcessStatus.file` when usable,
   - otherwise use `process_{process_status_id}.md`,
   - force `.md` suffix,
   - write under `PUBLIC_MARKDOWN_DIR`.
7. Build `MarkdownOrganizationJob` with:

```python
process_status_id=process_status_id
context=context
output_path=output_path
```

8. Enqueue with the existing `markdown_dispatcher.enqueue(...)` contract.
9. Preserve dispatcher error behavior:
   - `TaskDispatchEnqueueError` maps to HTTP `503`,
   - response shape remains `message`, `process_id`, `output_file`.
10. Keep or refactor existing helper logic only as needed. Do not create a new `ProcessStatus` from this path.
11. Add service tests that assert:
    - the created job uses the existing process id,
    - context is joined with `\n\n`,
    - note order is preserved from the service/repository result,
    - no call is made to `create_process_for_review`,
    - no notes returns `400`,
    - missing/non-owned process returns `404`,
    - dispatcher failure still returns `503`,
    - output path always ends in `.md`.

Deliverable:

- Review dispatch starts from existing process notes and keeps the current async markdown job infrastructure.

## Phase 5: Review Router Replacement

Files:

```text
labs/agents/router.py
tests/test_auth_routes.py
tests/test_service.py
```

Steps:

1. Replace:

```python
@router.post("/review")
```

with:

```python
@router.post("/review/{process_status_id}")
```

2. Remove `file: UploadFile = File(...)` from the review endpoint.
3. Parse `process_status_id` as `UUID`.
4. Keep `BackgroundTasks` and authenticated user injection.
5. Call `LabPostService.enqueue_markdown_organization_for_process(...)`.
6. Remove old direct file-reading and UTF-8 decoding from the review endpoint.
7. Confirm `/labs/review` is no longer registered in OpenAPI.
8. Add or update router/auth tests:
   - `POST /labs/review/{process_status_id}` requires authorization,
   - valid authenticated call delegates to the service with `process_status_id` and `user_id`,
   - invalid UUID returns `422`,
   - old `POST /labs/review` is not treated as the supported endpoint.

Deliverable:

- The public API requires an existing process id to start review.

## Phase 6: Response Contracts And OpenAPI

Files:

```text
labs/process_status/schemas.py
labs/agents/router.py
tests/test_process_status_router.py
tests/test_auth_routes.py
```

Steps:

1. Reuse `ProcessStatusNoteResponse` for the note upload endpoint.
2. Keep the review response as:

```text
message: str
process_id: str
output_file: str
```

3. Ensure OpenAPI documents:
   - `POST /labs/files-note/{process_status_id}` with multipart upload,
   - `POST /labs/review/{process_status_id}`,
   - no supported `POST /labs/review` endpoint.
4. Keep existing process-status endpoint schemas unchanged.
5. Add OpenAPI assertions if the project already has endpoint schema tests near this area.

Deliverable:

- API documentation reflects the new process-first review flow.

## Phase 7: Regression And Full Test Pass

Files:

```text
tests/test_process_status_repository.py
tests/test_process_status_service.py
tests/test_process_status_router.py
tests/test_auth_routes.py
tests/test_service.py
```

Steps:

1. Run focused tests:

```bash
PYTHONPATH=. pytest \
  tests/test_process_status_repository.py \
  tests/test_process_status_service.py \
  tests/test_process_status_router.py \
  tests/test_auth_routes.py \
  tests/test_service.py -q
```

2. Run the full suite:

```bash
PYTHONPATH=. pytest -q
```

3. Fix any regressions in existing note JSON behavior:
   - `POST /labs/processes/notes`,
   - `GET /labs/process/notes`,
   - process status reads,
   - agent process status reads.
4. Confirm the old file-backed review assumptions are removed from tests.

Deliverable:

- New flow is covered and existing process status behavior remains stable.

## Manual Verification

Use an authenticated request flow:

1. Create a process:

```text
POST /labs/processes/create
```

2. Upload one `.md` note:

```text
POST /labs/files-note/{process_status_id}
```

3. Upload one `.txt` note:

```text
POST /labs/files-note/{process_status_id}
```

4. Start review:

```text
POST /labs/review/{process_status_id}
```

5. Fetch status:

```text
GET /labs/processes/{process_status_id}/status
```

Expected result:

- The returned `process_id` from review equals the existing process id.
- The created agent process records belong to the same process id.
- Generated markdown output path ends with `.md`.
- The note descriptions were passed into the job context separated by `\n\n`.

## Rollback Notes

- Reverting this feature requires restoring the old `POST /labs/review` upload endpoint and restoring review-time process creation in `LabPostService.enqueue_markdown_organization`.
- Do not remove `ProcessStatusNote` data or schemas during rollback; notes are already used by separate process note endpoints.
- If the note upload endpoint causes issues independently, disable `POST /labs/files-note/{process_status_id}` while keeping JSON note creation available.

## Implementation Checklist

- [ ] Add single-process note repository listing.
- [ ] Add service method to create notes from uploaded text.
- [ ] Add service method to list notes for a specific owned process.
- [ ] Add `POST /labs/files-note/{process_status_id}`.
- [ ] Enforce `.md` and `.txt` suffix validation.
- [ ] Enforce UTF-8 decoding.
- [ ] Enforce empty-file `422`.
- [ ] Enforce `10 KiB` upload limit `422`.
- [ ] Add review service path for existing process ids.
- [ ] Join note descriptions with `\n\n`.
- [ ] Remove old `POST /labs/review`.
- [ ] Add `POST /labs/review/{process_status_id}`.
- [ ] Verify review does not create a new `ProcessStatus`.
- [ ] Update focused tests.
- [ ] Run full `PYTHONPATH=. pytest -q`.
