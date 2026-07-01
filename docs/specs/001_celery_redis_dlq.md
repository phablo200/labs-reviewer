# Celery Redis Dead Letter Queue

## Objective

Add an application-level dead letter queue for Celery tasks backed by Redis so
failed Labs processes can be inspected after Celery exhausts retries.

The first DLQ implementation must cover `labs.process_markdown_job`, preserve
the current successful Markdown processing flow, and prevent permanently failed
Celery jobs from leaving their `ProcessStatus` stuck in `IN_PROGRESS`.

## Background

The project uses Redis as the Celery broker and result backend:

- `core/tasks/celery_app.py` builds the Celery app from
  `settings.CELERY_BROKER_URL`, `settings.CELERY_RESULT_BACKEND`, and
  `settings.CELERY_TASK_MODULES`.
- `core/tasks/celery_task_dispatcher.py` enqueues Celery work by calling
  `task.delay(*args)`.
- `core/tasks/background_task_dispatcher.py` and
  `core/tasks/celery_task_dispatcher.py` both use args-only submission
  contracts. `BackgroundTaskSubmission` has `function` and `args`.
  `CeleryTaskSubmission` has `task` and `args`.
- `labs/tasks/factory.py` adapts `MarkdownOrganizationJob` into
  `process_markdown_job.delay(...)` with JSON-serializable positional args:
  `context`, `output_path`, and `process_status_id`. The adapter branches by
  configured dispatcher type and sends only the matching submission object.
- `labs/tasks/celery_tasks.py` defines `process_markdown_job` as a plain
  unbound Celery task that accepts positional arguments. It initializes MongoDB,
  builds worker-local dependencies, runs
  `MarkdownHelper.process_and_save_markdown_with_status(...)`, closes MongoDB,
  and returns operational metadata.
- `labs/process_status` already supports `FAILED` process and agent states, but
  the parent process status is derived from agent process records. If a Celery
  task fails before an agent record is created, or outside the agent proxy path,
  the parent process can remain `IN_PROGRESS`.

Redis does not provide RabbitMQ-style broker-native dead lettering for Celery.
With the Redis transport, the DLQ must be implemented at the application layer.
After Celery retries a task and the final attempt fails, the worker should write
a compact failed-task record to a Redis list such as:

```text
dlq:labs.process_markdown_job
```

The normal Redis queue key and the DLQ key have different meanings:

- `celery`: pending tasks waiting for workers.
- `dlq:labs.process_markdown_job`: failed tasks after max retries.

## Scope

### In Scope

- Add an application-level Redis DLQ for Celery tasks.
- Add a reusable Celery task base or helper in `core/tasks` for DLQ persistence.
- Configure `labs.process_markdown_job` to retry failed executions before
  dead-lettering.
- Write a failed task payload to Redis only after retries are exhausted.
- Include enough DLQ metadata to inspect and optionally replay the failed job.
- Mark the related `ProcessStatus` as `FAILED` when final task failure happens.
- Add a controlled failure simulation path for local/manual DLQ verification.
- Add unit tests for retry/DLQ payload construction and process-status failure
  updates.
- Document manual verification commands using Docker Compose and `redis-cli`.

### Out of Scope

- Broker-native DLQ support with RabbitMQ exchanges or routing keys.
- A DLQ replay endpoint or UI.
- Automatic DLQ replay.
- Moving DLQ records to MongoDB.
- Splitting each agent invocation into separate Celery tasks.
- Changing successful `/labs/review` response contracts.
- Changing Markdown/PDF output paths.
- Enabling `acks_late=True` as part of this change.

## Proposed Approach

Implement a reusable DLQ base task for Celery tasks that need retry and
dead-letter behavior.

Recommended files:

- `core/tasks/dead_letter.py`
- `core/tasks/celery_app.py`
- `core/tasks/constants.py`
- `core/config.py`
- `labs/tasks/celery_tasks.py`
- `labs/process_status/service.py`
- `labs/process_status/repository.py`
- `tests/test_celery_tasks.py`
- `tests/test_task_dead_letter.py`
- `.env.example`

### Configuration

Add DLQ settings in `core/config.py` and document them in `.env.example`:

```text
CELERY_DLQ_ENABLED=true
CELERY_DLQ_KEY_PREFIX=dlq
```

Add the shared retry count in `core/tasks/constants.py`:

```python
CELERY_TASK_MAX_RETRIES = 3
```

Default behavior:

- All Celery tasks that use the DLQ base retry exactly
  `core.tasks.constants.CELERY_TASK_MAX_RETRIES` times.
- `CELERY_DLQ_ENABLED` defaults to `true` when Celery mode is active.
- `CELERY_DLQ_KEY_PREFIX` defaults to `dlq`.
- The DLQ uses `CELERY_BROKER_URL`, which means the local Compose DLQ is stored
  in Redis database `0` beside the broker queue.

Retry count is intentionally not environment-configurable in the first version.
Use one global constant for all DLQ-enabled tasks.

### Resolved Decisions

- DLQ records must omit the full Markdown `context` by default. Redis DLQ
  entries should store metadata such as `process_status_id`, `output_path`,
  error, retry count, and context size/hash when useful. Replay must recover the
  original input from MongoDB, an uploaded file record, or another durable
  source once replay exists.
- The first version does not add API endpoints to list, replay, or purge DLQ
  records. Operators inspect and manage Redis DLQ entries with `redis-cli`.
- Redis is enough for the first version. MongoDB-backed DLQ records are deferred
  until DLQ inspection becomes product/admin functionality requiring richer
  queryability or user-level ownership.
- Use one global retry constant:
  `core.tasks.constants.CELERY_TASK_MAX_RETRIES = 3`.
- Keep task dispatch submissions args-only. DLQ-enabled Celery tasks must
  accept positional arguments so `CeleryTaskDispatcher` can continue calling
  `task.delay(*args)`.

### DLQ Record Contract

Persist one JSON object per permanently failed task using `LPUSH`.

Key:

```text
{CELERY_DLQ_KEY_PREFIX}:{task_name}
```

For the Markdown task:

```text
dlq:labs.process_markdown_job
```

Payload:

```json
{
  "task_id": "celery-task-id",
  "task_name": "labs.process_markdown_job",
  "args": [
    "[omitted-context]",
    "public/markdown/example_reviewd.md",
    "00000000-0000-0000-0000-000000000001"
  ],
  "kwargs": {},
  "context": {
    "omitted": true,
    "length": 12842,
    "sha256": "context-content-sha256"
  },
  "error": "RuntimeError: simulated failure",
  "exception_type": "RuntimeError",
  "retries": 3,
  "max_retries": 3,
  "queue": "celery",
  "failed_at": "2026-06-20T13:15:08Z"
}
```

Notes:

- Use `json.dumps(..., default=str)` so UUIDs, paths, and exceptions remain
  serializable.
- Keep the payload compact. Do not include tracebacks by default because they
  can be large. The worker log remains the primary traceback source.
- Do not persist the full Markdown `context` in Redis. Store a small context
  descriptor, such as `omitted`, `length`, and optional `sha256`, so operators
  can correlate records without leaking the full user payload.
- Sanitize positional task args before writing to Redis. For
  `labs.process_markdown_job`, replace the first positional arg, `context`, with
  an omission marker and retain the non-sensitive positional args:
  `output_path` and `process_status_id`.
- If replay is added later, it must use `process_status_id`, `output_path`, or a
  durable input record to recover the original content.

### Dead Letter Task Base

Create `core/tasks/dead_letter.py` with a reusable `DeadLetterTask`.

Responsibilities:

- Set `abstract = True`.
- Read max retries from `core.tasks.constants.CELERY_TASK_MAX_RETRIES`.
- Build a Redis client from `settings.CELERY_BROKER_URL`.
- On final failure, push the DLQ JSON payload to Redis.
- Log DLQ write failures without masking the original task failure.
- Delegate workflow-specific cleanup to overridable hooks.

Recommended shape:

```python
class DeadLetterTask(Task):
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        if self.request.retries >= self.max_retries:
            self.write_dead_letter(exc, task_id, args, kwargs)
            self.on_final_failure(exc, task_id, args, kwargs, einfo)
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_final_failure(self, exc, task_id, args, kwargs, einfo):
        return None
```

Implementation detail:

- `write_dead_letter(...)` should be separately testable without requiring a
  running worker.
- The Redis client factory should be injectable or monkeypatchable in tests.
- Avoid module-level Redis connections that are opened during import. Build the
  client lazily so importing tests does not require Redis.

### Markdown Task Retry and DLQ

Update `labs/tasks/celery_tasks.py` so `process_markdown_job` uses the DLQ base:

```python
@celery_app.task(
    bind=True,
    base=MarkdownDeadLetterTask,
    name="labs.process_markdown_job",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": constants.CELERY_TASK_MAX_RETRIES},
)
def process_markdown_job(self, context: str, output_path: str, process_status_id: str):
    ...
```

Create a Markdown-specific subclass in `labs/tasks/celery_tasks.py` or a small
helper module:

```python
class MarkdownDeadLetterTask(DeadLetterTask):
    def on_final_failure(self, exc, task_id, args, kwargs, einfo):
        mark_process_failed_from_task_args(args, exc)
```

Because Celery failure hooks are synchronous, the process-status update helper
must bridge to async code with `anyio.run(...)`, similar to the existing task
body.

`mark_process_failed_from_task_args(...)` should read `process_status_id` from
the third positional arg used by `process_markdown_job`. It should not depend on
Celery kwargs for the Markdown task.

### Process Status Failure Update

Add a service method to mark a process failed directly:

```python
async def mark_process_failed(
    self,
    *,
    process_status_id: UUID,
    result: str | None = None,
) -> ProcessStatus | None:
    ...
```

Repository support can reuse `save(...)`:

1. Load the process with `get_by_process_id(...)`.
2. Return `None` if missing.
3. Set `process_status.status = "FAILED"`.
4. Save and return it.

The DLQ final-failure hook should call this method when `process_status_id` is
present and valid in the task args. This handles failures that occur before any
`AgentProcessStatus` exists.

If agent processes already exist, the direct parent process update is still
acceptable because a permanently failed Celery task means the workflow failed
even if some agent records had succeeded.

### Simulated Failure

Add a controlled task-only simulation flag for manual verification:

```python
def process_markdown_job(
    self,
    context: str,
    output_path: str,
    process_status_id: str,
    simulate_failure: bool = False,
) -> dict[str, str]:
    if simulate_failure:
        raise RuntimeError("Simulated DLQ failure")
```

Do not expose `simulate_failure` through public HTTP request models in the first
implementation. Use it from tests or by manually dispatching the Celery task
inside the Compose network.

Update `labs/tasks/factory.py` only if the application needs an internal test
path that passes `simulate_failure`; otherwise the normal dispatcher should keep
sending the current three positional args.

## Failure Flow

Expected final behavior:

1. API enqueues `labs.process_markdown_job` through the existing dispatcher.
2. Worker receives the task.
3. The task fails.
4. Celery retries according to
   `core.tasks.constants.CELERY_TASK_MAX_RETRIES` and backoff settings.
5. On the final failure:
   - The worker writes one JSON payload to
     `dlq:labs.process_markdown_job`.
   - The worker marks the related `ProcessStatus` as `FAILED` when
     `process_status_id` is available.
   - Celery records the final task failure in the result backend.
6. Operators inspect the DLQ with Redis CLI.

## Milestones

1. Add configuration and DLQ base task.
   - Add `CELERY_TASK_MAX_RETRIES = 3` to `core/tasks/constants.py`.
   - Add DLQ settings to `core/config.py`.
   - Add `.env.example` documentation.
   - Add `core/tasks/dead_letter.py` with lazy Redis client creation and
     payload serialization.

2. Add process-status final failure support.
   - Add `ProcessStatusService.mark_process_failed(...)`.
   - Add focused tests in `tests/test_process_status_service.py`.

3. Wire `labs.process_markdown_job`.
   - Add `MarkdownDeadLetterTask`.
   - Make the task bound.
   - Enable `autoretry_for`, `retry_backoff`, and configured max retries.
   - Add the task-only `simulate_failure` kwarg.
   - Preserve the successful return payload.

4. Add tests for DLQ and Celery task behavior.
   - Unit test DLQ payload shape.
   - Unit test DLQ write occurs only when retries are exhausted.
   - Unit test final failure marks `ProcessStatus` as `FAILED`.
   - Update existing Celery task tests for the bound task signature.

5. Document manual verification.
   - Add commands to the spec or README after implementation.
   - Include Redis inspection commands for the Compose stack.

## Edge Cases

- Redis is unavailable during final failure:
  - The worker must log the DLQ write failure and still allow Celery to record
    the task failure.

- MongoDB is unavailable during final failure:
  - The DLQ record should still be written. The process may remain
    `IN_PROGRESS`, but the DLQ payload will include `process_status_id` for
    repair.

- Invalid `process_status_id`:
  - The task should still dead-letter. The failure-status update should log and
    skip the MongoDB update.

- Failure occurs after reviewed Markdown was written:
  - Preserve existing file behavior in `MarkdownHelper`. The process should
    still become `FAILED` if the Celery task ultimately fails.

- Failure occurs in metadata generation:
  - Existing behavior catches metadata failures and uses fallback metadata. That
    should not trigger retry or DLQ unless the broader task still raises.

- Large Markdown context:
  - The full `context` must be omitted from Redis DLQ records. Store only small
    metadata such as length and optional hash. Replay must use a durable input
    source outside the DLQ.

## Acceptance Criteria

- [ ] `labs.process_markdown_job` retries failures up to the configured max
      retry count.
- [ ] After the final failed retry, Redis contains exactly one DLQ entry at
      `dlq:labs.process_markdown_job`.
- [ ] The DLQ entry includes task id, task name, sanitized args, kwargs, error,
      exception type, retry count, max retries, queue, and failure timestamp.
- [ ] The DLQ entry does not include the full Markdown `context`.
- [ ] A task that succeeds does not write to the DLQ.
- [ ] A task that fails but still has retries remaining does not write to the
      DLQ.
- [ ] A permanently failed Markdown task marks the related `ProcessStatus` as
      `FAILED`.
- [ ] The current successful Markdown processing path still returns
      `process_status_id`, `output_path`, and `status: completed`.
- [ ] Public API response contracts remain unchanged.

## Test Plan

- Unit:
  - Test `DeadLetterTask` payload serialization with JSON-serializable and
    non-serializable values.
  - Test DLQ payload sanitization omits full `context` and preserves
    `process_status_id` plus `output_path` from positional args.
  - Test DLQ key construction from task name and prefix.
  - Test `on_failure(...)` writes only when `request.retries >= max_retries`.
  - Test Redis write failures are logged and do not replace the original
    exception.
  - Test `ProcessStatusService.mark_process_failed(...)` updates an existing
    process and returns `None` for a missing process.
  - Test `process_markdown_job` still calls MongoDB init/close and returns the
    existing success metadata.

- Integration:
  - Run the Celery task in eager mode or with a patched task request to verify
    final failure invokes DLQ and process-status update hooks.
  - Run existing dispatcher tests to confirm `labs/tasks/factory.py` keeps
    submitting the current serializable positional args.

- Manual verification:
  - Start the local stack:

    ```bash
    docker compose up --build api worker redis mongodb
    ```

  - Dispatch a simulated failure from inside the API or worker container:

    ```bash
    docker compose exec worker python -c "from labs.tasks.celery_tasks import process_markdown_job; process_markdown_job.delay('# Notes', 'public/markdown/dlq_test.md', '00000000-0000-0000-0000-000000000001', True)"
    ```

  - Watch retries and final failure:

    ```bash
    docker compose logs -f worker
    ```

  - Inspect the DLQ:

    ```bash
    docker compose exec redis redis-cli -n 0 LRANGE dlq:labs.process_markdown_job 0 -1
    ```

  - Confirm the related process status is `FAILED` in MongoDB or through:

    ```text
    GET /labs/processes/{process_id}/status
    ```

## Risks and Mitigations

- Risk: Replay is harder because Redis DLQ records omit full Markdown content.
  - Mitigation: Store enough metadata to identify the failed process, and add a
    durable input source before building replay.

- Risk: Redis list growth is unbounded.
  - Mitigation: Add an operational cleanup policy. A later implementation can
    add `CELERY_DLQ_MAX_LENGTH` and use `LTRIM` after `LPUSH`.

- Risk: Retrying non-idempotent work can duplicate output files or status
  records.
  - Mitigation: Keep `acks_late=False` for this implementation and add
    idempotency guards before enabling stronger delivery semantics.

- Risk: Final failure hook can fail while writing DLQ or updating MongoDB.
  - Mitigation: Isolate DLQ write and process-status update failures so one
    failure does not hide the other. Always log failures with `task_id` and
    `process_status_id`.

- Risk: `autoretry_for=(Exception,)` may retry errors that should fail fast.
  - Mitigation: Start with the Markdown job only and revisit exception-specific
    retry policy after observing real failures.

## Open Questions

- None for the first implementation. The previous questions are resolved in
  the decisions above.
