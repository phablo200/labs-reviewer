"""Celery task dispatch strategy."""

from dataclasses import dataclass, field
from typing import Any

from core.tasks.exceptions import TaskDispatchEnqueueError


@dataclass(frozen=True)
class CeleryTaskSubmission:
    """Task payload for Celery dispatch."""

    task: Any
    kwargs: dict[str, Any] = field(default_factory=dict)


class CeleryTaskDispatcher:
    """Schedule work with Celery."""

    async def enqueue(
        self,
        *,
        celery_task_submission: CeleryTaskSubmission | None = None,
        **_kwargs: Any,
    ) -> None:
        if celery_task_submission is None:
            raise RuntimeError("Celery task submission is required.")

        try:
            celery_task_submission.task.delay(**celery_task_submission.kwargs)
        except Exception as exc:
            raise TaskDispatchEnqueueError("Failed to enqueue Celery task.") from exc
