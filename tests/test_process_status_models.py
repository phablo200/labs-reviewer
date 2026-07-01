from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from labs.process_status.models import (
    AgentProcessStatus,
    ProcessStatus,
    ProcessStatusNote,
)
from labs.process_status.schemas import (
    AgentProcessStatusDetailResponse,
    AgentProcessStatusSummaryResponse,
    ProcessStatusNoteBodyRequest,
    ProcessStatusNoteRequest,
    ProcessStatusNoteResponse,
    ProcessStatusResponse,
)


def _process_status(**kwargs) -> ProcessStatus:
    values = {
        "id": uuid4(),
        "file": "notes.md",
        "status": "IN_PROGRESS",
        "created_at": datetime.now(timezone.utc),
        "user_id": uuid4(),
    }
    values.update(kwargs)
    return ProcessStatus.model_construct(**values)


def _agent_process_status(**kwargs) -> AgentProcessStatus:
    values = {
        "id": uuid4(),
        "process_status_id": uuid4(),
        "parent_agent_process_status_id": None,
        "name": "Labs Writer",
        "status": "IN_PROGRESS",
        "loop_from": None,
        "loop_to": None,
        "finished_at": None,
        "result": None,
    }
    values.update(kwargs)
    return AgentProcessStatus.model_construct(**values)


def test_agent_process_status_uses_expected_collection_and_process_id() -> None:
    process_id = uuid4()
    agent_process_status = _agent_process_status(process_status_id=process_id)

    assert AgentProcessStatus.Settings.name == "agent_process_status"
    assert agent_process_status.process_status_id == process_id


def test_agent_process_status_supports_parent_child_ids_and_result() -> None:
    parent_id = uuid4()
    agent_process_status = _agent_process_status(
        parent_agent_process_status_id=parent_id,
        result="reviewed markdown",
    )

    assert agent_process_status.parent_agent_process_status_id == parent_id
    assert agent_process_status.result == "reviewed markdown"


def test_process_status_uses_expected_collection_name_and_file() -> None:
    process_status = _process_status()

    assert ProcessStatus.Settings.name == "process_status"
    assert process_status.file == "notes.md"
    assert process_status.status == "IN_PROGRESS"
    assert not hasattr(process_status, "data")


def test_process_status_defaults_to_in_progress() -> None:
    process_status = ProcessStatus.model_construct(
        id=uuid4(),
        user_id=uuid4(),
    )

    assert process_status.status == "IN_PROGRESS"
    assert process_status.file is None


def test_process_status_can_be_writting() -> None:
    process_status = _process_status(
        file="2026-06-18 10:00:00",
        status="WRITTING",
    )

    assert process_status.status == "WRITTING"
    assert process_status.file == "2026-06-18 10:00:00"


def test_process_status_note_uses_expected_collection_and_timestamps() -> None:
    process_id = uuid4()
    note = ProcessStatusNote.model_construct(
        id=uuid4(),
        process_status_id=process_id,
        description="Draft note",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    assert ProcessStatusNote.Settings.name == "process_status_notes"
    assert note.process_status_id == process_id
    assert note.description == "Draft note"
    assert isinstance(note.created_at, datetime)
    assert isinstance(note.updated_at, datetime)


def test_process_status_response_excludes_result_recursively() -> None:
    child = _agent_process_status(
        name="Labs Reviewer",
        status="SUCCEEDED",
        result="review notes",
    )
    parent = _agent_process_status(
        name="Labs Writer",
        status="SUCCEEDED",
        result="final markdown",
    )

    payload = ProcessStatusResponse.from_process_status(
        _process_status(),
        data=[
            AgentProcessStatusSummaryResponse.from_agent_process_status(
                parent,
                children=[
                    AgentProcessStatusSummaryResponse.from_agent_process_status(child)
                ],
            )
        ],
    ).model_dump()

    assert "result" not in payload["data"][0]
    assert "result" not in payload["data"][0]["children"][0]
    assert payload["file"] == "notes.md"
    assert payload["status"] == "IN_PROGRESS"
    assert payload["data"][0]["children"][0]["name"] == "Labs Reviewer"


def test_process_status_response_accepts_null_file() -> None:
    payload = ProcessStatusResponse.from_process_status(
        _process_status(file=None, status="WRITTING")
    ).model_dump()

    assert payload["file"] is None
    assert payload["status"] == "WRITTING"


def test_process_status_note_request_strips_note_and_rejects_blank() -> None:
    process_id = uuid4()
    request = ProcessStatusNoteRequest(process_status_id=process_id, note="  draft  ")

    assert request.process_status_id == process_id
    assert request.note == "draft"

    with pytest.raises(ValidationError):
        ProcessStatusNoteRequest(process_status_id=process_id, note="   ")


def test_process_status_note_body_request_strips_note_and_rejects_blank() -> None:
    request = ProcessStatusNoteBodyRequest(note="  draft  ")

    assert request.note == "draft"

    with pytest.raises(ValidationError):
        ProcessStatusNoteBodyRequest(note="   ")


def test_process_status_note_response_maps_note_fields() -> None:
    note = ProcessStatusNote.model_construct(
        id=uuid4(),
        process_status_id=uuid4(),
        description="Draft note",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    payload = ProcessStatusNoteResponse.from_process_status_note(note).model_dump()

    assert payload["id"] == note.id
    assert payload["process_status_id"] == note.process_status_id
    assert payload["description"] == "Draft note"
    assert payload["created_at"] == note.created_at
    assert payload["updated_at"] == note.updated_at


def test_agent_process_detail_response_includes_result() -> None:
    agent_process_status = _agent_process_status(result="MARKDOWN_CONTENT")

    payload = AgentProcessStatusDetailResponse.from_agent_process_status(
        agent_process_status
    ).model_dump()

    assert payload["result"] == "MARKDOWN_CONTENT"
