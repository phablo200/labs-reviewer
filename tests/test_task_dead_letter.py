import json

from core.config import settings
from core.tasks.dead_letter import DeadLetterTask


class _RedisStub:
    def __init__(self) -> None:
        self.calls = []

    def lpush(self, key, value):
        self.calls.append((key, value))


class _DeadLetterTask(DeadLetterTask):
    name = "example.task"


def test_dead_letter_task_writes_serialized_payload(monkeypatch) -> None:
    redis = _RedisStub()
    task = _DeadLetterTask()
    task._request_retries = lambda: 3
    task._request_queue = lambda: "celery"
    task._build_redis_client = lambda: redis
    monkeypatch.setattr(settings, "CELERY_DLQ_KEY_PREFIX", "dlq")

    task.write_dead_letter(
        RuntimeError("boom"),
        "task-id",
        ("value",),
        {"path": object()},
    )

    assert redis.calls[0][0] == "dlq:example.task"
    payload = json.loads(redis.calls[0][1])
    assert payload["task_id"] == "task-id"
    assert payload["task_name"] == "example.task"
    assert payload["args"] == ["value"]
    assert payload["kwargs"]["path"].startswith("<object object at")
    assert payload["error"] == "RuntimeError: boom"
    assert payload["exception_type"] == "RuntimeError"
    assert payload["retries"] == 3
    assert payload["max_retries"] == 3
    assert payload["queue"] == "celery"
    assert payload["failed_at"].endswith("Z")


def test_dead_letter_task_does_not_write_before_final_failure(monkeypatch) -> None:
    task = _DeadLetterTask()
    calls = []
    task._is_final_failure = lambda: False
    task.write_dead_letter = lambda *_args: calls.append("dlq")
    task.on_final_failure = lambda *_args: calls.append("final")
    monkeypatch.setattr(settings, "CELERY_DLQ_ENABLED", True)

    task.on_failure(RuntimeError("boom"), "task-id", (), {}, None)

    assert calls == []


def test_dead_letter_task_runs_final_hook_after_dlq_write_failure(monkeypatch) -> None:
    task = _DeadLetterTask()
    calls = []
    task._is_final_failure = lambda: True

    def _write(*_args):
        calls.append("dlq")
        raise RuntimeError("redis down")

    task.write_dead_letter = _write
    task.on_final_failure = lambda *_args: calls.append("final")
    monkeypatch.setattr(settings, "CELERY_DLQ_ENABLED", True)

    task.on_failure(RuntimeError("boom"), "task-id", (), {}, None)

    assert calls == ["dlq", "final"]
