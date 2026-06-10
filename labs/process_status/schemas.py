"""Response schemas for process status endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from labs.process_status.models import AgentStatus, AgentStatusState, ProcessStatus


class AgentStatusResponse(BaseModel):
    """Status response for an agent, excluding persisted result content."""

    id: UUID
    name: str
    status: AgentStatusState
    loop_from: int | None = None
    loop_to: int | None = None
    finished_at: datetime | None = None
    children: list[AgentStatusResponse] = Field(default_factory=list)

    @classmethod
    def from_agent_status(cls, agent_status: AgentStatus) -> AgentStatusResponse:
        return cls(
            id=agent_status.id,
            name=agent_status.name,
            status=agent_status.status,
            loop_from=agent_status.loop_from,
            loop_to=agent_status.loop_to,
            finished_at=agent_status.finished_at,
            children=[
                cls.from_agent_status(child) for child in agent_status.children
            ],
        )


class ProcessStatusResponse(BaseModel):
    """Process status response, excluding persisted agent result content."""

    id: UUID
    file: str
    created_at: datetime
    user_id: UUID
    data: list[AgentStatusResponse] = Field(default_factory=list)

    @classmethod
    def from_process_status(cls, process_status: ProcessStatus) -> ProcessStatusResponse:
        return cls(
            id=process_status.id,
            file=process_status.file,
            created_at=process_status.created_at,
            user_id=process_status.user_id,
            data=[
                AgentStatusResponse.from_agent_status(agent_status)
                for agent_status in process_status.data
            ],
        )
