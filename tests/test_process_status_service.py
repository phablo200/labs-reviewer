from datetime import datetime, timezone
from uuid import uuid4

import anyio

from labs.process_status.models import AgentStatus, ProcessStatus
from labs.process_status.service import ProcessStatusService


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


class _RepositoryStub:
    def __init__(self) -> None:
        self.created: ProcessStatus | None = None
        self.saved: ProcessStatus | None = None
        self.process_status = _process_status()

    async def create(self, *, file, user_id, data=None):
        self.created = _process_status(file=file, user_id=user_id, data=data or [])
        return self.created

    async def get_by_id(self, *, process_id, user_id):
        if self.process_status.id == process_id and self.process_status.user_id == user_id:
            return self.process_status
        return None

    async def save(self, process_status):
        self.saved = process_status
        return process_status


def test_service_create_process_status_delegates_to_repository() -> None:
    repository = _RepositoryStub()
    service = ProcessStatusService(repository=repository)
    user_id = uuid4()

    async def _create() -> ProcessStatus:
        return await service.create_process_status(
            file="notes.md",
            user_id=user_id,
            data=[AgentStatus(name="Labs Writer", status="IN_PROGRESS")],
        )

    result = anyio.run(_create)

    assert result is repository.created
    assert result.file == "notes.md"
    assert result.user_id == user_id


def test_service_get_process_status_is_user_scoped() -> None:
    repository = _RepositoryStub()
    service = ProcessStatusService(repository=repository)

    async def _get_found() -> ProcessStatus | None:
        return await service.get_process_status(
            process_id=repository.process_status.id,
            user_id=repository.process_status.user_id,
        )

    async def _get_missing() -> ProcessStatus | None:
        return await service.get_process_status(
            process_id=repository.process_status.id,
            user_id=uuid4(),
        )

    found = anyio.run(_get_found)
    missing = anyio.run(_get_missing)

    assert found is repository.process_status
    assert missing is None


def test_service_build_status_response_excludes_result() -> None:
    service = ProcessStatusService(repository=_RepositoryStub())
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
                        result="review result",
                    )
                ],
            )
        ],
    )

    payload = service.build_status_response(process_status).model_dump()

    assert "result" not in payload["data"][0]
    assert "result" not in payload["data"][0]["children"][0]
