"""MongoDB document models for Labs workflow process status."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from beanie import Document
from pydantic import Field

from core.utils.datetime import utc_now

AgentProcessStatusState = Literal["IN_PROGRESS", "FAILED", "SUCCEEDED"]


class AgentProcessStatus(Document):
    """Persisted status for one workflow agent invocation."""

    id: UUID = Field(default_factory=uuid4)
    process_status_id: UUID
    parent_agent_process_status_id: UUID | None = None
    name: str
    status: AgentProcessStatusState
    loop_from: int | None = None
    loop_to: int | None = None
    finished_at: datetime | None = None
    result: str | None = None

    class Settings:
        name = "agent_process_status"


class ProcessStatus(Document):
    """Persisted status for a complete Labs processing workflow."""

    id: UUID = Field(default_factory=uuid4)
    file: str
    created_at: datetime = Field(default_factory=utc_now)
    user_id: UUID

    class Settings:
        name = "process_status"
