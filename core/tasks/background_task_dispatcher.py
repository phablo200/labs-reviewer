"""FastAPI BackgroundTasks dispatch strategy."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import BackgroundTasks


@dataclass(frozen=True)
class BackgroundTaskSubmission:
    """Task payload for FastAPI BackgroundTasks dispatch."""

    function: Callable[..., Any]
    args: tuple[Any, ...] = ()


class BackgroundTasksDispatcher:
    """Schedule work with FastAPI BackgroundTasks."""

    async def enqueue(
        self,
        *,
        submission: BackgroundTaskSubmission,
        background_tasks: BackgroundTasks,
    ) -> None:
        background_tasks.add_task(
            submission.function,
            *submission.args,
        )
