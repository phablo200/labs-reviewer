"""Generic task dispatcher contract and configuration-based builder."""

import core.tasks.constants as constants
from core.config import settings
from core.tasks.background_task_dispatcher import BackgroundTasksDispatcher
from core.tasks.celery_task_dispatcher import CeleryTaskDispatcher
from core.tasks.exceptions import TaskDispatcherConfigurationError


TaskDispatcher = BackgroundTasksDispatcher | CeleryTaskDispatcher


def build_task_dispatcher() -> TaskDispatcher:
    """Build the generic task dispatcher configured by TASK_DISPATCHER."""
    dispatcher = settings.TASK_DISPATCHER.strip().lower()

    if dispatcher == constants.DISPATCHER_BACKGROUND_TASKS:
        return BackgroundTasksDispatcher()

    if dispatcher == constants.DISPATCHER_CELERY:
        if not settings.CELERY_RESULT_BACKEND.strip():
            raise TaskDispatcherConfigurationError(
                "CELERY_RESULT_BACKEND is required when TASK_DISPATCHER=celery."
            )
        return CeleryTaskDispatcher()

    raise TaskDispatcherConfigurationError(
        f"Unsupported TASK_DISPATCHER: {settings.TASK_DISPATCHER}."
    )
