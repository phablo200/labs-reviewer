"""HTTP routes for Labs process status."""

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from core.auth.dependencies import get_current_user
from core.auth.schemas import AuthenticatedUser
from core.auth.service import parse_user_id
from labs.process_status.constants import ALLOWED_NOTE_FILE_SUFFIXES, NOTE_FILE_MAX_BYTES
from labs.process_status.schemas import (
    ProcessStatusNoteBodyRequest,
    ProcessStatusNoteRequest,
    ProcessStatusNoteDestroyedResponse,
    ProcessStatusNoteResponse,
    ProcessStatusResponse,
    WritingProcessStatusResponse,
)
from labs.process_status.service import ProcessStatusService

router = APIRouter(prefix="/labs/processes", tags=["Process Status"])
service = ProcessStatusService()


@router.get("", response_model=list[ProcessStatusResponse])
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Process status not found.",
        )

    return process_status


@router.delete("/{process_id}/destroy")
async def destroy_process(process_id: UUID):
    """Destroy a process by id."""
    result = await service.destroy_process(process_id)
    if not result["status"]:
        raise HTTPException(status_code=result["status_code"], detail=result)

    return result


@router.post("/files-note/{process_status_id}", response_model=ProcessStatusNoteResponse)
async def create_file_note(
    process_status_id: UUID,
    file: UploadFile = File(...),
    user: AuthenticatedUser = Depends(get_current_user),
) -> ProcessStatusNoteResponse:
    """Store uploaded note file content for an existing process."""
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A filename is required.",
        )

    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_NOTE_FILE_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .md and .txt files are supported.",
        )

    raw_content = await file.read()
    if not raw_content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File must not be empty.",
        )
    if len(raw_content) > NOTE_FILE_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File must be 10 KiB or smaller.",
        )

    try:
        description = raw_content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be UTF-8 encoded.",
        ) from exc

    note = await service.create_note_from_file(
        process_status_id=process_status_id,
        user_id=parse_user_id(user),
        description=description,
    )
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Process status not found.",
        )

    return note


@router.post("/notes/{process_status_id}", response_model=ProcessStatusNoteResponse)
async def create_or_update_process_note(
    process_status_id: UUID,
    request: ProcessStatusNoteBodyRequest,
    id: UUID | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ProcessStatusNoteResponse:
    """Create or update a note owned through its parent process status."""
    note = await service.create_or_update_note(
        user_id=parse_user_id(user),
        request=ProcessStatusNoteRequest(
            process_status_id=process_status_id,
            note=request.note,
        ),
        note_id=id,
    )
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Process status note not found.",
        )

    return note


@router.get("/notes", response_model=list[ProcessStatusNoteResponse])
async def list_process_notes(
    user: AuthenticatedUser = Depends(get_current_user),
) -> list[ProcessStatusNoteResponse]:
    """Return all notes owned by the authenticated user."""
    return await service.list_notes(user_id=parse_user_id(user))


@router.get("/notes/{process_status_id}", response_model=list[ProcessStatusNoteResponse])
async def list_process_notes_by_process(
    process_status_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
) -> list[ProcessStatusNoteResponse]:
    """Return notes for one process owned by the authenticated user."""
    process_notes = await service.get_process_notes(
        process_status_id=process_status_id,
        user_id=parse_user_id(user),
    )
    if process_notes is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Process status not found.",
        )

    return [
        ProcessStatusNoteResponse.from_process_status_note(note)
        for note in process_notes.notes
    ]


@router.delete("/notes/{note_id}", response_model=ProcessStatusNoteDestroyedResponse)
async def destroy_note(note_id: UUID):
    """Destroy a note by note_id."""
    result = await service.destroy_note(note_id)
    if not result["status"]:
        raise HTTPException(status_code=result["status_code"], detail=result)

    return result
