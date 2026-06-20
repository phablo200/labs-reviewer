"""Celery task dispatch strategy."""

from dataclasses import dataclass
from typing import Any

from core.tasks.exceptions import TaskDispatchEnqueueError


@dataclass(frozen=True)
class CeleryTaskSubmission:
    """Task payload for Celery dispatch."""

    task: Any
    args: tuple[Any, ...] = ()


class CeleryTaskDispatcher:
    """Schedule work with Celery."""

    async def enqueue(
        self,
        *,
        celery_task_submission: CeleryTaskSubmission,
    ) -> None:
        try:
            celery_task_submission.task.delay(*celery_task_submission.args)
        except Exception as exc:
            raise TaskDispatchEnqueueError("Failed to enqueue Celery task.") from exc
