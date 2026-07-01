"""HTTP routes for Labs agent process status."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from core.auth.dependencies import get_current_user
from core.auth.schemas import AuthenticatedUser
from core.auth.service import parse_user_id
from labs.process_status.schemas import AgentProcessStatusDetailResponse
from labs.process_status.service import ProcessStatusService

agent_process_router = APIRouter(
    prefix="/labs/agent-process",
    tags=["Agent Process Status"],
)
service = ProcessStatusService()


@agent_process_router.get(
    "/{agent_process_id}",
    response_model=AgentProcessStatusDetailResponse,
)
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent process status not found.",
        )

    return agent_process_status
