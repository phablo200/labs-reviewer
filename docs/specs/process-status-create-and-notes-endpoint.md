# Process Status Create and Notes Endpoints

## Objective
- Add authenticated API endpoints that let the frontend start a user-owned `ProcessStatus` without a file upload, create or update user notes for that process, and list all stored notes for the authenticated user.
- Introduce a parent-only `WRITTING` process state for manually started writing flows while keeping agent process states limited to `IN_PROGRESS`, `FAILED`, and `SUCCEEDED`.

## Background
- `labs/process_status/router.py` currently exposes read-only process endpoints under `/labs/processes`:
  - `GET /labs/processes/`
  - `GET /labs/processes/{process_id}/status`
- `labs/process_status/models.py` currently defines:
  - `ProcessStatusState = Literal["IN_PROGRESS", "FAILED", "SUCCEEDED"]`
  - `AgentProcessStatusState = ProcessStatusState`
- Because `AgentProcessStatusState` aliases `ProcessStatusState`, adding a parent process state today would also allow that state on agent records.
- `ProcessStatus` currently requires `file: str`; the new create endpoint has an empty body, so the implementation must support a process record that is not created from a file-backed workflow.
- There is no persisted model or read endpoint for user notes tied to a process status.

## Scope
### In Scope
- Add `WRITTING` to `ProcessStatusState`.
- Split `AgentProcessStatusState` from `ProcessStatusState` so agents keep exactly `IN_PROGRESS`, `FAILED`, and `SUCCEEDED`.
- Add a new persisted note model in `labs/process_status/models.py` with `process_status_id`, `description`, `created_at`, and `updated_at`.
- Add repository and service methods to create manual process statuses and create/update/list process status notes.
- Add `POST /labs/processes/create` with an empty body.
- Add `POST /labs/processes/notes?id=[optional]` with a JSON body containing `process_status_id` and `note`.
- Add `GET /labs/process/notes` to return all notes owned by the authenticated user.
- Return only the current stored note from the create/update note endpoint.
- Enforce authenticated user ownership for creating, updating, and listing notes.
- Update focused tests for models, repository, service, and router behavior.

### Out of Scope
- Starting LLM agent execution from the new `/create` endpoint.
- Changing existing agent process status transitions.
- Returning notes from `GET /labs/processes/{process_id}/status` unless needed by the implementation.
- Renaming `WRITTING` to `WRITING`; use the exact status value requested.
- Backfilling existing process status documents.
- Adding `user_id` directly to note documents; note ownership should be derived through the parent `ProcessStatus`.

## Proposed Approach
- In `labs/process_status/models.py`, define status aliases separately:

```python
ProcessStatusState = Literal["WRITTING", "IN_PROGRESS", "FAILED", "SUCCEEDED"]
AgentProcessStatusState = Literal["IN_PROGRESS", "FAILED", "SUCCEEDED"]
```

- Keep existing review/file workflows creating `ProcessStatus` with `IN_PROGRESS`.
- Add a manual creation path that creates `ProcessStatus` with `status="WRITTING"` for the authenticated user.
- Because `POST /create` has an empty body, make manual process creation independent from a submitted filename. The recommended implementation is to allow `ProcessStatus.file` to be `str | None = None` and update `ProcessStatusResponse.file` accordingly. Existing file-backed flows should continue sending a string.
- Add a new Beanie document in `labs/process_status/models.py`:

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

- Register `ProcessStatusNote` in `core/database/mongodb.py` Beanie initialization.
- Add schemas in `labs/process_status/schemas.py`:
  - `ProcessStatusNoteRequest` with `process_status_id: UUID` and `note: str`.
  - `ProcessStatusNoteResponse` with `id: UUID`, `process_status_id: UUID`, `description: str`, `created_at: datetime`, and `updated_at: datetime`.
- Store request `note` into model field `description`.
- Add repository methods in `labs/process_status/repository.py`:
  - `ProcessStatusRepository.create_writing(user_id: UUID) -> ProcessStatus`
  - `ProcessStatusNoteRepository.create(process_status_id: UUID, description: str) -> ProcessStatusNote`
  - `ProcessStatusNoteRepository.get_by_id(note_id: UUID) -> ProcessStatusNote | None`
  - `ProcessStatusNoteRepository.update(note: ProcessStatusNote, description: str) -> ProcessStatusNote`
  - `ProcessStatusNoteRepository.list_by_process_status_ids(process_status_ids: list[UUID]) -> list[ProcessStatusNote]`
- Add service methods in `labs/process_status/service.py`:
  - `create_writing_process_status(user_id: UUID) -> ProcessStatusResponse`
  - `create_or_update_note(user_id: UUID, request: ProcessStatusNoteRequest, note_id: UUID | None = None) -> ProcessStatusNoteResponse`
  - `list_notes(user_id: UUID) -> list[ProcessStatusNoteResponse]`
- Before creating or updating a note, fetch the related `ProcessStatus` by `process_status_id` and `user_id`. Return `404` from the router if the process does not belong to the authenticated user.
- If `id` is absent on `POST /labs/processes/notes`, create a new note.
- If `id` is present, fetch that note and update its `description`. Return `404` if the note does not exist or does not belong to a process owned by the authenticated user.
- On note update, refresh `updated_at` with `utc_now()` and preserve the original `created_at`.
- `POST /labs/processes/notes` must return only the stored note payload, not the parent `ProcessStatus`.
- For `GET /labs/process/notes`, list notes for processes owned by the authenticated user. Because notes do not store `user_id`, the service should first list or query the user's `ProcessStatus` records and then fetch notes whose `process_status_id` belongs to that set.
- Add the new write routes to the existing `/labs/processes` router:
  - `@router.post("/create", response_model=ProcessStatusResponse)`
  - `@router.post("/notes", response_model=ProcessStatusNoteResponse)`
- Add a read route for the requested singular path:
  - `GET /labs/process/notes`
  - Implement this route in the existing `labs/process_status/router.py` process status routing module. Do not create a dedicated `notes_router` or change router registration in `main.py`.

## Milestones
1. Update data contracts.
   - Split `ProcessStatusState` and `AgentProcessStatusState` in `labs/process_status/models.py`.
   - Add `WRITTING` to `ProcessStatusState` only.
   - Add `ProcessStatusNote` in `labs/process_status/models.py`.
   - Add `created_at` and `updated_at` fields to `ProcessStatusNote`.
   - Register `ProcessStatusNote` in MongoDB startup.
   - Add request/response schemas for notes.

2. Add persistence operations.
   - Add a manual `ProcessStatus` creation method that defaults status to `WRITTING`.
   - Add note create, read, update, and list methods.
   - Ensure note updates refresh `updated_at`.
   - Keep existing file-backed process creation behavior unchanged.

3. Add service behavior.
   - Add a service method for creating a writing process for the authenticated user.
   - Add a service method that creates or updates notes based on optional `id`.
   - Add a service method that returns all notes owned by the authenticated user.
   - Validate ownership through `ProcessStatusRepository.get_by_id`.

4. Add API endpoints.
   - Add `POST /labs/processes/create` with no request body.
   - Add `POST /labs/processes/notes?id=[optional]` with `process_status_id` and `note`.
   - Add `GET /labs/process/notes` to return all notes for the authenticated user.
   - Return `404` for missing or unauthorized process/note records.

5. Update tests.
   - Cover model status separation.
   - Cover manual process creation defaulting to `WRITTING`.
   - Cover note create/update/list persistence and user ownership checks.
   - Cover router behavior for all new endpoints.

## Edge Cases
- `POST /labs/processes/create` receives `{}` or no body: both should create a `WRITTING` process.
- `POST /labs/processes/notes` references a missing `process_status_id`: return `404`.
- `POST /labs/processes/notes?id=<uuid>` references a missing note: return `404`.
- A user attempts to add or update a note for another user's process: return `404`.
- `GET /labs/process/notes` is called by a user with no processes or notes: return `200` with an empty list.
- The note body contains an empty or whitespace-only string: reject with `422` by adding a minimum length validation on the schema.
- Existing code that derives aggregate process status should never return `WRITTING` from agent process data; it should still derive only `IN_PROGRESS`, `FAILED`, or `SUCCEEDED`.
- Multiple notes exist for the same process: `GET /labs/process/notes` should return all of them, ordered consistently by newest `updated_at` or `created_at`.

## Acceptance Criteria
- [ ] `ProcessStatusState` allows `WRITTING`, `IN_PROGRESS`, `FAILED`, and `SUCCEEDED`.
- [ ] `AgentProcessStatusState` allows only `IN_PROGRESS`, `FAILED`, and `SUCCEEDED`.
- [ ] Existing agent process schemas and service methods do not accept or emit `WRITTING`.
- [ ] `ProcessStatusNote` exists with `process_status_id`, `description`, `created_at`, and `updated_at` fields and uses a dedicated MongoDB collection.
- [ ] `POST /labs/processes/create` requires authentication and creates a user-owned process with `status="WRITTING"`.
- [ ] `POST /labs/processes/create` accepts an empty request body.
- [ ] `POST /labs/processes/notes` without `id` creates a note for the requested process.
- [ ] `POST /labs/processes/notes?id=<note_id>` updates the existing note description.
- [ ] `POST /labs/processes/notes` returns only the stored note payload.
- [ ] Note update preserves `created_at` and refreshes `updated_at`.
- [ ] `GET /labs/process/notes` requires authentication and returns all notes for the authenticated user.
- [ ] Notes cannot be created, updated, or listed for processes owned by another user.
- [ ] Existing process status list/status endpoints continue to work for file-backed processes.

## Test Plan
- Unit:
  - `tests/test_process_status_models.py`
    - Assert `ProcessStatusState` accepts `WRITTING`.
    - Assert agent process status test data remains limited to the original three values.
    - Assert `ProcessStatusNote` stores `process_status_id`, `description`, `created_at`, and `updated_at`.
  - `tests/test_process_status_repository.py`
    - Assert manual process creation persists `status="WRITTING"`.
    - Assert note create and update persist `description`.
    - Assert note update refreshes `updated_at`.
    - Assert notes can be listed by owned process ids.
  - `tests/test_process_status_service.py`
    - Assert creating a writing process delegates to the repository with the authenticated user.
    - Assert note creation checks process ownership.
    - Assert note update checks both note existence and process ownership.
    - Assert note listing only returns notes for the authenticated user's processes.

- Integration:
  - `tests/test_process_status_router.py`
    - Assert unauthenticated requests to all new endpoints return `401`.
    - Assert `POST /labs/processes/create` returns a process payload with `WRITTING`.
    - Assert `POST /labs/processes/notes` creates a note when `id` is absent and returns only the note payload.
    - Assert `POST /labs/processes/notes?id=<uuid>` updates a note when `id` is present and returns only the note payload.
    - Assert `GET /labs/process/notes` returns the authenticated user's notes.
    - Assert missing or unauthorized records return `404`.

- Manual verification:
  - Start the API with MongoDB configured.
  - Call `POST /labs/processes/create` with an auth token and no body; verify the response status is `WRITTING`.
  - Call `POST /labs/processes/notes` with the returned process id and a note; verify a note response is returned.
  - Call `POST /labs/processes/notes?id=<note_id>` with a different note value; verify `description` changes.
  - Call `GET /labs/process/notes` with the same auth token; verify the created note appears with `created_at` and `updated_at`.

## Risks and Mitigations
- Risk: Adding `WRITTING` to the shared state alias would allow invalid agent process states.
  - Mitigation: Define `ProcessStatusState` and `AgentProcessStatusState` separately and update imports/tests to enforce the split.

- Risk: Empty-body process creation conflicts with the current required `file` field.
  - Mitigation: Make `file` optional for manual process statuses while preserving existing file-backed workflow behavior.

- Risk: Notes could be updated across user boundaries if only note id is checked.
  - Mitigation: Resolve the note's `process_status_id` and verify the parent process belongs to the authenticated user before updating.

- Risk: Note listing could leak notes because notes do not store `user_id`.
  - Mitigation: Derive visibility from parent `ProcessStatus.user_id` and only query notes for process ids owned by the authenticated user.

- Risk: The misspelled `WRITTING` value may become a public API typo.
  - Mitigation: Treat `WRITTING` as the explicit API value for this spec and document any future spelling correction as a separate migration.

## Open Questions
- None.
