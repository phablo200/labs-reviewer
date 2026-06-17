from pathlib import Path
from uuid import UUID

from labs.tasks import celery_tasks
from labs.tasks.celery_tasks import process_markdown_job


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

    monkeypatch.setattr(celery_tasks, "init_mongodb", _init_mongodb)
    monkeypatch.setattr(celery_tasks, "close_mongodb", _close_mongodb)
    monkeypatch.setattr(
        celery_tasks,
        "build_markdown_processing_dependencies",
        lambda: _Dependencies(),
    )
    monkeypatch.setattr(
        celery_tasks.MarkdownHelper,
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
