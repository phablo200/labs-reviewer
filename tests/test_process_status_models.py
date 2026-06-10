from datetime import datetime, timezone
from uuid import uuid4

from labs.process_status.models import AgentStatus, ProcessStatus
from labs.process_status.schemas import ProcessStatusResponse


def _process_status(**kwargs) -> ProcessStatus:
    values = {
        "id": uuid4(),
        "file": "notes.md",
        "created_at": datetime.now(timezone.utc),
        "user_id": uuid4(),
        "data": [],
    }
    values.update(kwargs)
    return ProcessStatus.model_construct(**values)


def test_agent_status_supports_nested_children_and_result() -> None:
    child = AgentStatus(
        name="Labs Reviewer",
        status="SUCCEEDED",
        result="reviewed markdown",
    )
    parent = AgentStatus(
        name="Labs Writer",
        status="IN_PROGRESS",
        children=[child],
    )

    assert parent.children[0].result == "reviewed markdown"
    assert parent.children[0].name == "Labs Reviewer"


def test_agent_status_children_do_not_share_mutable_defaults() -> None:
    first = AgentStatus(name="Labs Writer", status="IN_PROGRESS")
    second = AgentStatus(name="Labs Translator", status="IN_PROGRESS")

    first.children.append(AgentStatus(name="Labs Reviewer", status="SUCCEEDED"))

    assert len(first.children) == 1
    assert second.children == []


def test_process_status_uses_expected_collection_name_and_file() -> None:
    process_status = _process_status()

    assert ProcessStatus.Settings.name == "process_status"
    assert process_status.file == "notes.md"


def test_process_status_response_excludes_result_recursively() -> None:
    process_status = _process_status(
        data=[
            AgentStatus(
                name="Labs Writer",
                status="SUCCEEDED",
                result="final markdown",
                children=[
                    AgentStatus(
                        name="Labs Reviewer",
                        status="SUCCEEDED",
                        result="review notes",
                    )
                ],
            )
        ],
    )

    payload = ProcessStatusResponse.from_process_status(process_status).model_dump()

    assert "result" not in payload["data"][0]
    assert "result" not in payload["data"][0]["children"][0]
    assert payload["file"] == "notes.md"
    assert payload["data"][0]["children"][0]["name"] == "Labs Reviewer"
