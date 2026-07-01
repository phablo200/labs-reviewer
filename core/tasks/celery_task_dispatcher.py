"""Celery task dispatch strategy."""

from dataclasses import dataclass
from typing import Any, Protocol

from core.tasks.exceptions import TaskDispatchEnqueueError


class CeleryDelayableTask(Protocol):
    def delay(self, *args: Any, **kwargs: Any) -> Any:
        ...  

@dataclass(frozen=True)
class CeleryTaskSubmission:
    """Task payload for Celery dispatch."""

    task: CeleryDelayableTask
    args: tuple[Any, ...] = ()


class CeleryTaskDispatcher:
    """Schedule work with Celery."""

    async def enqueue(
        self,
        *,
        submission: CeleryTaskSubmission,
    ) -> None:
        try:
            submission.task.delay(*submission.args)
        except Exception as exc:
            raise TaskDispatchEnqueueError("Failed to enqueue Celery task.") from exc
