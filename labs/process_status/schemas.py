"""Response schemas for process status endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from labs.process_status.models import (
    AgentProcessStatus,
    AgentProcessStatusState,
    ProcessStatus,
    ProcessStatusNote,
    ProcessStatusState,
)


class AgentProcessStatusSummaryResponse(BaseModel):
    """Agent process status response without result content."""

    id: UUID
    name: str
    status: AgentProcessStatusState
    loop_from: int | None = None
    loop_to: int | None = None
    finished_at: datetime | None = None
    children: list[AgentProcessStatusSummaryResponse] = Field(default_factory=list)

    @classmethod
    def from_agent_process_status(
        cls,
        agent_process_status: AgentProcessStatus,
        children: list[AgentProcessStatusSummaryResponse] | None = None,
    ) -> AgentProcessStatusSummaryResponse:
        return cls(
            id=agent_process_status.id,
            name=agent_process_status.name,
            status=agent_process_status.status,
            loop_from=agent_process_status.loop_from,
            loop_to=agent_process_status.loop_to,
            finished_at=agent_process_status.finished_at,
            children=children or [],
        )


class AgentProcessStatusDetailResponse(BaseModel):
    """Agent process detail response with result content."""

    id: UUID
    name: str
    status: AgentProcessStatusState
    loop_from: int | None = None
    loop_to: int | None = None
    finished_at: datetime | None = None
    children: list[AgentProcessStatusSummaryResponse] = Field(default_factory=list)
    result: str | None = None

    @classmethod
    def from_agent_process_status(
        cls,
        agent_process_status: AgentProcessStatus,
        children: list[AgentProcessStatusSummaryResponse] | None = None,
    ) -> AgentProcessStatusDetailResponse:
        return cls(
            id=agent_process_status.id,
            name=agent_process_status.name,
            status=agent_process_status.status,
            loop_from=agent_process_status.loop_from,
            loop_to=agent_process_status.loop_to,
            finished_at=agent_process_status.finished_at,
            children=children or [],
            result=agent_process_status.result,
        )


class ProcessStatusResponse(BaseModel):
    """Process status response assembled from related agent process records."""

    id: UUID
    file: str | None
    status: ProcessStatusState
    created_at: datetime
    user_id: UUID
    data: list[AgentProcessStatusSummaryResponse] = Field(default_factory=list)

    @classmethod
    def from_process_status(
        cls,
        process_status: ProcessStatus,
        data: list[AgentProcessStatusSummaryResponse] | None = None,
    ) -> ProcessStatusResponse:
        return cls(
            id=process_status.id,
            file=process_status.file,
            status=process_status.status,
            created_at=process_status.created_at,
            user_id=process_status.user_id,
            data=data or [],
        )


class ProcessStatusNoteRequest(BaseModel):
    """Request payload for creating or updating a process note."""

    process_status_id: UUID
    note: str = Field(min_length=1)

    @field_validator("note", mode="before")
    @classmethod
    def strip_note(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value


class ProcessStatusNoteResponse(BaseModel):
    """Persisted process note response."""

    id: UUID
    process_status_id: UUID
    description: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_process_status_note(
        cls,
        process_status_note: ProcessStatusNote,
    ) -> ProcessStatusNoteResponse:
        return cls(
            id=process_status_note.id,
            process_status_id=process_status_note.process_status_id,
            description=process_status_note.description,
            created_at=process_status_note.created_at,
            updated_at=process_status_note.updated_at,
        )
