import pytest

from core.tasks.background_task_dispatcher import BackgroundTasksDispatcher
from core.tasks.celery_task_dispatcher import CeleryTaskDispatcher
from core.tasks.task_dispatcher import (
    build_task_dispatcher,
)
from core.tasks.exceptions import TaskDispatcherConfigurationError
from labs.tasks.factory import (
    MarkdownOrganizationTaskDispatcher,
    build_markdown_dispatcher,
)


def test_build_task_dispatcher_returns_fastapi_strategy(monkeypatch) -> None:
    monkeypatch.setattr(
        "core.tasks.task_dispatcher.settings.TASK_DISPATCHER",
        "background_tasks",
    )

    dispatcher = build_task_dispatcher()

    assert isinstance(dispatcher, BackgroundTasksDispatcher)


def test_build_task_dispatcher_returns_celery_strategy(monkeypatch) -> None:
    monkeypatch.setattr("core.tasks.task_dispatcher.settings.TASK_DISPATCHER", "celery")
    monkeypatch.setattr(
        "core.tasks.task_dispatcher.settings.CELERY_RESULT_BACKEND",
        "redis://localhost:6379/1",
    )

    dispatcher = build_task_dispatcher()

    assert isinstance(dispatcher, CeleryTaskDispatcher)


def test_build_task_dispatcher_requires_result_backend(monkeypatch) -> None:
    monkeypatch.setattr("core.tasks.task_dispatcher.settings.TASK_DISPATCHER", "celery")
    monkeypatch.setattr("core.tasks.task_dispatcher.settings.CELERY_RESULT_BACKEND", "")

    with pytest.raises(TaskDispatcherConfigurationError, match="CELERY_RESULT_BACKEND"):
        build_task_dispatcher()


def test_build_task_dispatcher_rejects_unknown_strategy(monkeypatch) -> None:
    monkeypatch.setattr(
        "core.tasks.task_dispatcher.settings.TASK_DISPATCHER",
        "unknown",
    )

    with pytest.raises(TaskDispatcherConfigurationError, match="Unsupported"):
        build_task_dispatcher()


def test_build_markdown_dispatcher_wraps_generic_dispatcher(monkeypatch) -> None:
    task_dispatcher = object()
    monkeypatch.setattr(
        "labs.tasks.factory.build_task_dispatcher",
        lambda: task_dispatcher,
    )

    dispatcher = build_markdown_dispatcher(
        writer_agent=object(),
        translator_agent=object(),
        metadata_agent=object(),
        process_status_service=object(),
    )

    assert isinstance(dispatcher, MarkdownOrganizationTaskDispatcher)
    assert dispatcher.task_dispatcher is task_dispatcher
