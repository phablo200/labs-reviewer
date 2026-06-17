"""Contracts for markdown organization task dispatch."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from fastapi import BackgroundTasks


@dataclass(frozen=True)
class MarkdownOrganizationJob:
    """Serializable application job for markdown organization."""

    context: str
    output_path: Path
    process_status_id: UUID


class TaskDispatchEnqueueError(Exception):
    """Raised when a task cannot be enqueued."""


class MarkdownOrganizationDispatcher(Protocol):
    """Strategy contract for markdown organization dispatch."""

    async def enqueue(
        self,
        *,
        job: MarkdownOrganizationJob,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        ...

