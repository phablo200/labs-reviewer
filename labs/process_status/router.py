"""HTTP routes for Labs process status."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.routing import APIRoute

from core.auth.dependencies import get_current_user
from core.auth.schemas import AuthenticatedUser
from core.auth.service import parse_user_id
from labs.process_status.schemas import (
    AgentProcessStatusDetailResponse,
    ProcessStatusNoteRequest,
    ProcessStatusNoteResponse,
    ProcessStatusResponse,
    WritingProcessStatusResponse,
)
from labs.process_status.service import ProcessStatusService

router = APIRouter(prefix="/labs/processes", tags=["Process Status"])
agent_process_router = APIRouter(
    prefix="/labs/agent-process",
    tags=["Agent Process Status"],
)
service = ProcessStatusService()


@router.get("/", response_model=list[ProcessStatusResponse])
async def list_process_statuses(
    term: str | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
) -> list[ProcessStatusResponse]:
    """Return the latest process statuses for the authenticated user."""
    return await service.list_process_statuses(user_id=parse_user_id(user), term=term)


@router.post(
    "/create",
    response_model=WritingProcessStatusResponse,
    summary="Create writing process status",
    description=(
        "Create a manual writing process for the authenticated user. "
        "This endpoint does not accept a request body; id, status, timestamps, "
        "and user ownership are assigned by the API."
    ),
)
async def create_writing_process_status(
    user: AuthenticatedUser = Depends(get_current_user),
) -> WritingProcessStatusResponse:
    """Create a manual writing process status for the authenticated user."""
    return await service.create_writing_process_status(user_id=parse_user_id(user))


@router.post("/notes", response_model=ProcessStatusNoteResponse)
async def create_or_update_process_note(
    request: ProcessStatusNoteRequest,
    id: UUID | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ProcessStatusNoteResponse:
    """Create or update a note owned through its parent process status."""
    note = await service.create_or_update_note(
        user_id=parse_user_id(user),
        request=request,
        note_id=id,
    )
    if note is None:
        raise HTTPException(status_code=404, detail="Process status note not found.")

    return note


async def list_process_notes(
    user: AuthenticatedUser = Depends(get_current_user),
) -> list[ProcessStatusNoteResponse]:
    """Return all notes owned by the authenticated user."""
    return await service.list_notes(user_id=parse_user_id(user))


# Register the singular compatibility path on the existing router object without
# changing main.py router registration.
router.routes.append(
    APIRoute(
        path="/labs/process/notes",
        endpoint=list_process_notes,
        response_model=list[ProcessStatusNoteResponse],
        methods=["GET"],
        tags=["Process Status"],
    )
)


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
