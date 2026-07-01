# Process Status Review Endpoint Flow

## Objective
- Change the review workflow so users first create a `ProcessStatus`, add one or more note documents from uploaded `.md` or `.txt` files, then start agent processing for that existing process.
- Replace the current file-driven `/labs/review` behavior with `/labs/review/{process_status_id}`, where the review context is assembled from `ProcessStatusNote` records owned by the authenticated user.

## Background
- `labs/agents/router.py` currently exposes `POST /labs/review` and accepts one uploaded file. The endpoint reads the file bytes, decodes UTF-8 content, then calls `LabPostService.enqueue_markdown_organization`.
- `LabPostService.enqueue_markdown_organization` currently validates the uploaded filename, creates a new `ProcessStatus` through `ProcessStatusService.create_process_for_review`, builds a `MarkdownOrganizationJob`, and enqueues it.
- Manual process creation already exists in `labs/process_status/router.py` as `POST /labs/processes/create`, returning a user-owned `ProcessStatus`.
- Notes already exist as `ProcessStatusNote` documents with `process_status_id`, `description`, `created_at`, and `updated_at`.
- `ProcessStatusService.create_or_update_note` can create notes from JSON payloads, and `list_notes` can list all notes owned by a user, but there is no endpoint for uploading a note file and no service method for listing notes for one specific process.

## Scope
### In Scope
- Add an authenticated endpoint `POST /labs/files-note/{process_status_id}`.
- Accept exactly one uploaded file on the new note-file endpoint.
- Allow only `.md` and `.txt` filenames, case-insensitive.
- Decode the uploaded file as UTF-8 and store the raw text in a new `ProcessStatusNote.description`.
- Verify the target `ProcessStatus` exists and belongs to the authenticated user before creating the note.
- Change the review endpoint from `POST /labs/review` to `POST /labs/review/{process_status_id}`.
- Make the new review endpoint read all `ProcessStatusNote` rows for the specified process and authenticated user.
- Concatenate note descriptions into the `context` passed to `enqueue_markdown_organization`.
- Start the existing markdown organization dispatch flow after notes are gathered.
- Refactor service behavior so review uses the existing `ProcessStatus.id` instead of creating another process.
- Update tests and OpenAPI expectations for changed endpoint paths and payloads.

### Out of Scope
- Changing the `ProcessStatusNote` document fields or collection name.
- Supporting file encodings other than UTF-8.
- Supporting uploaded note file types other than `.md` and `.txt`.
- Removing the JSON note create/update endpoint at `POST /labs/processes/notes`.
- Changing the agent chain, Celery/dispatcher implementation, or markdown generation internals.
- Migrating existing notes or process-status documents.

## Proposed Approach
- Add a route in `labs/agents/router.py` or a closely related router module:
  - `POST /labs/files-note/{process_status_id}`
  - Request body: multipart form-data with `file: UploadFile`.
  - Response model: `ProcessStatusNoteResponse`.
- Validate uploaded note files before reading/storing:
  - Require a non-empty filename.
  - Accept suffixes `.md` and `.txt` only.
  - Return `400` for unsupported suffixes.
  - Decode as UTF-8 and return `400` for decode errors.
  - Reject empty files with a `422` validation error.
  - Reject files larger than `10 KiB` with a `422` validation error. This is the initial one-page markdown writing limit.
  - Store the decoded text exactly as received, without markdown transformation or trimming.
- Add a `ProcessStatusService.create_note_from_file` method, or equivalent, that:
  - Calls `ProcessStatusRepository.get_by_id(process_id=..., user_id=...)`.
  - Returns `None` when the process does not exist or is not owned by the user.
  - Calls `ProcessStatusNoteRepository.create(process_status_id=..., description=raw_text)`.
  - Returns `ProcessStatusNoteResponse`.
- Add repository/service support for listing notes by one process:
  - Prefer `ProcessStatusNoteRepository.list_by_process_status_id(process_status_id: UUID)`.
  - Keep the existing `list_by_process_status_ids` for the global user note list.
  - Sort notes deterministically by creation order for review context assembly. Recommendation: ascending `created_at`, then ascending `updated_at`, so the generated context follows the order notes were added.
- Change `labs/agents/router.py` review route:
  - Replace `@router.post("/review")` with `@router.post("/review/{process_status_id}")`.
  - Remove the uploaded file parameter from this endpoint.
  - Remove the old `/labs/review` route immediately; it should not remain as a deprecated compatibility endpoint.
  - Verify auth with the existing `get_current_user` dependency.
  - Pass `process_status_id` and `user_id` to the service.
- Refactor `LabPostService`:
  - Keep one internal method that builds and enqueues `MarkdownOrganizationJob`.
  - Add a path for existing processes, for example `enqueue_markdown_organization_for_process(background_tasks, process_status_id, user_id)`.
  - This method should verify the process belongs to the user, load its notes, join `note.description` values with `\n\n`, and enqueue the job with `process_status_id=process_status.id`.
  - It must not call `create_process_for_review`.
  - Return the same response shape as today: `message`, `process_id`, and `output_file`.
- Output filename recommendation:
  - Since `/review/{process_status_id}` no longer receives an uploaded filename, derive the output path from the existing process.
  - Use a stable sanitized base name from `ProcessStatus.file` when it is present and usable.
  - Fallback to `process_{process_status_id}.md`.
  - Always write generated markdown with a `.md` suffix under `PUBLIC_MARKDOWN_DIR`.

## Milestones
1. Add process-scoped note retrieval.
   - Update `labs/process_status/repository.py` with a single-process note listing method.
   - Update `labs/process_status/service.py` with a method that verifies process ownership and returns notes for one process.
   - Add repository/service tests for ownership and note ordering.

2. Add file-to-note creation.
   - Add `POST /labs/files-note/{process_status_id}`.
   - Validate filename extension, UTF-8 decoding, non-empty content, and the `10 KiB` one-page note size limit.
   - Store decoded content as a new `ProcessStatusNote`.
   - Add router/service tests for success, unsupported extension, invalid UTF-8, empty content, oversized content, missing process, and unauthorized access.

3. Refactor review enqueue flow.
   - Change `POST /labs/review` to `POST /labs/review/{process_status_id}`.
   - Add or refactor `LabPostService` methods so existing process ids are used.
   - Assemble the job context from process notes.
   - Ensure `enqueue_markdown_organization` no longer creates a new process for this review path.

4. Update tests and docs contracts.
   - Update auth route tests from `/labs/review` to `/labs/review/{process_status_id}`.
   - Update service tests to assert jobs use the existing process id and concatenated note context.
   - Update OpenAPI assertions if present.
   - Confirm full `pytest` passes.

## Edge Cases
- `process_status_id` is not a valid UUID: FastAPI should return `422`.
- The authenticated user does not own the process: return `404` to avoid leaking existence.
- The process exists but has no notes: return `400` with a clear message such as `Process status has no notes to review.`
- Uploaded note file has no filename: return `400`.
- Uploaded note file is `.md` or `.txt` but not valid UTF-8: return `400`.
- Uploaded note file is empty: return a `422` validation error.
- Uploaded note file is larger than `10 KiB`: return a `422` validation error.
- Multiple uploaded note files in one request: not supported; clients should call the endpoint once per file.
- Existing `/labs/processes/notes` JSON note behavior should continue to work.

## Acceptance Criteria
- [ ] `POST /labs/files-note/{process_status_id}` creates exactly one `ProcessStatusNote` for a valid `.md` upload.
- [ ] `POST /labs/files-note/{process_status_id}` creates exactly one `ProcessStatusNote` for a valid `.txt` upload.
- [ ] The stored `ProcessStatusNote.description` equals the uploaded file text content.
- [ ] Uploads with extensions other than `.md` or `.txt` return `400`.
- [ ] Invalid UTF-8 uploads return `400`.
- [ ] Empty `.md` and `.txt` uploads return `422`.
- [ ] `.md` and `.txt` uploads larger than `10 KiB` return `422`.
- [ ] Note-file uploads for a missing or non-owned process return `404`.
- [ ] `POST /labs/review/{process_status_id}` reads notes only for that process and authenticated user.
- [ ] `POST /labs/review/{process_status_id}` enqueues a `MarkdownOrganizationJob` using the existing `process_status_id`.
- [ ] `POST /labs/review/{process_status_id}` does not create a new `ProcessStatus`.
- [ ] The job context contains all note descriptions for the process in deterministic order joined with `\n\n`.
- [ ] `POST /labs/review` without a process id is removed and no longer documented as the supported review endpoint.
- [ ] Existing process status and note endpoints continue to pass their current tests.

## Test Plan
- Unit:
  - `ProcessStatusNoteRepository.list_by_process_status_id` returns only notes for the requested process id and applies deterministic sort.
  - `ProcessStatusService` returns `None` or equivalent not-found signal when a process is missing or user ownership does not match.
  - `ProcessStatusService` creates a note from raw uploaded content without trimming or transforming it.
  - Note file validation rejects empty content and content larger than `10 KiB` with `422`.
  - `LabPostService` assembles note descriptions into one `\n\n`-delimited context and enqueues a job with the existing process id.
  - `LabPostService` rejects an existing process with no notes.
- Integration:
  - Router test for `POST /labs/files-note/{process_status_id}` with `.md`.
  - Router test for `POST /labs/files-note/{process_status_id}` with `.txt`.
  - Router test for unsupported file extension.
  - Router test for invalid UTF-8.
  - Router test for empty file returning `422`.
  - Router test for oversized file returning `422`.
  - Router test for `POST /labs/review/{process_status_id}` enqueuing from stored notes.
  - Auth route tests confirm both new/changed endpoints require authorization.
- Manual verification:
  - Create a writing process with `POST /labs/processes/create`.
  - Upload two note files with `POST /labs/files-note/{process_id}`.
  - Start review with `POST /labs/review/{process_id}`.
  - Fetch `GET /labs/processes/{process_id}/status` and confirm agent process records are created for the same process id.

## Risks and Mitigations
- Risk: Existing clients still call `POST /labs/review` with an uploaded file.
  - Mitigation: Treat this as an intentional breaking API change in release notes. The old route is removed immediately and clients must call `/labs/review/{process_status_id}`.
- Risk: Notes are concatenated in an unexpected order, causing inconsistent agent output.
  - Mitigation: Define and test deterministic ordering in repository/service code.
- Risk: `ProcessStatus.file` may contain timestamp text or a value without a markdown suffix, so output file naming can become invalid.
  - Mitigation: Centralize output filename derivation and always force a `.md` suffix for generated markdown.
- Risk: Large uploaded note files can increase memory use because the endpoint reads the whole file.
  - Mitigation: Enforce the `10 KiB` one-page note limit before storing content.
- Risk: Returning `404` for non-owned processes can hide authorization detail from clients.
  - Mitigation: Use `404` consistently with existing process-status ownership checks to avoid leaking process ids.

## Open Questions
- None. Endpoint naming, empty file handling, route replacement, the one-page upload limit, and the context delimiter are resolved in this spec.
