# Decouple Process Status Persistence From MongoDB

## Objective

Decouple `labs/process_status` from MongoDB/Beanie so process-status business logic depends on storage-neutral contracts instead of MongoDB document classes.

The implementation should keep the current API behavior and MongoDB as the default storage backend, while making MongoDB one strategy behind a repository interface. This should make future backends, such as in-memory, SQL, or remote service storage, possible without rewriting `ProcessStatusService`, response schemas, or workflow tracking code.

## Background

`core/auth` already uses a small strategy pattern:

- `core/auth/token_verifier.py` defines a `TokenVerifier` protocol.
- `core/auth/jwt_token_verifier.py` implements the JWT strategy.
- `core/auth/dependencies.py` chooses the implementation with `settings.AUTH_TOKEN_VERIFIER`.

`labs/process_status` has a repository layer, but it is still tightly coupled to MongoDB:

- `labs/process_status/models.py` defines `ProcessStatus` and `AgentProcessStatus` as Beanie `Document` subclasses.
- `labs/process_status/repository.py` directly constructs Beanie documents and calls Beanie query/save APIs.
- `labs/process_status/service.py` imports Beanie-backed models and exposes them in public method signatures.
- `labs/process_status/schemas.py`, `labs/process_status/proxy.py`, and `labs/helpers/markdown_helper.py` also import those models.
- `core/database/mongodb.py` initializes the process-status Beanie documents unconditionally during app startup.

The coupling has two layers:

- Persistence operations are coupled to Beanie/MongoDB.
- Domain objects are coupled to Beanie/MongoDB because the objects passed through business logic are database documents.

The current repository classes are useful test seams, but they are not true storage strategies because their inputs and outputs are Beanie `Document` objects. A different backend would need to fake Beanie behavior or force service-layer changes.

## Scope

### In Scope

- Add storage-neutral process-status domain entities.
- Introduce repository strategy protocols for process and agent-process persistence.
- Move Beanie document classes into a MongoDB-specific provider module.
- Convert the current repository implementation into a MongoDB strategy adapter.
- Add a factory that selects the process-status storage backend from configuration.
- Keep MongoDB as the default process-status backend.
- Update `ProcessStatusService`, schemas, proxy code, helper code, and package exports to depend on storage-neutral entities.
- Update MongoDB startup to initialize provider document classes only when MongoDB storage is configured.
- Add or update tests for entities, service behavior, MongoDB adapter mapping, repository factory behavior, routing, proxy tracking, and app startup configuration.
- Preserve the existing HTTP response shapes for:
  - `GET /labs/processes/{process_id}/status`
  - `GET /labs/agent-process/{agent_process_id}`

### Out of Scope

- Adding a production-ready non-MongoDB backend in this change.
- Migrating existing MongoDB data.
- Changing endpoint URLs, response field names, or auth behavior.
- Changing the workflow status state machine.
- Changing generated Markdown/PDF output behavior.
- Introducing transaction support across process and agent-process updates.
- Reworking unrelated database lifecycle code for features that do not use process status.

## Proposed Approach

### Resolved Decisions

- Use `typing.Protocol`, matching the `core/auth` strategy style.
- Keep MongoDB as the default backend with a new `PROCESS_STATUS_STORAGE=mongodb` setting.
- Use storage-neutral Pydantic entities for process status data.
- Move Beanie `Document` classes out of `labs/process_status/models.py` and into a MongoDB provider namespace.
- Keep the public API contract unchanged.
- Do not add a second backend in the first implementation. Add only the strategy boundary and MongoDB strategy.

### Target Module Shape

```text
labs/process_status/
  __init__.py
  entities.py
  factory.py
  proxy.py
  router.py
  schemas.py
  service.py
  storage.py
  providers/
    mongodb/
      __init__.py
      documents.py
      repository.py
```

Optional later refinement:

```text
labs/process_status/providers/mongodb/lifecycle.py
```

Use this only if MongoDB startup logic becomes large enough to move out of `core/database/mongodb.py`.

### Domain Entities

Create storage-neutral entities in `labs/process_status/entities.py`.

The entities should preserve the existing fields:

```python
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.utils.datetime import utc_now

ProcessStatusState = Literal["IN_PROGRESS", "FAILED", "SUCCEEDED"]
AgentProcessStatusState = ProcessStatusState


class ProcessStatus(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    file: str
    status: ProcessStatusState = "IN_PROGRESS"
    created_at: datetime = Field(default_factory=utc_now)
    user_id: UUID


class AgentProcessStatus(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    process_status_id: UUID
    parent_agent_process_status_id: UUID | None = None
    name: str
    status: AgentProcessStatusState = "IN_PROGRESS"
    loop_from: int | None = None
    loop_to: int | None = None
    finished_at: datetime | None = None
    result: str | None = None
```

`labs/process_status/models.py` should not remain the long-term import location for MongoDB documents. Either remove it after updating imports or turn it into a compatibility shim only if needed during migration. The final code should make new imports use `entities.py`.

### Repository Strategy Contracts

Create `labs/process_status/storage.py`.

It should define protocols and configuration errors:

```python
from datetime import datetime
from typing import Protocol
from uuid import UUID

from labs.process_status.entities import (
    AgentProcessStatus,
    AgentProcessStatusState,
    ProcessStatus,
)


class ProcessStatusStorageConfigurationError(Exception):
    """Raised when process-status storage cannot be configured."""


class ProcessStatusRepository(Protocol):
    async def create(self, *, file: str, user_id: UUID) -> ProcessStatus: ...
    async def get_by_process_id(self, process_id: UUID) -> ProcessStatus | None: ...
    async def get_by_id(self, *, process_id: UUID, user_id: UUID) -> ProcessStatus | None: ...
    async def update_status(
        self,
        *,
        process_id: UUID,
        status: ProcessStatusState,
    ) -> ProcessStatus | None: ...


class AgentProcessStatusRepository(Protocol):
    async def create(
        self,
        *,
        process_status_id: UUID,
        name: str,
        parent_agent_process_status_id: UUID | None = None,
        loop_from: int | None = None,
        loop_to: int | None = None,
        result: str | None = None,
    ) -> AgentProcessStatus: ...

    async def get_by_id(self, agent_process_id: UUID) -> AgentProcessStatus | None: ...
    async def list_by_process_status_id(self, process_status_id: UUID) -> list[AgentProcessStatus]: ...
    async def list_children(self, parent_agent_process_status_id: UUID) -> list[AgentProcessStatus]: ...
    async def update_status(
        self,
        *,
        agent_process_status_id: UUID,
        status: AgentProcessStatusState,
        finished_at: datetime | None = None,
        result: str | None = None,
    ) -> AgentProcessStatus | None: ...
```

Prefer explicit `update_status` methods over `save(process_status)`. This avoids passing mutable storage-shaped objects through the service and is easier for non-document backends to implement.

### MongoDB Provider

Move Beanie documents to `labs/process_status/providers/mongodb/documents.py`.

The document classes should keep the current collection names:

- `process_status`
- `agent_process_status`

The MongoDB repository implementation should live in `labs/process_status/providers/mongodb/repository.py`.

The adapter should:

- Implement `ProcessStatusRepository` and `AgentProcessStatusRepository`.
- Create Beanie documents internally.
- Query Beanie documents internally.
- Return `labs.process_status.entities` objects from all public methods.
- Accept only primitive identifiers and storage-neutral values in update methods.
- Contain mapper helpers such as `_process_status_from_document` and `_agent_process_status_from_document`.

The adapter must not return Beanie `Document` instances to the service layer.

### Factory And Configuration

Add this setting to `core/config.py`:

```python
PROCESS_STATUS_STORAGE: str = os.getenv("PROCESS_STATUS_STORAGE", "mongodb")
```

Add this env var to `.env.example`:

```text
PROCESS_STATUS_STORAGE=mongodb
```

Create `labs/process_status/factory.py`:

```python
from core.config import settings
from labs.process_status.providers.mongodb.repository import (
    MongoAgentProcessStatusRepository,
    MongoProcessStatusRepository,
)
from labs.process_status.storage import (
    AgentProcessStatusRepository,
    ProcessStatusRepository,
    ProcessStatusStorageConfigurationError,
)


def get_process_status_repositories() -> tuple[
    ProcessStatusRepository,
    AgentProcessStatusRepository,
]:
    if settings.PROCESS_STATUS_STORAGE == "mongodb":
        return MongoProcessStatusRepository(), MongoAgentProcessStatusRepository()

    raise ProcessStatusStorageConfigurationError(
        f"Unsupported PROCESS_STATUS_STORAGE: {settings.PROCESS_STATUS_STORAGE}."
    )
```

Update `ProcessStatusService.__init__` to default to this factory while preserving direct repository injection for tests:

```python
class ProcessStatusService:
    def __init__(
        self,
        repository: ProcessStatusRepository | None = None,
        agent_repository: AgentProcessStatusRepository | None = None,
    ) -> None:
        if repository is None or agent_repository is None:
            repository, agent_repository = get_process_status_repositories()

        self.repository = repository
        self.agent_repository = agent_repository
```

### Service Changes

Update `labs/process_status/service.py` to:

- Import entities from `labs.process_status.entities`.
- Import repository protocols from `labs.process_status.storage`.
- Stop importing the concrete MongoDB repository classes.
- Replace `_sync_process_status` mutation plus `save` with an explicit repository `update_status`.
- Continue building nested response data from agent process records.

Expected behavior should remain:

- No agent processes means parent process remains `IN_PROGRESS`.
- Any failed agent process makes the parent process `FAILED`.
- Any in-progress agent process keeps the parent process `IN_PROGRESS`.
- All succeeded agent processes make the parent process `SUCCEEDED`.
- Process lookup remains user-scoped for endpoint reads.

### Schema, Proxy, And Workflow Changes

Update imports in:

- `labs/process_status/schemas.py`
- `labs/process_status/proxy.py`
- `labs/helpers/markdown_helper.py`
- `labs/process_status/__init__.py`
- tests that construct process-status objects

These modules should depend on `labs.process_status.entities`, not Beanie documents.

`AgentInvocationProxy` should continue to pass the created `AgentProcessStatus` entity to the child proxy factory. Child callbacks may use the entity `id`, but must not rely on Beanie methods.

### MongoDB Startup

Update `core/database/mongodb.py` to initialize the MongoDB provider documents:

```python
from labs.process_status.providers.mongodb.documents import (
    AgentProcessStatusDocument,
    ProcessStatusDocument,
)
```

Then pass those document classes to `init_beanie`.

Update `main.py` lifespan so MongoDB is initialized only when configured:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.PROCESS_STATUS_STORAGE == "mongodb":
        await init_mongodb()
    yield
    if settings.PROCESS_STATUS_STORAGE == "mongodb":
        await close_mongodb()
```

This keeps current behavior for the default backend and allows future non-MongoDB strategies to start without requiring MongoDB.

### Compatibility

The implementation must preserve:

- Existing collection names.
- Existing persisted field names.
- Existing process status and agent process status values.
- Existing endpoint paths.
- Existing endpoint response shapes.
- Existing behavior of `/labs/review` returning a `process_id`.

No MongoDB data migration is required because the document field shape and collection names remain unchanged.

## Milestones

1. Add configuration and storage-neutral contracts.
   - Add `PROCESS_STATUS_STORAGE` to `core/config.py` and `.env.example`.
   - Add `labs/process_status/entities.py`.
   - Add `labs/process_status/storage.py`.
   - Add entity tests for defaults and field behavior.

2. Move MongoDB-specific code behind a provider.
   - Create `labs/process_status/providers/mongodb/`.
   - Move Beanie document definitions to `documents.py`.
   - Convert current repository behavior into `MongoProcessStatusRepository` and `MongoAgentProcessStatusRepository`.
   - Add mapper helpers and adapter tests.

3. Introduce repository factory and service decoupling.
   - Add `labs/process_status/factory.py`.
   - Update `ProcessStatusService` to use repository protocols and the factory.
   - Replace `save(process_status)` parent sync with explicit `update_status`.
   - Update service tests to use entity stubs and protocol-compatible repositories.

4. Update callers and response schemas.
   - Update schemas, proxy, helper code, routers, package exports, and tests to import entities.
   - Keep route behavior unchanged.
   - Keep `AgentInvocationProxy` behavior unchanged except repository method signatures.

5. Update app lifecycle and regression tests.
   - Update `core/database/mongodb.py` to register provider documents.
   - Guard startup/shutdown in `main.py` based on `PROCESS_STATUS_STORAGE`.
   - Add factory/config tests.
   - Run focused and full test suites.

## Edge Cases

- Unsupported `PROCESS_STATUS_STORAGE` should raise `ProcessStatusStorageConfigurationError` during service construction.
- If an agent process is updated but no parent process exists, `_sync_process_status` should return `None` without raising.
- If an agent process update target no longer exists, the repository should return `None`; the service should handle that defensively.
- If a process has no agent process records, derived status remains `IN_PROGRESS`.
- Child process tree construction must still handle arbitrary depth through `parent_agent_process_status_id`.
- Existing MongoDB records with UUID ids and current field names should still deserialize through the MongoDB provider documents.
- The router must still return `404` for process records that exist but belong to another user.
- Large agent results should still be truncated by `AgentInvocationProxy` before persistence.

## Acceptance Criteria

- [ ] `ProcessStatus` and `AgentProcessStatus` used by service, schemas, proxy, and helper code are storage-neutral entities, not Beanie `Document` subclasses.
- [ ] Beanie document classes live under `labs/process_status/providers/mongodb/`.
- [ ] `ProcessStatusService` imports repository protocols and the repository factory, not concrete MongoDB repository classes.
- [ ] MongoDB repositories return domain entities and do not leak Beanie documents to callers.
- [ ] `PROCESS_STATUS_STORAGE` defaults to `mongodb` and is documented in `.env.example`.
- [ ] Unsupported process-status storage configuration raises a clear configuration error.
- [ ] `core/database/mongodb.py` initializes the MongoDB provider documents, not domain entities.
- [ ] App startup initializes MongoDB only when `PROCESS_STATUS_STORAGE=mongodb`.
- [ ] Existing process-status endpoints keep the same response fields and status codes.
- [ ] `/labs/review` still creates a process record and returns a `process_id`.
- [ ] Agent invocation tracking still creates agent process records, stores results, truncates large results, and syncs parent process status.
- [ ] No generated files under `public/markdown` or `public/pdf` are required for this implementation.

## Test Plan

Unit:

- Entity tests for `ProcessStatus` and `AgentProcessStatus` defaults.
- Response schema tests using storage-neutral entities.
- Service tests using stub repositories that implement the new protocols.
- Status derivation tests for empty, succeeded, in-progress, and failed agent process lists.
- Proxy tests for successful invocation, failed invocation, large result truncation, and retry-without-result behavior.
- Factory tests for `PROCESS_STATUS_STORAGE=mongodb` and unsupported values.
- MongoDB adapter mapper tests that verify provider documents convert to domain entities.

Integration:

- Router tests for authenticated success and `404` behavior.
- Process status repository tests updated to target `MongoProcessStatusRepository` and `MongoAgentProcessStatusRepository`.
- App lifespan/config test verifying MongoDB initialization is skipped for non-Mongo storage once a non-Mongo test value is configured.

Manual verification:

- Start the API with default `.env` settings and confirm startup initializes MongoDB.
- Submit a `/labs/review` request and confirm the response includes `process_id`.
- Poll `GET /labs/processes/{process_id}/status` and confirm nested agent statuses render without `result` fields.
- Fetch `GET /labs/agent-process/{agent_process_id}` and confirm the detail response includes `result`.

Commands:

```bash
pytest tests/test_process_status_models.py \
  tests/test_process_status_repository.py \
  tests/test_process_status_service.py \
  tests/test_process_status_router.py \
  tests/test_agent_invocation_proxy.py
```

```bash
pytest
```

## Risks and Mitigations

- Risk: Beanie documents leak back into service or schema imports.
  - Mitigation: Use `rg "from labs.process_status.models|beanie|Document" labs/process_status labs/helpers tests` during review and keep Beanie imports limited to the MongoDB provider and MongoDB lifecycle.

- Risk: Moving `models.py` breaks existing imports.
  - Mitigation: Update imports in one migration pass and keep a temporary compatibility shim only if necessary. Prefer final imports from `entities.py`.

- Risk: Explicit `update_status` changes repository behavior compared with mutating objects and calling `save`.
  - Mitigation: Cover parent status sync and agent status updates with service and adapter tests.

- Risk: Startup guard accidentally skips MongoDB initialization for the default configuration.
  - Mitigation: Add tests for default `PROCESS_STATUS_STORAGE=mongodb` and manual startup verification.

- Risk: Existing tests assert Beanie collection names on domain models.
  - Mitigation: Move collection-name assertions to MongoDB provider document tests.

- Risk: Agent status update and parent process sync remain two separate writes.
  - Mitigation: Keep current behavior for this change and document transaction support as deferred work.

## Open Questions

- Should `labs/process_status/models.py` be deleted, or kept temporarily as a compatibility re-export of `entities.py`?
- Should the first implementation include an in-memory strategy for tests and local development, or should it only add the MongoDB strategy boundary?
- Should `ProcessStatusStorageConfigurationError` map to an HTTP `500` in routers if service construction fails at request time, or is startup-time failure acceptable?
- Should MongoDB provider lifecycle move into `labs/process_status/providers/mongodb/lifecycle.py` now, or wait until another MongoDB-backed feature needs a cleaner provider lifecycle boundary?
