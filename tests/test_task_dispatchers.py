from pathlib import Path
from uuid import UUID

import anyio
import pytest
from fastapi import BackgroundTasks

from core.tasks.background_task_dispatcher import (
    BackgroundTaskSubmission,
    BackgroundTasksDispatcher,
)
from core.tasks.celery_task_dispatcher import (
    CeleryTaskDispatcher,
    CeleryTaskSubmission,
)
from core.tasks.exceptions import TaskDispatchEnqueueError
from labs.helpers.markdown_helper import MarkdownHelper
from labs.tasks.factory import MarkdownOrganizationTaskDispatcher
from labs.tasks.markdown_jobs import MarkdownOrganizationJob


def test_background_tasks_dispatcher_adds_task() -> None:
    background_tasks = BackgroundTasks()
    dispatcher = BackgroundTasksDispatcher()

    async def _enqueue():
        await dispatcher.enqueue(
            background_task=BackgroundTaskSubmission(
                function=_example_task,
                args=("value",),
                kwargs={"enabled": True},
            ),
            background_tasks=background_tasks,
        )

    anyio.run(_enqueue)

    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is _example_task
    assert task.args == ("value",)
    assert task.kwargs == {"enabled": True}


def test_background_tasks_dispatcher_requires_background_tasks() -> None:
    dispatcher = BackgroundTasksDispatcher()

    async def _enqueue():
        await dispatcher.enqueue(
            background_task=BackgroundTaskSubmission(function=_example_task),
        )

    with pytest.raises(RuntimeError, match="BackgroundTasks is required"):
        anyio.run(_enqueue)


def test_celery_task_dispatcher_enqueues_serializable_payload() -> None:
    calls = []

    class _TaskStub:
        @staticmethod
        def delay(**kwargs):
            calls.append(kwargs)

    dispatcher = CeleryTaskDispatcher()

    async def _enqueue():
        await dispatcher.enqueue(
            celery_task=CeleryTaskSubmission(
                task=_TaskStub,
                kwargs={"value": "payload"},
            ),
            background_tasks=BackgroundTasks(),
        )

    anyio.run(_enqueue)

    assert calls == [{"value": "payload"}]


def test_celery_task_dispatcher_wraps_enqueue_failure() -> None:
    class _TaskStub:
        @staticmethod
        def delay(**_kwargs):
            raise RuntimeError("redis unavailable")

    dispatcher = CeleryTaskDispatcher()

    async def _enqueue():
        await dispatcher.enqueue(celery_task=CeleryTaskSubmission(task=_TaskStub))

    with pytest.raises(TaskDispatchEnqueueError):
        anyio.run(_enqueue)


def test_markdown_dispatcher_adapts_job_to_generic_dispatcher() -> None:
    background_tasks = BackgroundTasks()
    writer_agent = object()
    translator_agent = object()
    metadata_agent = object()
    process_status_service = object()
    task_dispatcher = _TaskDispatcherStub()
    dispatcher = MarkdownOrganizationTaskDispatcher(
        task_dispatcher=task_dispatcher,
        writer_agent=writer_agent,
        translator_agent=translator_agent,
        metadata_agent=metadata_agent,
        process_status_service=process_status_service,
    )

    async def _enqueue():
        await dispatcher.enqueue(job=_job(), background_tasks=background_tasks)

    anyio.run(_enqueue)

    call = task_dispatcher.calls[0]
    assert call["background_tasks"] is background_tasks
    assert call["background_task"].function is (
        MarkdownHelper.process_and_save_markdown_with_status
    )
    assert call["background_task"].args == (
        "# Notes",
        Path("public/markdown/example_reviewd.md"),
        writer_agent,
        translator_agent,
        metadata_agent,
        UUID("00000000-0000-0000-0000-000000000001"),
        process_status_service,
    )
    assert call["celery_task"].kwargs == {
        "context": "# Notes",
        "output_path": "public/markdown/example_reviewd.md",
        "process_status_id": "00000000-0000-0000-0000-000000000001",
    }


class _TaskDispatcherStub:
    def __init__(self) -> None:
        self.calls = []

    async def enqueue(self, **kwargs):
        self.calls.append(kwargs)


def _example_task(*_args, **_kwargs):
    return None


def _job() -> MarkdownOrganizationJob:
    return MarkdownOrganizationJob(
        context="# Notes",
        output_path=Path("public/markdown/example_reviewd.md"),
        process_status_id=UUID("00000000-0000-0000-0000-000000000001"),
    )
