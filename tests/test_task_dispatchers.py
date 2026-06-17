from pathlib import Path
from uuid import UUID

import anyio
import pytest
from fastapi import BackgroundTasks

from labs.tasks.celery_dispatcher import CeleryMarkdownDispatcher
from labs.tasks.fastapi_dispatcher import FastAPIBackgroundMarkdownDispatcher
from labs.tasks.markdown_jobs import MarkdownOrganizationJob, TaskDispatchEnqueueError


def test_fastapi_dispatcher_adds_markdown_task() -> None:
    background_tasks = BackgroundTasks()
    job = _job()
    writer_agent = object()
    translator_agent = object()
    metadata_agent = object()
    process_status_service = object()
    dispatcher = FastAPIBackgroundMarkdownDispatcher(
        writer_agent=writer_agent,
        translator_agent=translator_agent,
        metadata_agent=metadata_agent,
        process_status_service=process_status_service,
    )

    async def _enqueue():
        await dispatcher.enqueue(job=job, background_tasks=background_tasks)

    anyio.run(_enqueue)

    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.args == (
        "# Notes",
        Path("public/markdown/example_reviewd.md"),
        writer_agent,
        translator_agent,
        metadata_agent,
        UUID("00000000-0000-0000-0000-000000000001"),
        process_status_service,
    )


def test_fastapi_dispatcher_requires_background_tasks() -> None:
    dispatcher = FastAPIBackgroundMarkdownDispatcher(
        writer_agent=object(),
        translator_agent=object(),
        metadata_agent=object(),
        process_status_service=object(),
    )

    async def _enqueue():
        await dispatcher.enqueue(job=_job())

    with pytest.raises(RuntimeError, match="BackgroundTasks is required"):
        anyio.run(_enqueue)


def test_celery_dispatcher_enqueues_serializable_payload(monkeypatch) -> None:
    calls = []

    class _TaskStub:
        @staticmethod
        def delay(**kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(
        "labs.tasks.celery_dispatcher.process_markdown_job",
        _TaskStub,
    )
    dispatcher = CeleryMarkdownDispatcher()

    async def _enqueue():
        await dispatcher.enqueue(job=_job(), background_tasks=BackgroundTasks())

    anyio.run(_enqueue)

    assert calls == [
        {
            "context": "# Notes",
            "output_path": "public/markdown/example_reviewd.md",
            "process_status_id": "00000000-0000-0000-0000-000000000001",
        }
    ]


def test_celery_dispatcher_wraps_enqueue_failure(monkeypatch) -> None:
    class _TaskStub:
        @staticmethod
        def delay(**_kwargs):
            raise RuntimeError("redis unavailable")

    monkeypatch.setattr(
        "labs.tasks.celery_dispatcher.process_markdown_job",
        _TaskStub,
    )
    dispatcher = CeleryMarkdownDispatcher()

    async def _enqueue():
        await dispatcher.enqueue(job=_job())

    with pytest.raises(TaskDispatchEnqueueError):
        anyio.run(_enqueue)


def _job() -> MarkdownOrganizationJob:
    return MarkdownOrganizationJob(
        context="# Notes",
        output_path=Path("public/markdown/example_reviewd.md"),
        process_status_id=UUID("00000000-0000-0000-0000-000000000001"),
    )
