"""HTTP routes for Labs process status."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from core.auth.dependencies import get_current_user
from core.auth.schemas import AuthenticatedUser
from core.auth.service import parse_user_id
from labs.process_status.schemas import (
    AgentProcessStatusDetailResponse,
    ProcessStatusResponse,
)
from labs.process_status.service import ProcessStatusService

router = APIRouter(prefix="/labs/processes", tags=["Process Status"])
agent_process_router = APIRouter(
    prefix="/labs/agent-process",
    tags=["Agent Process Status"],
)
service = ProcessStatusService()


@router.get("/{process_id}/status", response_model=ProcessStatusResponse)
async def get_process_status(
    process_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ProcessStatusResponse:
    """Return process status metadata for the authenticated user."""
    process_status = await service.get_process_with_agent_processes(
        process_id=process_id,
        user_id=parse_user_id(user),
    )
    if process_status is None:
        raise HTTPException(status_code=404, detail="Process status not found.")

    return process_status


@agent_process_router.get("/{agent_process_id}", response_model=AgentProcessStatusDetailResponse)
async def get_agent_process_status(
    agent_process_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
) -> AgentProcessStatusDetailResponse:
    """Return agent process status with result content for the authenticated user."""
    agent_process_status = await service.get_agent_process_with_children(
        agent_process_id=agent_process_id,
        user_id=parse_user_id(user),
    )
    if agent_process_status is None:
        raise HTTPException(status_code=404, detail="Agent process status not found.")

    return agent_process_status
