# Integrating Celery And Redis With Strategy Pattern

## Objective

Add a background task dispatch strategy boundary so Labs Reviewer can run the
Markdown review workflow with either FastAPI `BackgroundTasks` or Celery workers
backed by Redis.

The current behavior must stay the default. A local or production environment
should keep working without Redis or a Celery worker unless it explicitly sets:

```text
TASK_DISPATCHER=celery
```

## Background

`POST /labs/review` is handled by `labs/agents/router.py` and delegates to
`LabPostService.enqueue_markdown_organization(...)` in `labs/agents/service.py`.

The current flow:

1. Validate the uploaded Markdown filename.
2. Create a `ProcessStatus` record for the authenticated user.
3. Build an output path under `public/markdown`.
4. Schedule `MarkdownHelper.process_and_save_markdown_with_status(...)` with
   FastAPI `BackgroundTasks`.
5. Return the current response contract:

```json
{
  "message": "Processing started.",
  "process_id": "UUID",
  "output_file": "public/markdown/example_reviewd.md"
}
```

FastAPI `BackgroundTasks` is simple and valid for the current release, but long
LLM workflows, PDF generation, and process restarts are tied to the API process
lifecycle. Celery + Redis should become an interchangeable execution strategy,
not a rewrite of the route or service workflow.

Inputs reviewed:

- `.workspace/reports/backgroundtask_definitions.md`
- `labs/agents/service.py`
- `labs/agents/router.py`
- `tests/test_service.py`
- `.env.example`
- `core/config.py`

The requested context file `content/_originals/scaling-a-python-backend.md` was
not present in the repository. No file with that name was found under the
workspace, so this spec is based on the available research note and current
code.

## Scope

### In Scope

- Add a Strategy Pattern task dispatch boundary for Markdown organization jobs.
- Keep FastAPI `BackgroundTasks` as the default task dispatch strategy.
- Add a Celery strategy that sends Markdown organization jobs through Redis.
- Add task dispatch settings to `.env.example`, local `.env`, and
  `core/config.py`.
- Add a dispatcher factory selected by `TASK_DISPATCHER`.
- Add Celery and Redis Python dependencies.
- Add a Celery app configured from `core.config.settings`.
- Add a Celery task for Markdown organization.
- Add a worker-side dependency builder so Celery workers construct their own
  agents and services.
- Update `LabPostService` to depend on the dispatcher contract.
- Keep `POST /labs/review` response shape unchanged.
- Add unit and integration tests for strategy selection and service delegation.
- Document how to run API, Redis, and Celery locally.

### Out of Scope

- Changing prompt behavior or agent orchestration order.
- Changing Markdown/PDF output locations.
- Changing process status endpoint contracts.
- Adding periodic jobs or Celery Beat.
- Adding a production Redis deployment manifest.
- Adding distributed tracing.
- Adding broad automatic Celery retries in the first implementation.
- Splitting each nested agent invocation into its own Celery task.

## Proposed Approach

Use the Strategy Pattern behind a narrow task dispatch port:

```text
LabPostService
  |
  | creates ProcessStatus and MarkdownOrganizationJob
  v
MarkdownOrganizationDispatcher
  |
  +--> FastAPIBackgroundMarkdownDispatcher
  |
  +--> CeleryMarkdownDispatcher
```

`LabPostService` remains responsible for request validation, process creation,
output path selection, and response shape. The dispatcher becomes responsible for
scheduling the work.

### Configuration

The selected task backend is controlled through environment variables:

```text
# Task dispatch
# Supported values: background_tasks, celery
TASK_DISPATCHER=background_tasks
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

`background_tasks` is the default because it preserves the current version.
`celery` requires Redis and a separate Celery worker.

`core/config.py` should expose:

```python
TASK_DISPATCHER: str = os.getenv("TASK_DISPATCHER", "background_tasks")
CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND: str = os.getenv(
    "CELERY_RESULT_BACKEND",
    "redis://localhost:6379/1",
)
```

### Target Modules

Add a new task dispatch package:

```text
labs/tasks/
  __init__.py
  celery_app.py
  celery_dispatcher.py
  celery_tasks.py
  dependencies.py
  factory.py
  fastapi_dispatcher.py
  markdown_jobs.py
```

### Job Contract

`labs/tasks/markdown_jobs.py` should define a serializable application job and a
dispatcher protocol:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from fastapi import BackgroundTasks


@dataclass(frozen=True)
class MarkdownOrganizationJob:
    context: str
    output_path: Path
    process_status_id: UUID


class MarkdownOrganizationDispatcher(Protocol):
    async def enqueue(
        self,
        *,
        job: MarkdownOrganizationJob,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        ...
```

The protocol accepts `BackgroundTasks | None` because the FastAPI strategy needs
that object. The Celery strategy should ignore it.

### FastAPI Strategy

`labs/tasks/fastapi_dispatcher.py` preserves current behavior:

```python
class FastAPIBackgroundMarkdownDispatcher:
    def __init__(
        self,
        *,
        writer_agent,
        translator_agent,
        metadata_agent,
        process_status_service,
    ) -> None:
        self.writer_agent = writer_agent
        self.translator_agent = translator_agent
        self.metadata_agent = metadata_agent
        self.process_status_service = process_status_service

    async def enqueue(
        self,
        *,
        job: MarkdownOrganizationJob,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        if background_tasks is None:
            raise RuntimeError("BackgroundTasks is required for background_tasks dispatch.")

        background_tasks.add_task(
            MarkdownHelper.process_and_save_markdown_with_status,
            job.context,
            job.output_path,
            self.writer_agent,
            self.translator_agent,
            self.metadata_agent,
            job.process_status_id,
            self.process_status_service,
        )
```

### Celery Strategy

`labs/tasks/celery_dispatcher.py` should pass only JSON-serializable values:

```python
class CeleryMarkdownDispatcher:
    async def enqueue(
        self,
        *,
        job: MarkdownOrganizationJob,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        process_markdown_job.delay(
            context=job.context,
            output_path=str(job.output_path),
            process_status_id=str(job.process_status_id),
        )
```

Do not pass agent instances, service instances, Beanie documents, database
clients, or `Path` objects through Celery.

### Celery App

`labs/tasks/celery_app.py` should configure Celery from centralized settings:

```python
from celery import Celery

from core.config import settings

celery_app = Celery(
    "labs_reviewer",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    imports=("labs.tasks.celery_tasks",),
)
```

### Worker Dependencies

`labs/tasks/dependencies.py` should build dependencies inside the Celery worker
process:

```python
@dataclass(frozen=True)
class MarkdownProcessingDependencies:
    writer_agent: LabPostWriterAgent
    translator_agent: LabPostTranslatorAgent
    metadata_agent: LabPostMetadataAgent
    process_status_service: ProcessStatusService


def build_markdown_processing_dependencies() -> MarkdownProcessingDependencies:
    ...
```

This builder should mirror the current `LabPostService.__init__` wiring:

- reviewer LLM
- code-example LLM
- writer LLM
- metadata LLM
- translator LLM
- writer agent with reviewer and code-example agents attached
- process status service

### Celery Task

`labs/tasks/celery_tasks.py` should run the existing async helper from a
synchronous Celery task:

```python
from pathlib import Path
from uuid import UUID

import anyio

from labs.helpers.markdown_helper import MarkdownHelper
from labs.tasks.celery_app import celery_app
from labs.tasks.dependencies import build_markdown_processing_dependencies


@celery_app.task(name="labs.process_markdown_job")
def process_markdown_job(
    *,
    context: str,
    output_path: str,
    process_status_id: str,
) -> None:
    dependencies = build_markdown_processing_dependencies()
    anyio.run(
        MarkdownHelper.process_and_save_markdown_with_status,
        context,
        Path(output_path),
        dependencies.writer_agent,
        dependencies.translator_agent,
        dependencies.metadata_agent,
        UUID(process_status_id),
        dependencies.process_status_service,
    )
```

### Dispatcher Factory

`labs/tasks/factory.py` should select the active strategy:

```python
class TaskDispatcherConfigurationError(Exception):
    """Raised when task dispatch configuration is invalid."""


def build_markdown_dispatcher(
    *,
    writer_agent,
    translator_agent,
    metadata_agent,
    process_status_service,
) -> MarkdownOrganizationDispatcher:
    dispatcher = settings.TASK_DISPATCHER.strip().lower()

    if dispatcher == "background_tasks":
        return FastAPIBackgroundMarkdownDispatcher(
            writer_agent=writer_agent,
            translator_agent=translator_agent,
            metadata_agent=metadata_agent,
            process_status_service=process_status_service,
        )

    if dispatcher == "celery":
        return CeleryMarkdownDispatcher()

    raise TaskDispatcherConfigurationError(
        f"Unsupported TASK_DISPATCHER: {settings.TASK_DISPATCHER}."
    )
```

### Service Changes

`LabPostService.__init__` should build the dispatcher after agents and
`ProcessStatusService` are initialized:

```python
self.markdown_dispatcher = build_markdown_dispatcher(
    writer_agent=self.writer_agent,
    translator_agent=self.translator_agent,
    metadata_agent=self.metadata_agent,
    process_status_service=self.process_status_service,
)
```

`enqueue_markdown_organization(...)` should create the job and delegate
scheduling:

```python
job = MarkdownOrganizationJob(
    context=context,
    output_path=output_path,
    process_status_id=process_status.id,
)

await self.markdown_dispatcher.enqueue(
    job=job,
    background_tasks=background_tasks,
)
```

The route can keep accepting `BackgroundTasks` in both modes. This keeps the
router stable while the dispatcher decides whether the object is used.

### Dependencies

Add to `requirements.txt`:

```text
celery>=5.4.0,<6.0.0
redis>=5.0.0,<6.0.0
```

Application code should not call Redis directly in this milestone. Redis is the
Celery broker and optional result backend.

### Runtime Commands

Current mode:

```bash
TASK_DISPATCHER=background_tasks uvicorn main:app --reload --host 0.0.0.0 --port 3015
```

Celery mode:

```bash
redis-server
TASK_DISPATCHER=celery uvicorn main:app --reload --host 0.0.0.0 --port 3015
celery -A labs.tasks.celery_app.celery_app worker --loglevel=info
```

## Milestones

1. Add configuration.
   - Update `.env.example` and local `.env` with `TASK_DISPATCHER`,
     `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND`.
   - Update `core/config.py` with matching settings and defaults.

2. Add the strategy boundary.
   - Create `labs/tasks/markdown_jobs.py`.
   - Create `labs/tasks/fastapi_dispatcher.py`.
   - Add tests proving FastAPI dispatch still schedules the same helper.

3. Refactor service delegation.
   - Update `LabPostService` to build and use a dispatcher.
   - Keep filename validation, process status creation, output path generation,
     and response shape in the service.
   - Update existing service tests to assert dispatcher delegation.

4. Add Celery infrastructure.
   - Add Celery and Redis dependencies to `requirements.txt`.
   - Create `labs/tasks/celery_app.py`.
   - Create `labs/tasks/dependencies.py`.
   - Create `labs/tasks/celery_tasks.py`.
   - Create `labs/tasks/celery_dispatcher.py`.

5. Add factory selection.
   - Create `labs/tasks/factory.py`.
   - Support `background_tasks` and `celery`.
   - Raise a configuration error for unsupported values.

6. Validate both modes.
   - Run unit and integration tests.
   - Manually verify `TASK_DISPATCHER=background_tasks`.
   - Manually verify `TASK_DISPATCHER=celery` with Redis and a worker.

## Edge Cases

- Missing `TASK_DISPATCHER` should use `background_tasks`.
- Unsupported `TASK_DISPATCHER` should fail with a clear configuration error.
- FastAPI strategy without `BackgroundTasks` should fail with a clear runtime
  error.
- Celery strategy should ignore `BackgroundTasks`.
- Celery payload must stay JSON-serializable.
- Invalid `process_status_id` in a Celery task should fail the task instead of
  creating a new process.
- Redis unavailable in `celery` mode should fail enqueueing visibly.
- Worker process must initialize the same environment variables as the API.
- Existing output path behavior, including the current `_reviewd.md` suffix,
  should not change in this implementation.

## Acceptance Criteria

- [ ] With no task environment variables set, the app uses FastAPI
      `BackgroundTasks`.
- [ ] `TASK_DISPATCHER=background_tasks` preserves the current `/labs/review`
      response contract.
- [ ] `TASK_DISPATCHER=celery` enqueues the same Markdown processing job to
      Celery.
- [ ] `ProcessStatus` creation remains in the API service before enqueueing.
- [ ] Celery task arguments are strings or other JSON-serializable primitives.
- [ ] Celery worker constructs its own agents and process status service.
- [ ] `LabPostService` no longer calls `background_tasks.add_task(...)`
      directly.
- [ ] Unsupported dispatcher values produce a clear configuration error.
- [ ] `.env.example` documents the task dispatch settings.
- [ ] Local `.env` defaults to `TASK_DISPATCHER=background_tasks`.
- [ ] Existing service tests pass.
- [ ] New tests cover dispatcher strategies, factory selection, and service
      delegation.

## Test Plan

Unit:

- `FastAPIBackgroundMarkdownDispatcher` adds
  `MarkdownHelper.process_and_save_markdown_with_status` to `BackgroundTasks`.
- `FastAPIBackgroundMarkdownDispatcher` raises when `background_tasks` is
  missing.
- `CeleryMarkdownDispatcher` calls `process_markdown_job.delay(...)` with
  `context`, string `output_path`, and string `process_status_id`.
- `build_markdown_dispatcher(...)` returns the FastAPI strategy for
  `TASK_DISPATCHER=background_tasks`.
- `build_markdown_dispatcher(...)` returns the Celery strategy for
  `TASK_DISPATCHER=celery`.
- `build_markdown_dispatcher(...)` raises for unsupported values.
- `LabPostService.enqueue_markdown_organization(...)` creates process status and
  delegates to `self.markdown_dispatcher.enqueue(...)`.

Integration:

- `POST /labs/review` returns the same response in `background_tasks` mode.
- `POST /labs/review` returns the same response in `celery` mode with Celery
  enqueue mocked.
- Process status id is passed to both dispatch strategies unchanged.
- Output path generation remains unchanged.

Manual verification:

- Run the API with `TASK_DISPATCHER=background_tasks`, submit a Markdown file,
  and confirm generated Markdown/PDF output still works.
- Start Redis, run the API with `TASK_DISPATCHER=celery`, start a Celery worker,
  submit a Markdown file, and confirm the worker updates the same process status
  and writes the expected output files.

## Risks and Mitigations

- Risk: Celery workers may not share the same environment as the API.
  - Mitigation: document required environment variables and build worker
    dependencies from `core.config.settings`.

- Risk: Passing live Python objects through Celery would fail serialization or
  create hidden process coupling.
  - Mitigation: keep Celery task arguments limited to `str` values and rebuild
    dependencies inside the worker.

- Risk: Automatic retries could duplicate LLM cost or overwrite output files.
  - Mitigation: defer broad retry policy until the job is confirmed idempotent.

- Risk: Redis outage in Celery mode prevents work from being enqueued.
  - Mitigation: fail visibly at enqueue time and keep `background_tasks` as the
    default for environments without Redis.

- Risk: Duplicating agent construction between API and worker can drift.
  - Mitigation: move shared construction into
    `build_markdown_processing_dependencies()` and reuse it where possible.

## Open Questions

- Should `CELERY_RESULT_BACKEND` be required, or can production disable result
  storage if process status remains the source of truth? Even with our MongoDB, I feel that to keep robustness and well architecture it MUST be required to save the result, so implement saving the results, just for good architecture.
- Should failed Celery enqueue attempts mark the existing `ProcessStatus` as
  `FAILED`, or should the API return an error before the client receives a
  `process_id`? It should return an error before the client receives `process_id`, I understood that this is a prior step, and should be stopped before moving foward.
- Should the first Celery implementation use `acks_late=True`, or should that
  wait until output writes and LLM calls are made idempotent?
- Should the local development stack add Redis to Docker Compose in the same
  implementation milestone? Yes, read our `Dockerfile` and create the services related using docker compose, this will make easier start our necessary services.
