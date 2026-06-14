# MongoDB And Process Setup Plan

## Source Spec

Implementation source of truth:

```text
docs/specs/mongodb-and-process-setup.md
```

This plan prepares MongoDB-backed process status infrastructure for the Labs workflow. It sets up package structure, configuration, persistence models, repository/service boundaries, and the protected status endpoint.

This plan must not implement agent workflow status updates. Existing agents, background task behavior, Markdown generation, PDF generation, and result-writing behavior stay unchanged until the next spec.

## Decisions To Preserve

- Use MongoDB for process status persistence.
- Use Beanie with PyMongo Async-compatible dependencies.
- Move Labs API/orchestration modules into `labs/agents`.
- Create process status infrastructure under `labs/process_status`.
- Use one MongoDB collection named `process_status`.
- Persist `AgentStatus.result`.
- Do not return `AgentStatus.result` from `GET /labs/processes/{process_id}/status`.
- Expose the status endpoint at `GET /labs/processes/{process_id}/status`.
- Defer agent status creation, status transitions, and result retrieval endpoint behavior to the next spec.
- Defer any separate `process_agents_status` collection decision.

## Phase 1: Dependency And Configuration

Files:

```text
requirements.txt
core/config.py
.env.example
```

Steps:

1. Add MongoDB dependencies:
   - Beanie.
   - PyMongo version that supports the async API.

2. Extend `Settings` in `core/config.py` with:

```text
MONGODB_URI
MONGODB_DATABASE
```

3. Use safe local defaults:

```text
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=labs_reviewer
```

4. Add the same variables to `.env.example` under a MongoDB section.

5. Keep MongoDB configuration separate from LLM and auth configuration.

Deliverable:

- Runtime configuration can resolve MongoDB connection settings without changing application behavior yet.

## Phase 2: Move Labs Orchestration Modules

Files to move:

```text
labs/contants.py -> labs/agents/contants.py
labs/router.py -> labs/agents/router.py
labs/service.py -> labs/agents/service.py
```

Files likely requiring import updates:

```text
main.py
labs/helpers/markdown_helper.py
tests/test_auth_routes.py
tests/test_outputs_pdf_endpoint.py
tests/test_outputs_router.py
tests/test_service.py
```

Steps:

1. Move the three requested files into `labs/agents`.
2. Add `labs/agents/__init__.py` if needed for package clarity.
3. Update imports from old paths:

```text
labs.router -> labs.agents.router
labs.service -> labs.agents.service
labs.contants -> labs.agents.contants
```

4. After moving `contants.py`, fix path resolution so public output paths still point to project root:

```text
public/markdown
public/pdf
```

5. Do not change route behavior or response shapes during this move.

Deliverable:

- Existing Labs routes and output listing behavior still work through the new `labs.agents.*` module paths.

## Phase 3: MongoDB Lifecycle Package

Files:

```text
core/database/__init__.py
core/database/mongodb.py
main.py
```

Steps:

1. Create `core/database`.
2. Implement MongoDB client ownership in `core/database/mongodb.py`.
3. Initialize Beanie with the `ProcessStatus` document model.
4. Expose startup and shutdown functions, for example:

```text
init_mongodb
close_mongodb
```

5. Wire MongoDB startup/shutdown through FastAPI lifespan in `main.py`.
6. Keep router registration behavior unchanged except for the updated `labs.agents.router` import.

Implementation constraints:

- Do not create process status records from `/labs/review` in this phase.
- Do not update background task behavior.
- Keep connection lifecycle isolated from process-status business logic.

Deliverable:

- App startup can initialize MongoDB and Beanie, and app shutdown closes the MongoDB client.

## Phase 4: Process Status Models

Files:

```text
labs/process_status/__init__.py
labs/process_status/models.py
```

Steps:

1. Create `labs/process_status`.
2. Define `AgentStatus`.
3. Define `ProcessStatus`.
4. Configure `ProcessStatus.Settings.name` as:

```text
process_status
```

5. Preserve the spec fields:

```python
class AgentStatus(BaseModel):
      id: UUID
      name: str
      status: Literal["IN_PROGRESS", "FAILED", "SUCCEEDED"]
      loop_from: int | None = None
      loop_to: int | None = None
      finished_at: datetime | None = None
      result: str | None = None
      children: list["AgentStatus"] = []
```

```python
class ProcessStatus(Document):
      id: UUID
      file: str
      created_at: datetime
      user_id: UUID
      data: list[AgentStatus]

      class Settings:
          name = "process_status"
```

6. Use implementation-safe defaults:
   - UUID default factories for ids.
   - UTC datetime default factory for `created_at`.
   - `Field(default_factory=list)` for child/status lists.

Deliverable:

- Beanie/Pydantic models can represent persisted process status, nested child agents, and internal agent results.

## Phase 5: Status Response Schemas

Recommended file:

```text
labs/process_status/schemas.py
```

Steps:

1. Add response models for the status endpoint.
2. Mirror the persisted status structure, but omit `result`.
3. Include nested children without `result`.
4. Keep `AgentStatus.result` available on persisted models only.

Recommended response model shape:

```text
ProcessStatusResponse
AgentStatusResponse
```

Fields to include:

```text
id
file
created_at
user_id
data
name
status
loop_from
loop_to
finished_at
children
```

Fields to exclude:

```text
result
```

Deliverable:

- The status endpoint can serialize process status without leaking stored agent results.

## Phase 6: Repository Layer

File:

```text
labs/process_status/repository.py
```

Steps:

1. Create `ProcessStatusRepository`.
2. Add direct persistence methods needed for setup:
   - Create a process status document.
   - Fetch a process status by `process_id` and `user_id`.
   - Save/replace a process status document.
3. Keep methods async.
4. Keep Beanie-specific query details inside the repository.

Implementation constraints:

- Do not encode workflow transition rules here.
- Do not call existing agents from this layer.
- Do not strip `result` here unless the method is explicitly for endpoint serialization.

Deliverable:

- Persistence operations are available without leaking Beanie query logic into routers or future workflow code.

## Phase 7: Service Layer

File:

```text
labs/process_status/service.py
```

Steps:

1. Create `ProcessStatusService`.
2. Use `ProcessStatusRepository` internally.
3. Add setup-focused methods:
   - Create process status.
   - Get process status for a user.
   - Convert persisted process status to a status response without `result`.
4. Keep service methods async.
5. Keep status transition behavior intentionally minimal.

Implementation constraints:

- Do not integrate with `LabPostService.enqueue_markdown_organization`.
- Do not mutate statuses from writer/reviewer/metadata/translator agents.
- Do not implement the future result endpoint.

Deliverable:

- Business-facing process status operations are available for the router and future workflow integration.

## Phase 8: Status Router

File:

```text
labs/process_status/router.py
```

Main endpoint:

```text
GET /labs/processes/{process_id}/status
```

Steps:

1. Create an `APIRouter` with prefix:

```text
/labs/processes
```

2. Protect the router with `get_current_user`.
3. Parse `process_id` as `UUID`.
4. Resolve the authenticated user id from `AuthenticatedUser`.
5. Use `ProcessStatusService` to fetch process status by process id and user id.
6. Return `404` when no matching process exists.
7. Return a response that excludes every `result` field.
8. Register the router in `main.py`.

Implementation constraints:

- Do not expose a result endpoint in this plan.
- Do not return process documents owned by a different user.

Deliverable:

- Authenticated clients can read process status metadata at the confirmed endpoint path.

## Phase 9: Tests

New or updated test files:

```text
tests/test_process_status_models.py
tests/test_process_status_service.py
tests/test_process_status_router.py
tests/test_service.py
tests/test_auth_routes.py
tests/test_outputs_router.py
tests/test_outputs_pdf_endpoint.py
```

Add focused tests for model behavior:

- `AgentStatus` supports nested children.
- `AgentStatus.result` is persisted on the model.
- Child lists do not share mutable defaults.
- `ProcessStatus` uses collection name `process_status`.
- `ProcessStatus` includes `file`.

Add focused tests for response serialization:

- Top-level agent `result` is excluded.
- Nested child agent `result` is excluded.
- Other status fields are preserved.

Add focused tests for repository/service behavior:

- Can create a process status document.
- Can fetch by `process_id` and `user_id`.
- Does not return another user's process.
- Can save/replace process status data.

Add route tests:

- Missing auth returns `401`.
- Valid auth and missing process returns `404`.
- Valid auth and owned process returns `200`.
- Valid auth and another user's process returns `404`.
- Response does not include any `result` key.

Add migration/import tests:

- Existing `/labs/review` tests still import the router from the new path.
- Existing `/outputs/makdown` and `/outputs/pdf` behavior is unchanged.
- Service initialization tests still pass after moving modules.

Deliverable:

- Tests prove setup behavior, endpoint protection, response shape, and import migration correctness without requiring agent workflow integration.

## Phase 10: Verification

Automated checks:

```bash
pytest
```

Recommended focused checks while developing:

```bash
pytest tests/test_process_status_models.py
pytest tests/test_process_status_service.py
pytest tests/test_process_status_router.py
pytest tests/test_service.py tests/test_auth_routes.py tests/test_outputs_router.py tests/test_outputs_pdf_endpoint.py
```

Manual checks:

1. Start MongoDB locally with the configured URI.
2. Start the FastAPI app.
3. Confirm startup initializes MongoDB and Beanie without import errors.
4. Call `GET /labs/processes/{process_id}/status` without auth and confirm `401`.
5. Seed or create a process document through the repository/service in a controlled test/dev path.
6. Call the status endpoint with valid auth and confirm:
   - status metadata is returned,
   - `result` is absent,
   - nested children are included,
   - another user's process is not returned.

## Execution Order

1. Add dependencies and MongoDB settings.
2. Move `labs/contants.py`, `labs/router.py`, and `labs/service.py` into `labs/agents`.
3. Update imports and path calculations.
4. Add MongoDB lifecycle package.
5. Add `labs/process_status` models.
6. Add status response schemas.
7. Add repository layer.
8. Add service layer.
9. Add process status router.
10. Register router and MongoDB lifespan in `main.py`.
11. Add/update tests.
12. Run focused tests.
13. Run full `pytest`.

## Rollback Strategy

If the setup causes startup or import regressions:

1. Temporarily unregister `labs.process_status.router` from `main.py`.
2. Temporarily disable MongoDB lifespan initialization.
3. Keep moved `labs.agents.*` imports only if tests pass.
4. If the module migration itself is the issue, move:

```text
labs/agents/contants.py -> labs/contants.py
labs/agents/router.py -> labs/router.py
labs/agents/service.py -> labs/service.py
```

5. Revert related import updates.

## Definition Of Done

- MongoDB settings are available in `core/config.py` and `.env.example`.
- Beanie/PyMongo dependencies are declared.
- MongoDB lifecycle is isolated under `core/database`.
- Labs orchestration modules live under `labs/agents`.
- `labs/process_status` contains models, schemas, repository, service, and router.
- `ProcessStatus` persists to `process_status`.
- `AgentStatus.result` exists in persistence models.
- `GET /labs/processes/{process_id}/status` is protected and user-scoped.
- Status responses exclude all `result` fields.
- Existing agents and background workflow behavior are unchanged.
- Targeted and full test suites pass.
