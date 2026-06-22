from pathlib import Path
from uuid import UUID

import anyio

from core.tasks import constants
from labs.tasks import helpers
from labs.tasks.celery_tasks import MarkdownDeadLetterTask, process_markdown_job


def test_process_markdown_job_runs_helper_and_returns_operational_metadata(
    monkeypatch,
) -> None:
    calls = []

    class _Dependencies:
        writer_agent = object()
        translator_agent = object()
        metadata_agent = object()
        process_status_service = object()

    async def _init_mongodb():
        calls.append(("init",))

    async def _close_mongodb():
        calls.append(("close",))

    async def _process(
        context,
        output_path,
        writer_agent,
        translator_agent,
        metadata_agent,
        process_status_id,
        process_status_service,
    ):
        calls.append(
            (
                context,
                output_path,
                writer_agent,
                translator_agent,
                metadata_agent,
                process_status_id,
                process_status_service,
            )
        )

    monkeypatch.setattr(helpers, "init_mongodb", _init_mongodb)
    monkeypatch.setattr(helpers, "close_mongodb", _close_mongodb)
    monkeypatch.setattr(
        helpers,
        "build_markdown_processing_dependencies",
        lambda: _Dependencies(),
    )
    monkeypatch.setattr(
        helpers.MarkdownHelper,
        "process_and_save_markdown_with_status",
        _process,
    )

    result = process_markdown_job(
        context="# Notes",
        output_path="public/markdown/example_reviewd.md",
        process_status_id="00000000-0000-0000-0000-000000000001",
    )

    assert calls[0] == ("init",)
    assert calls[-1] == ("close",)
    assert calls[1] == (
        "# Notes",
        Path("public/markdown/example_reviewd.md"),
        _Dependencies.writer_agent,
        _Dependencies.translator_agent,
        _Dependencies.metadata_agent,
        UUID("00000000-0000-0000-0000-000000000001"),
        _Dependencies.process_status_service,
    )
    assert result == {
        "process_status_id": "00000000-0000-0000-0000-000000000001",
        "output_path": "public/markdown/example_reviewd.md",
        "status": "completed",
    }


def test_process_markdown_job_does_not_use_acks_late() -> None:
    assert not getattr(process_markdown_job, "acks_late", False)


def test_process_markdown_job_uses_configured_retries() -> None:
    assert process_markdown_job.max_retries == constants.CELERY_TASK_MAX_RETRIES
    assert process_markdown_job.retry_kwargs == {
        "max_retries": constants.CELERY_TASK_MAX_RETRIES
    }


def test_markdown_dead_letter_task_omits_context_from_payload() -> None:
    task = MarkdownDeadLetterTask()
    task.name = "labs.process_markdown_job"
    task._request_retries = lambda: 3
    task._request_queue = lambda: "celery"

    payload = task.build_dead_letter_payload(
        RuntimeError("boom"),
        "task-id",
        (
            "# Private notes",
            "public/markdown/example_reviewd.md",
            "00000000-0000-0000-0000-000000000001",
        ),
        {},
    )

    assert payload["args"] == [
        "[omitted-context]",
        "public/markdown/example_reviewd.md",
        "00000000-0000-0000-0000-000000000001",
    ]
    assert "# Private notes" not in str(payload)
    assert payload["context"]["omitted"] is True
    assert payload["context"]["length"] == len("# Private notes")
    assert payload["context"]["sha256"]


def test_mark_process_failed_from_task_args_marks_process_failed(monkeypatch) -> None:
    calls = []

    async def _init_mongodb():
        calls.append(("init",))

    async def _close_mongodb():
        calls.append(("close",))

    class _ProcessStatusServiceStub:
        async def mark_process_failed(self, *, process_status_id, result=None):
            calls.append((process_status_id, result))

    monkeypatch.setattr(helpers, "init_mongodb", _init_mongodb)
    monkeypatch.setattr(helpers, "close_mongodb", _close_mongodb)
    monkeypatch.setattr(helpers, "ProcessStatusService", _ProcessStatusServiceStub)

    anyio.run(
        helpers.mark_process_failed_from_task_args,
        (
            "# Notes",
            "public/markdown/example_reviewd.md",
            "00000000-0000-0000-0000-000000000001",
        ),
        {},
        RuntimeError("boom"),
    )

    assert calls == [
        ("init",),
        (
            UUID("00000000-0000-0000-0000-000000000001"),
            "RuntimeError: boom",
        ),
        ("close",),
    ]


def test_mark_process_failed_from_task_args_skips_invalid_process_id(monkeypatch) -> None:
    calls = []

    async def _init_mongodb():
        calls.append(("init",))

    monkeypatch.setattr(helpers, "init_mongodb", _init_mongodb)

    anyio.run(
        helpers.mark_process_failed_from_task_args,
        ("# Notes", "public/markdown/example_reviewd.md", "not-a-uuid"),
        {},
        RuntimeError("boom"),
    )

    assert calls == []
