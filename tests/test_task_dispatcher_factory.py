import pytest

from core.tasks.exceptions import TaskDispatcherConfigurationError
from labs.tasks.factory import (
    build_markdown_dispatcher,
)
from labs.tasks.celery_dispatcher import CeleryMarkdownDispatcher
from labs.tasks.fastapi_dispatcher import FastAPIBackgroundMarkdownDispatcher


def test_build_markdown_dispatcher_returns_fastapi_strategy(monkeypatch) -> None:
    monkeypatch.setattr("labs.tasks.factory.settings.TASK_DISPATCHER", "background_tasks")

    dispatcher = build_markdown_dispatcher(
        writer_agent=object(),
        translator_agent=object(),
        metadata_agent=object(),
        process_status_service=object(),
    )

    assert isinstance(dispatcher, FastAPIBackgroundMarkdownDispatcher)


def test_build_markdown_dispatcher_returns_celery_strategy(monkeypatch) -> None:
    monkeypatch.setattr("labs.tasks.factory.settings.TASK_DISPATCHER", "celery")
    monkeypatch.setattr(
        "labs.tasks.factory.settings.CELERY_RESULT_BACKEND",
        "redis://localhost:6379/1",
    )

    dispatcher = build_markdown_dispatcher(
        writer_agent=object(),
        translator_agent=object(),
        metadata_agent=object(),
        process_status_service=object(),
    )

    assert isinstance(dispatcher, CeleryMarkdownDispatcher)


def test_build_markdown_dispatcher_requires_result_backend(monkeypatch) -> None:
    monkeypatch.setattr("labs.tasks.factory.settings.TASK_DISPATCHER", "celery")
    monkeypatch.setattr("labs.tasks.factory.settings.CELERY_RESULT_BACKEND", "")

    with pytest.raises(TaskDispatcherConfigurationError, match="CELERY_RESULT_BACKEND"):
        build_markdown_dispatcher(
            writer_agent=object(),
            translator_agent=object(),
            metadata_agent=object(),
            process_status_service=object(),
        )


def test_build_markdown_dispatcher_rejects_unknown_strategy(monkeypatch) -> None:
    monkeypatch.setattr("labs.tasks.factory.settings.TASK_DISPATCHER", "unknown")

    with pytest.raises(TaskDispatcherConfigurationError, match="Unsupported"):
        build_markdown_dispatcher(
            writer_agent=object(),
            translator_agent=object(),
            metadata_agent=object(),
            process_status_service=object(),
        )
