"""MongoDB document models for Labs workflow process status."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from beanie import Document
from pydantic import BaseModel, Field

AgentStatusState = Literal["IN_PROGRESS", "FAILED", "SUCCEEDED"]


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class AgentStatus(BaseModel):
    """Persisted status for a workflow agent or nested sub-agent."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    status: AgentStatusState
    loop_from: int | None = None
    loop_to: int | None = None
    finished_at: datetime | None = None
    result: str | None = None
    children: list[AgentStatus] = Field(default_factory=list)


class ProcessStatus(Document):
    """Persisted status for a complete Labs processing workflow."""

    id: UUID = Field(default_factory=uuid4)
    file: str
    created_at: datetime = Field(default_factory=utc_now)
    user_id: UUID
    data: list[AgentStatus] = Field(default_factory=list)

    class Settings:
        name = "process_status"
