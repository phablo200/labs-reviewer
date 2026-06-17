# Integrating Celery And Redis Plan

## Source Spec

Implementation source of truth:

```text
docs/specs/integrating-celery-and-redis.md
```

This plan adds a task dispatch Strategy boundary for the Markdown review
workflow, keeps FastAPI `BackgroundTasks` as the default, and adds Celery +
Redis as an opt-in execution backend.

## Decisions To Preserve

- Default execution remains `TASK_DISPATCHER=background_tasks`.
- Celery mode is selected with `TASK_DISPATCHER=celery`.
- `CELERY_RESULT_BACKEND` is required in Celery mode.
- Celery result data is operational tracking metadata only.
- Generated Markdown/PDF outputs and detailed process status remain outside
  Celery result storage.
- Failed Celery enqueue attempts return an API error before the client receives
  a `process_id`.
- Do not use `acks_late=True` in the first Celery implementation.
- Docker Compose must provide local `api`, `worker`, `redis`, and `mongodb`
  services.

## Phase 1: Configuration And Dependencies

Files:

```text
requirements.txt
core/config.py
.env.example
.env
```

Steps:

1. Add Celery and Redis client dependencies:

```text
celery>=5.4.0,<6.0.0
redis>=5.0.0,<6.0.0
```

2. Confirm `core/config.py` exposes:

```text
TASK_DISPATCHER
CELERY_BROKER_URL
CELERY_RESULT_BACKEND
```

3. Keep defaults:

```text
TASK_DISPATCHER=background_tasks
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

4. Confirm `.env.example` documents the same settings.
5. Keep local `.env` defaulted to `TASK_DISPATCHER=background_tasks`.

## Phase 2: Task Dispatch Contract

Files:

```text
labs/tasks/__init__.py
labs/tasks/markdown_jobs.py
```

Steps:

1. Create `labs/tasks/`.
2. Define `MarkdownOrganizationJob`:

```python
@dataclass(frozen=True)
class MarkdownOrganizationJob:
    context: str
    output_path: Path
    process_status_id: UUID
```

3. Define `MarkdownOrganizationDispatcher` as a `Protocol`.
4. Keep the dispatcher method narrow:

```python
async def enqueue(
    self,
    *,
    job: MarkdownOrganizationJob,
    background_tasks: BackgroundTasks | None = None,
) -> None:
    ...
```

Implementation note:

- `background_tasks` exists on the protocol only because the FastAPI strategy
  needs it. Celery should ignore it.

## Phase 3: FastAPI BackgroundTasks Strategy

Files:

```text
labs/tasks/fastapi_dispatcher.py
tests/test_task_dispatchers.py
```

Steps:

1. Implement `FastAPIBackgroundMarkdownDispatcher`.
2. Inject:

```text
writer_agent
translator_agent
metadata_agent
process_status_service
```

3. In `enqueue`, require `background_tasks`.
4. Schedule the current helper:

```python
MarkdownHelper.process_and_save_markdown_with_status
```

5. Pass the same arguments currently passed by `LabPostService`.
6. Raise a clear runtime error when `background_tasks` is missing.

Tests:

- Dispatcher adds `MarkdownHelper.process_and_save_markdown_with_status` to
  `BackgroundTasks`.
- Dispatcher passes context, output path, agents, `process_status_id`, and
  process status service.
- Dispatcher raises when `background_tasks` is `None`.

## Phase 4: Worker Dependency Builder

Files:

```text
labs/tasks/dependencies.py
labs/agents/service.py
tests/test_task_dependencies.py
```

Steps:

1. Move or duplicate the current agent construction from `LabPostService.__init__`
   into a reusable builder:

```python
def build_markdown_processing_dependencies() -> MarkdownProcessingDependencies:
    ...
```

2. The builder must construct:

```text
reviewer_agent
code_example_agent
writer_agent
translator_agent
metadata_agent
process_status_service
```

3. Attach `reviewer_agent` and `code_example_agent` to `writer_agent` exactly as
   the service does today.
4. Return a small dataclass with only the dependencies needed by the background
   job:

```text
writer_agent
translator_agent
metadata_agent
process_status_service
```

5. Update `LabPostService.__init__` to use the same builder where practical, so
   API and worker wiring do not drift.

Tests:

- Builder calls `LLMConfig.build_chat_model_for_agent` for reviewer,
  code-example, post-writer, metadata, and translator roles.
- Builder wires reviewer and code-example agents into the writer agent.
- Service initialization still wires the same role models.

## Phase 5: Celery App And Task

Files:

```text
labs/tasks/celery_app.py
labs/tasks/celery_tasks.py
tests/test_celery_tasks.py
```

Steps:

1. Create `celery_app` configured from `core.config.settings`.
2. Use Redis as broker and result backend:

```python
broker=settings.CELERY_BROKER_URL
backend=settings.CELERY_RESULT_BACKEND
```

3. Configure JSON serialization:

```python
task_serializer="json"
accept_content=["json"]
result_serializer="json"
task_ignore_result=False
task_store_errors_even_if_ignored=True
imports=("labs.tasks.celery_tasks",)
```

4. Implement `process_markdown_job`.
5. Accept only serializable arguments:

```text
context: str
output_path: str
process_status_id: str
```

6. Rebuild dependencies inside the task with
   `build_markdown_processing_dependencies()`.
7. Run `MarkdownHelper.process_and_save_markdown_with_status(...)` with
   `anyio.run(...)`.
8. Return operational metadata only:

```python
{
    "process_status_id": process_status_id,
    "output_path": output_path,
    "status": "completed",
}
```

9. Do not add `acks_late=True`.

Tests:

- Task calls the dependency builder.
- Task calls `MarkdownHelper.process_and_save_markdown_with_status`.
- Task converts `output_path` to `Path`.
- Task converts `process_status_id` to `UUID`.
- Task returns only operational metadata.
- Task decorator/config does not set `acks_late=True`.

## Phase 6: Celery Dispatcher And Factory

Files:

```text
labs/tasks/celery_dispatcher.py
labs/tasks/factory.py
tests/test_task_dispatchers.py
tests/test_task_dispatcher_factory.py
```

Steps:

1. Implement `CeleryMarkdownDispatcher`.
2. In `enqueue`, call:

```python
process_markdown_job.delay(
    context=job.context,
    output_path=str(job.output_path),
    process_status_id=str(job.process_status_id),
)
```

3. Ignore `background_tasks` in Celery mode.
4. Catch enqueue failures only if needed to normalize the error. Do not create a
   successful response when enqueue fails.
5. Implement `TaskDispatcherConfigurationError`.
6. Implement `build_markdown_dispatcher(...)`.
7. Select:

```text
background_tasks -> FastAPIBackgroundMarkdownDispatcher
celery -> CeleryMarkdownDispatcher
```

8. Validate `CELERY_RESULT_BACKEND` when `TASK_DISPATCHER=celery`.
9. Raise `TaskDispatcherConfigurationError` for unsupported dispatcher values.

Tests:

- Celery dispatcher calls `.delay(...)` with only strings and primitives.
- Celery dispatcher ignores `background_tasks`.
- Celery enqueue failure propagates or maps to a clear application error.
- Factory returns FastAPI strategy for `TASK_DISPATCHER=background_tasks`.
- Factory returns Celery strategy for `TASK_DISPATCHER=celery`.
- Factory requires `CELERY_RESULT_BACKEND` in Celery mode.
- Factory raises for unsupported dispatcher values.

## Phase 7: Refactor LabPostService

Files:

```text
labs/agents/service.py
tests/test_service.py
```

Steps:

1. Add a `markdown_dispatcher` dependency to `LabPostService`.
2. Build the dispatcher in `__init__` with `build_markdown_dispatcher(...)`.
3. Keep these responsibilities in `enqueue_markdown_organization(...)`:

```text
filename validation
output path construction
ProcessStatus creation
response construction
```

4. Replace direct `background_tasks.add_task(...)` usage with:

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

5. Ensure a Celery enqueue failure stops the request before returning a
   `process_id`.

Implementation note:

- The current method creates `ProcessStatus` before scheduling. If Celery
  enqueue fails after that record is created, the API must still return an error
  and not a successful response. A follow-up cleanup/failed-status policy can be
  added later if needed.

Tests:

- Service creates a process status before dispatching.
- Service delegates to `self.markdown_dispatcher.enqueue(...)`.
- Service no longer calls `background_tasks.add_task(...)` directly.
- Service keeps the existing response keys.
- Service preserves current output path naming.
- Service propagates or maps dispatcher enqueue errors to an API error.

## Phase 8: Docker Compose Local Stack

Files:

```text
docker-compose.yaml
Dockerfile
```

Steps:

1. Add root `docker-compose.yaml`.
2. Add `api` service:

```text
build: .
env_file: .env
ports: 3015:80
TASK_DISPATCHER=celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
MONGODB_URI=mongodb://mongodb:27017
MONGODB_DATABASE=labs_reviewer
```

3. Add `worker` service using the same image:

```bash
celery -A labs.tasks.celery_app.celery_app worker --loglevel=info
```

4. Add `redis` service with `redis:7-alpine`.
5. Add Redis healthcheck with `redis-cli ping`.
6. Add `mongodb` service with `mongo:7`.
7. Add persistent `mongodb_data` volume.
8. Make `api` and `worker` depend on Redis and MongoDB.

Implementation note:

- Do this after Celery modules and dependencies exist, because the worker
  command will fail before then.

Tests:

- Static check that Compose defines `api`, `worker`, `redis`, and `mongodb`.
- Static check that API and worker use `redis://redis:6379/0`,
  `redis://redis:6379/1`, and `mongodb://mongodb:27017`.

## Phase 9: Route And Integration Tests

Files:

```text
tests/test_service.py
tests/test_task_dispatchers.py
tests/test_task_dispatcher_factory.py
tests/test_celery_tasks.py
tests/test_docker_compose.py
```

Steps:

1. Keep existing service tests passing.
2. Add route or service-level coverage for `background_tasks` mode.
3. Add route or service-level coverage for `celery` mode with Celery enqueue
   mocked.
4. Add coverage for failed Celery enqueue before successful response.
5. Add coverage for output path naming and process status id propagation.

Required command:

```bash
PYTHONPATH=. pytest
```

If full suite setup is too expensive during development, run focused tests first:

```bash
PYTHONPATH=. pytest tests/test_service.py tests/test_task_dispatchers.py tests/test_task_dispatcher_factory.py tests/test_celery_tasks.py
```

## Phase 10: Manual Verification

### BackgroundTasks Mode

1. Set:

```text
TASK_DISPATCHER=background_tasks
```

2. Run:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 3015
```

3. Submit a Markdown file to `POST /labs/review`.
4. Confirm the API returns:

```text
message
process_id
output_file
```

5. Confirm Markdown/PDF output behavior is unchanged.

### Celery Mode Without Compose

1. Start Redis.
2. Set:

```text
TASK_DISPATCHER=celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

3. Run the API.
4. Run the worker:

```bash
celery -A labs.tasks.celery_app.celery_app worker --loglevel=info
```

5. Submit a Markdown file to `POST /labs/review`.
6. Confirm the API returns only after enqueue succeeds.
7. Confirm the worker processes the job.
8. Confirm MongoDB process status updates.
9. Confirm Celery stores operational task result metadata.

### Celery Mode With Compose

1. Run:

```bash
docker compose up --build api worker redis mongodb
```

2. Submit a Markdown file to `POST /labs/review`.
3. Confirm Redis-backed enqueueing.
4. Confirm worker execution.
5. Confirm MongoDB process status updates in the Compose MongoDB service.
6. Confirm Celery result storage contains only operational metadata.

## Implementation Order

1. Configuration and dependencies.
2. Task job contract.
3. FastAPI strategy.
4. Worker dependency builder.
5. Celery app/task.
6. Celery dispatcher/factory.
7. `LabPostService` refactor.
8. Docker Compose.
9. Tests.
10. Manual verification.

## Done Criteria

- `TASK_DISPATCHER=background_tasks` preserves current behavior.
- `TASK_DISPATCHER=celery` enqueues through Celery and Redis.
- `CELERY_RESULT_BACKEND` is required in Celery mode.
- Celery task results contain operational metadata only.
- Failed Celery enqueue does not return a successful `process_id` response.
- First Celery implementation does not use `acks_late=True`.
- `docker-compose.yaml` starts API, worker, Redis, and MongoDB.
- Existing and new tests pass.
