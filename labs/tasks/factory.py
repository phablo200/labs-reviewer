"""Factories for task dispatch strategies."""

import core.tasks.constants as constants
from core.config import settings
from core.tasks.exceptions import TaskDispatcherConfigurationError
from labs.tasks.celery_dispatcher import CeleryMarkdownDispatcher
from labs.tasks.fastapi_dispatcher import FastAPIBackgroundMarkdownDispatcher
from labs.tasks.markdown_jobs import MarkdownOrganizationDispatcher


def build_markdown_dispatcher(
    *,
    writer_agent,
    translator_agent,
    metadata_agent,
    process_status_service,
) -> MarkdownOrganizationDispatcher:
    """Build the configured markdown dispatch strategy."""
    dispatcher = settings.TASK_DISPATCHER.strip().lower()

    if dispatcher == constants.DISPATCHER_BACKGROUND_TASKS:
        return FastAPIBackgroundMarkdownDispatcher(
            writer_agent=writer_agent,
            translator_agent=translator_agent,
            metadata_agent=metadata_agent,
            process_status_service=process_status_service,
        )

    if dispatcher == constants.DISPATCHER_CELERY:
        if not settings.CELERY_RESULT_BACKEND.strip():
            raise TaskDispatcherConfigurationError(
                "CELERY_RESULT_BACKEND is required when TASK_DISPATCHER=celery."
            )
        return CeleryMarkdownDispatcher()

    raise TaskDispatcherConfigurationError(
        f"Unsupported TASK_DISPATCHER: {settings.TASK_DISPATCHER}."
    )
