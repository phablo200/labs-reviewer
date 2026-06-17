# Process Status Create And Notes Endpoint Plan

## Source Spec

Implementation source of truth:

```text
docs/specs/process-status-create-and-notes-endpoint.md
```

This plan adds authenticated endpoints for manually starting a writing `ProcessStatus`, creating/updating process notes, and listing all notes owned by the authenticated user.

## Decisions To Preserve

- Use the exact parent process state value `WRITTING`.
- `ProcessStatusState` must allow:

```python
Literal["WRITTING", "IN_PROGRESS", "FAILED", "SUCCEEDED"]
```

- `AgentProcessStatusState` must remain limited to:

```python
Literal["IN_PROGRESS", "FAILED", "SUCCEEDED"]
```

- Keep existing file-backed review flows starting with `IN_PROGRESS`.
- `POST /labs/processes/create` has no request body and creates a user-owned `ProcessStatus` with `status="WRITTING"`.
- `POST /labs/processes/notes?id=[optional]` creates a note when `id` is absent and updates a note when `id` is present.
- `POST /labs/processes/notes` returns only the stored note payload, not the parent process.
- `GET /labs/process/notes` returns all notes visible to the authenticated user.
- Note ownership is derived through parent `ProcessStatus.user_id`; do not add `user_id` directly to notes.
- `ProcessStatusNote` stores `process_status_id`, `description`, `created_at`, and `updated_at`.
- Do not rename `WRITTING` to `WRITING` in this implementation.

## Dependency On Celery And Redis Plan

This plan is intended to run after:

```text
docs/plans/integrating-celery-and-redis.md
```

Expected post-Celery baseline:

- `LabPostService` delegates Markdown work through a task dispatcher instead of calling `background_tasks.add_task(...)` directly.
- `labs/tasks/dependencies.py` builds worker/API Markdown processing dependencies, including `ProcessStatusService`.
- Celery tasks pass `process_status_id` as a string and rebuild dependencies inside the worker.
- `ProcessStatus` creation for `/labs/review` remains in `LabPostService.enqueue_markdown_organization(...)` before dispatch.
- Existing review flows still call `ProcessStatusService.create_process_for_review(file, user_id)` and must keep creating `IN_PROGRESS` records.

Required compatibility decisions:

- Do not change task dispatcher contracts, Celery task arguments, or `MarkdownOrganizationJob`.
- Keep `ProcessStatusService.__init__` backward-compatible by adding `note_repository` as an optional third dependency only. Existing calls from `labs/tasks/dependencies.py`, dispatchers, workers, and tests must continue working without passing a note repository.
- Do not move note creation/listing into Celery. Manual writing process and notes endpoints are synchronous API operations.
- Do not change `/labs/review` behavior or response keys while adding `/labs/processes/create`, `/labs/processes/notes`, and `/labs/process/notes`.

## Phase 1: Model Contract

Files:

```text
labs/process_status/models.py
core/database/mongodb.py
tests/test_process_status_models.py
```

Steps:

1. Split status aliases in `labs/process_status/models.py`.

```python
ProcessStatusState = Literal["WRITTING", "IN_PROGRESS", "FAILED", "SUCCEEDED"]
AgentProcessStatusState = Literal["IN_PROGRESS", "FAILED", "SUCCEEDED"]
```

2. Keep `ProcessStatus.status` defaulting to `IN_PROGRESS` for existing review workflows and backward compatibility.
3. Make `ProcessStatus.file` optional so empty-body manual creation can create a process without a file name.
4. Update `ProcessStatusResponse.file` later in the schema phase to accept `None`.
5. Add `ProcessStatusNote` as a Beanie document:

```python
class ProcessStatusNote(Document):
    id: UUID = Field(default_factory=uuid4)
    process_status_id: UUID
    description: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "process_status_notes"
```

6. Register `ProcessStatusNote` in `core/database/mongodb.py` alongside the existing process status document models.
7. Update model tests to cover:
   - process status can be `WRITTING`,
   - agent status test data stays within the original three values,
   - note collection name and fields,
   - note timestamps exist.

Deliverable:

- Data models support manual process creation and note persistence without widening agent process states.

## Phase 2: Response And Request Schemas

Files:

```text
labs/process_status/schemas.py
tests/test_process_status_models.py
```

Steps:

1. Update `ProcessStatusResponse.file` to `str | None`.
2. Keep `ProcessStatusResponse.status` typed as `ProcessStatusState`.
3. Add `ProcessStatusNoteRequest`:

```text
process_status_id: UUID
note: str
```

4. Validate `note` with a minimum non-empty length. Prefer a Pydantic `Field(min_length=1)` plus whitespace stripping if already consistent with project style.
5. Add `ProcessStatusNoteResponse`:

```text
id: UUID
process_status_id: UUID
description: str
created_at: datetime
updated_at: datetime
```

6. Add a mapper such as `from_process_status_note` to keep router/service serialization consistent with existing schemas.
7. Add schema tests proving note request/response shape and `ProcessStatusResponse.file=None` are supported.

Deliverable:

- API contracts are explicit and can represent both manual processes and persisted notes.

## Phase 3: Repository Operations

Files:

```text
labs/process_status/repository.py
tests/test_process_status_repository.py
```

Steps:

1. Add `ProcessStatusRepository.create_writing(user_id: UUID) -> ProcessStatus`.
2. Ensure `create_writing` creates:

```text
file=None
status="WRITTING"
user_id=<authenticated user id>
```

3. Preserve existing `ProcessStatusRepository.create(file, user_id)` behavior for file-backed review flows with `status="IN_PROGRESS"`.
4. Add `ProcessStatusNoteRepository`.
5. Implement note methods:
   - `create(process_status_id, description)`
   - `get_by_id(note_id)`
   - `update(note, description)`
   - `list_by_process_status_ids(process_status_ids)`
6. In `update`, preserve `created_at`, set `description`, refresh `updated_at` with `utc_now()`, save, and return the note.
7. In `list_by_process_status_ids`, return an empty list when no process ids are supplied.
8. Sort listed notes consistently, preferably newest first by `updated_at` then `created_at`.
9. Keep Beanie query details inside repository classes.
10. Add repository tests for writing-process creation, note create/update timestamp behavior, missing empty-list behavior, and list-by-process ids.

Deliverable:

- Persistence supports manual processes and note CRUD/list operations with clear timestamp behavior.

## Phase 4: Service Composition

Files:

```text
labs/process_status/service.py
labs/tasks/dependencies.py
tests/test_process_status_service.py
tests/test_task_dependencies.py
```

Steps:

1. Extend `ProcessStatusService.__init__` to accept an optional `note_repository` for tests.
2. Verify existing Celery dependency builder code can still construct `ProcessStatusService()` with no arguments.
3. Add `create_writing_process_status(user_id)`.
4. Return a `ProcessStatusResponse` built from the created process.
5. Add `create_or_update_note(user_id, request, note_id=None)`.
6. For note creation:
   - verify `request.process_status_id` belongs to `user_id` through `ProcessStatusRepository.get_by_id`,
   - create the note with `description=request.note`,
   - return `ProcessStatusNoteResponse`.
7. For note update:
   - fetch the note by `note_id`,
   - return `None` or raise a service-level not-found signal if missing,
   - verify the note's parent process belongs to `user_id`,
   - update `description` and `updated_at`,
   - return `ProcessStatusNoteResponse`.
8. Add `list_notes(user_id)`.
9. For listing:
   - retrieve all process statuses owned by the user,
   - collect process ids,
   - fetch notes with matching `process_status_id`,
   - return `ProcessStatusNoteResponse` items.
10. Do not return or embed notes from existing process status read methods.
11. Keep existing `_derive_process_status` returning only `IN_PROGRESS`, `FAILED`, or `SUCCEEDED`; it must not derive `WRITTING` from agent states.
12. Re-run or update Celery dependency-builder tests if they assert `ProcessStatusService` construction details.
13. Add service tests for:
   - writing process creation,
   - note creation ownership check,
   - note update ownership check,
   - missing note update,
   - note listing filtered to user-owned process ids,
   - aggregate status derivation unchanged.

Deliverable:

- Service layer enforces ownership and exposes note operations without leaking notes across users.

## Phase 5: Router Endpoints

Files:

```text
labs/process_status/router.py
tests/test_process_status_router.py
```

Steps:

1. Add to the existing `/labs/processes` router:

```text
POST /labs/processes/create
POST /labs/processes/notes?id=[optional]
```

2. Add the singular notes list path to the existing process status router in `labs/process_status/router.py`:

```text
GET /labs/process/notes
```

3. Keep router registration unchanged in `main.py`; do not create or include a new router.
4. Add coverage for the new route in `tests/test_process_status_router.py` using the existing process status router test app setup.
5. Protect all new endpoints with `get_current_user`.
6. Parse user id with `parse_user_id(user)`.
7. `POST /labs/processes/create` should not require a body and should return `ProcessStatusResponse`.
8. `POST /labs/processes/notes` should accept `ProcessStatusNoteRequest`, optional query `id: UUID | None`, and return `ProcessStatusNoteResponse`.
9. `GET /labs/process/notes` should return `list[ProcessStatusNoteResponse]`.
10. Return `404` when:
   - parent process is missing,
   - parent process belongs to another user,
   - requested note id is missing,
   - requested note belongs to another user's process.
11. Let FastAPI/Pydantic return `422` for malformed UUIDs or invalid note bodies.
12. Add router tests for:
   - unauthenticated `401` on all new endpoints,
   - successful empty-body create,
   - create response includes `WRITTING`,
   - note create returns only note fields,
   - note update returns only note fields,
   - note list returns only authenticated user's notes,
   - missing/unauthorized resources return `404`.

Deliverable:

- Public API matches the spec paths, authentication requirements, and response contracts.

## Phase 6: Compatibility Checks

Files:

```text
labs/tasks/dependencies.py
labs/tasks/fastapi_dispatcher.py
labs/tasks/celery_tasks.py
labs/tasks/celery_dispatcher.py
labs/agents/service.py
labs/helpers/markdown_helper.py
labs/process_status/proxy.py
tests/test_service.py
tests/test_task_dependencies.py
tests/test_task_dispatchers.py
tests/test_celery_tasks.py
```

Steps:

1. Confirm existing review workflow still calls `create_process_for_review(file, user_id)` before dispatch and receives `IN_PROGRESS`.
2. Confirm `MarkdownOrganizationJob` remains unchanged and still carries only `context`, `output_path`, and `process_status_id`.
3. Confirm Celery task arguments remain JSON-serializable strings/primitives; do not add note data or `WRITTING` data to Celery payloads.
4. Confirm `labs/tasks/dependencies.py` still builds a `ProcessStatusService` that works in both API and worker contexts after the optional `note_repository` parameter is added.
5. Confirm optional `ProcessStatus.file` does not break filename filtering in `ProcessStatusRepository.list_by_user_id`.
6. If `file` can be `None`, adjust filtering logic to still work for normal file-backed records.
7. Confirm process list/status responses still serialize existing file-backed records.
8. Confirm `AgentInvocationProxy` and markdown helper imports do not depend on `AgentProcessStatusState` being aliased to `ProcessStatusState`.
9. Confirm `TASK_DISPATCHER=background_tasks` and `TASK_DISPATCHER=celery` tests still pass without changes to dispatcher behavior.

Deliverable:

- Existing agent-backed process tracking and Celery dispatch keep working while manual writing processes are added.

## Phase 7: Verification

Focused commands:

```bash
pytest tests/test_process_status_models.py
pytest tests/test_process_status_repository.py
pytest tests/test_process_status_service.py
pytest tests/test_process_status_router.py
```

Post-Celery regression commands:

```bash
pytest tests/test_service.py
pytest tests/test_task_dependencies.py
pytest tests/test_task_dispatchers.py
pytest tests/test_task_dispatcher_factory.py
pytest tests/test_celery_tasks.py
```

Broader check:

```bash
pytest
```

Manual verification:

1. Start the API with MongoDB configured.
2. Call `POST /labs/processes/create` with an auth token and no body.
3. Confirm the response has `status="WRITTING"` and `file=null`.
4. Call `POST /labs/processes/notes` with the returned process id and a note.
5. Confirm the response contains only note fields and includes `created_at` and `updated_at`.
6. Call `POST /labs/processes/notes?id=<note_id>` with a new note value.
7. Confirm `description` changes, `created_at` is preserved, and `updated_at` changes.
8. Call `GET /labs/process/notes` with the same auth token.
9. Confirm the note appears in the list.
10. Call the same list endpoint as another user and confirm the note is not returned.
11. With `TASK_DISPATCHER=background_tasks`, submit a normal `/labs/review` request and confirm it still returns `message`, `process_id`, and `output_file`.
12. With `TASK_DISPATCHER=celery`, submit a normal `/labs/review` request with Celery enqueue mocked or with a worker running and confirm the process status starts as `IN_PROGRESS`.

Deliverable:

- Tests and manual checks prove endpoint contracts, ownership, timestamps, and compatibility with the Celery dispatch work.

## Implementation Notes

- Keep all note persistence in `labs/process_status/repository.py`; do not query Beanie directly from routers.
- Keep ownership checks in the service so both router and future callers reuse the same rules.
- Prefer returning `None` from service methods for not-found cases if that matches existing service/router style.
- Preserve current `404` pattern in `labs/process_status/router.py`.
- Do not add note data to `ProcessStatusResponse` unless a future spec requests it.
- Use `utc_now` from `core.utils.datetime` for note timestamps.
- Treat the Celery task dispatcher layer as unrelated to manual writing notes; this plan should not edit `labs/tasks/*` except to fix constructor/test fallout from the optional `ProcessStatusService.note_repository`.
- Be careful with route ordering: `/create` and `/notes` must be declared before `/{process_id}/status` if FastAPI path matching would otherwise treat them as dynamic segments.

## Rollback Plan

1. Remove the new endpoints from `labs/process_status/router.py`.
2. Remove note service and repository methods.
3. Remove `ProcessStatusNote` from Beanie registration and models.
4. Restore `ProcessStatus.file` as required if no manual process records need to be preserved.
5. Remove `WRITTING` from `ProcessStatusState`.
6. Re-alias `AgentProcessStatusState` only if no code depends on separated status aliases.
7. Revert related tests.

MongoDB rows created in `process_status_notes` can be ignored in local/test environments unless production cleanup is explicitly required.
