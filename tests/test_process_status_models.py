from datetime import datetime, timezone
from uuid import uuid4

from labs.process_status.models import AgentProcessStatus, ProcessStatus
from labs.process_status.schemas import (
    AgentProcessStatusDetailResponse,
    AgentProcessStatusSummaryResponse,
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
        file="notes.md",
        user_id=uuid4(),
    )

    assert process_status.status == "IN_PROGRESS"


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


def test_agent_process_detail_response_includes_result() -> None:
    agent_process_status = _agent_process_status(result="MARKDOWN_CONTENT")

    payload = AgentProcessStatusDetailResponse.from_agent_process_status(
        agent_process_status
    ).model_dump()

    assert payload["result"] == "MARKDOWN_CONTENT"
