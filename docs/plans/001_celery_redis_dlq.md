# Celery Redis Dead Letter Queue Implementation Plan

Spec: `docs/specs/001_celery_redis_dlq.md`

## Objective

Implement an application-level Redis dead letter queue for Celery tasks so
permanently failed Markdown jobs are inspectable after all retries are
exhausted, while preserving the existing args-only dispatcher structure and the
current successful Markdown processing behavior.

## Current Baseline

- `core/tasks/celery_app.py` configures Celery from centralized settings.
- `core/tasks/celery_task_dispatcher.py` dispatches Celery tasks with
  `task.delay(*args)`.
- `core/tasks/background_task_dispatcher.py` and
  `core/tasks/celery_task_dispatcher.py` use args-only submission models.
- `labs/tasks/factory.py` sends `context`, `output_path`, and
  `process_status_id` as positional Celery args.
- `labs/tasks/celery_tasks.py` exposes `process_markdown_job(...)` with
  positional args and currently has no retry or DLQ behavior.
- `ProcessStatusService` can derive failed process state from failed
  `AgentProcessStatus` records, but it does not yet expose a direct
  `mark_process_failed(...)` method for task-level final failures.

## Implementation Steps

### 1. Add DLQ Configuration

Files:

- `core/tasks/constants.py`
- `core/config.py`
- `.env.example`

Tasks:

1. Add `CELERY_TASK_MAX_RETRIES = 3` to `core/tasks/constants.py`.
2. Add `CELERY_DLQ_ENABLED` and `CELERY_DLQ_KEY_PREFIX` settings to
   `core/config.py`.
3. Default `CELERY_DLQ_ENABLED` to true.
4. Default `CELERY_DLQ_KEY_PREFIX` to `dlq`.
5. Document both DLQ settings in `.env.example`.

Validation:

- `settings.CELERY_DLQ_ENABLED` and `settings.CELERY_DLQ_KEY_PREFIX` are
  available without requiring Redis at import time.
- Retry count is read from `core.tasks.constants.CELERY_TASK_MAX_RETRIES`, not
  from an environment variable.

### 2. Add Reusable Dead Letter Task Base

Files:

- `core/tasks/dead_letter.py`
- `tests/test_task_dead_letter.py`

Tasks:

1. Create `DeadLetterTask(Task)` with `abstract = True`.
2. Build Redis clients lazily from `settings.CELERY_BROKER_URL`.
3. Add a `dead_letter_key(task_name: str) -> str` helper using the configured
   prefix.
4. Add a payload builder that records:
   - `task_id`
   - `task_name`
   - sanitized `args`
   - `kwargs`
   - `error`
   - `exception_type`
   - `retries`
   - `max_retries`
   - `queue`
   - `failed_at`
5. Add a task-specific sanitization hook so subclasses can omit sensitive args.
6. Implement `on_failure(...)` so it writes to DLQ only when
   `self.request.retries >= self.max_retries`.
7. Call `on_final_failure(...)` after a successful or attempted DLQ write.
8. Log DLQ write errors without replacing the original task failure.

Validation:

- Unit tests can inject a fake Redis client.
- Importing `core/tasks/dead_letter.py` does not open a Redis connection.
- DLQ writes do not happen before the final retry.

### 3. Add Direct Process Failure Support

Files:

- `labs/process_status/service.py`
- `tests/test_process_status_service.py`

Tasks:

1. Add `ProcessStatusService.mark_process_failed(...)`.
2. Load the process by `process_status_id` with
   `ProcessStatusRepository.get_by_process_id(...)`.
3. Return `None` when the process does not exist.
4. Set `process_status.status = "FAILED"`.
5. Save through the existing repository `save(...)` method.

Validation:

- Existing process is saved as `FAILED`.
- Missing process returns `None`.
- Existing agent-process status derivation behavior remains unchanged.

### 4. Wire Markdown Task DLQ Behavior

Files:

- `labs/tasks/celery_tasks.py`
- `tests/test_celery_tasks.py`

Tasks:

1. Add `MarkdownDeadLetterTask(DeadLetterTask)`.
2. Make `process_markdown_job` a bound Celery task with:
   - `bind=True`
   - `base=MarkdownDeadLetterTask`
   - `autoretry_for=(Exception,)`
   - `retry_backoff=True`
   - `retry_kwargs={"max_retries": constants.CELERY_TASK_MAX_RETRIES}`
3. Keep positional args:
   - `context`
   - `output_path`
   - `process_status_id`
4. Add optional positional `simulate_failure: bool = False` for tests and
   manual verification.
5. In `MarkdownDeadLetterTask`, sanitize args so the DLQ entry omits full
   `context` and keeps only:
   - omitted-context marker
   - `output_path`
   - `process_status_id`
   - context length/hash metadata when available
6. In `on_final_failure(...)`, read `process_status_id` from the third task arg
   and call `ProcessStatusService.mark_process_failed(...)` through
   `anyio.run(...)`.

Validation:

- Existing successful task behavior still initializes MongoDB, runs
  `MarkdownHelper.process_and_save_markdown_with_status(...)`, closes MongoDB,
  and returns operational metadata.
- Simulated failure retries three times, then writes one DLQ record.
- Final failure marks the parent process as `FAILED`.

### 5. Preserve Args-Only Dispatcher Contract

Files:

- `labs/tasks/factory.py`
- `core/tasks/celery_task_dispatcher.py`
- `core/tasks/background_task_dispatcher.py`
- `tests/test_task_dispatchers.py`

Tasks:

1. Keep `BackgroundTaskSubmission` as `function` plus `args`.
2. Keep `CeleryTaskSubmission` as `task` plus `args`.
3. Keep `CeleryTaskDispatcher.enqueue(...)` calling `task.delay(*args)`.
4. Keep `MarkdownOrganizationTaskDispatcher` sending the current three
   positional Celery args.
5. Do not reintroduce task kwargs for the Markdown Celery path.

Validation:

- Existing dispatcher tests continue to assert args-only behavior.
- No task dispatch path depends on `CeleryTaskSubmission.kwargs`.

### 6. Manual Verification

Commands:

```bash
docker compose up --build api worker redis mongodb
```

Dispatch a simulated failure:

```bash
docker compose exec worker python -c "from labs.tasks.celery_tasks import process_markdown_job; process_markdown_job.delay('# Notes', 'public/markdown/dlq_test.md', '00000000-0000-0000-0000-000000000001', True)"
```

Watch worker logs:

```bash
docker compose logs -f worker
```

Inspect Redis DLQ:

```bash
docker compose exec redis redis-cli -n 0 LRANGE dlq:labs.process_markdown_job 0 -1
```

Expected result:

- Worker retries the simulated failure three times.
- Redis contains one DLQ entry.
- DLQ entry does not contain the full Markdown context.
- Related process status is marked `FAILED` when the process exists.

## Test Plan

Run focused tests:

```bash
PYTHONPATH=. pytest \
  tests/test_task_dead_letter.py \
  tests/test_celery_tasks.py \
  tests/test_process_status_service.py \
  tests/test_task_dispatchers.py
```

Run full suite:

```bash
PYTHONPATH=. pytest
```

## Acceptance Criteria

- [ ] Retry count is globally defined as
      `core.tasks.constants.CELERY_TASK_MAX_RETRIES = 3`.
- [ ] `labs.process_markdown_job` uses a DLQ-enabled bound task base.
- [ ] Failed Markdown jobs retry three times before dead-lettering.
- [ ] Final failure writes one Redis list item at
      `dlq:labs.process_markdown_job`.
- [ ] DLQ payload includes sanitized positional args and omits full `context`.
- [ ] Final failure marks the related `ProcessStatus` as `FAILED`.
- [ ] Successful Markdown task behavior and return payload remain unchanged.
- [ ] Dispatchers remain args-only.
- [ ] Public API contracts remain unchanged.

## Rollout Notes

- Deploy code with `CELERY_DLQ_ENABLED=true` and
  `CELERY_DLQ_KEY_PREFIX=dlq`.
- Keep `acks_late=False` for this version.
- Treat Redis DLQ data as operationally sensitive even though full Markdown
  context is omitted.
- Use `redis-cli` for first-version DLQ inspection and cleanup.

## Deferred Work

- DLQ list/replay/purge API.
- MongoDB-backed DLQ records for queryability and user ownership.
- Automatic replay.
- Per-task retry counts.
- Payload length caps and `LTRIM` cleanup policy.
