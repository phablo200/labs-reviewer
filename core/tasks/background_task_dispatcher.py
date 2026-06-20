"""FastAPI BackgroundTasks dispatch strategy."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import BackgroundTasks


@dataclass(frozen=True)
class BackgroundTaskSubmission:
    """Task payload for FastAPI BackgroundTasks dispatch."""

    function: Callable[..., Any]
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)


class BackgroundTasksDispatcher:
    """Schedule work with FastAPI BackgroundTasks."""

    async def enqueue(
        self,
        *,
        background_task_submission: BackgroundTaskSubmission | None = None,
        background_tasks: BackgroundTasks | None = None,
        **_kwargs: Any,
    ) -> None:
        if background_task_submission is None:
            raise RuntimeError("Background task submission is required.")
        if background_tasks is None:
            raise RuntimeError("BackgroundTasks is required for background_tasks dispatch.")

        background_tasks.add_task(
            background_task_submission.function,
            *background_task_submission.args,
            **background_task_submission.kwargs,
        )
