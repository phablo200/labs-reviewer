from datetime import datetime, timezone
from uuid import uuid4

import anyio

from labs.process_status.models import AgentProcessStatus, ProcessStatus
from labs.process_status.service import ProcessStatusService


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


class _ProcessRepositoryStub:
    def __init__(self) -> None:
        self.created: ProcessStatus | None = None
        self.saved: ProcessStatus | None = None
        self.process_status = _process_status()

    async def create(self, *, file, user_id):
        self.created = _process_status(file=file, user_id=user_id)
        return self.created

    async def get_by_id(self, *, process_id, user_id):
        if self.process_status.id == process_id and self.process_status.user_id == user_id:
            return self.process_status
        return None

    async def get_by_process_id(self, process_id):
        if self.process_status.id == process_id:
            return self.process_status
        return None

    async def save(self, process_status):
        self.saved = process_status
        return process_status


class _AgentRepositoryStub:
    def __init__(self) -> None:
        self.created: AgentProcessStatus | None = None
        self.updated: AgentProcessStatus | None = None
        self.agent_processes: list[AgentProcessStatus] = []

    async def create(self, **kwargs):
        self.created = _agent_process_status(**kwargs)
        return self.created

    async def get_by_id(self, agent_process_id):
        for agent_process in self.agent_processes:
            if agent_process.id == agent_process_id:
                return agent_process
        return None

    async def list_by_process_status_id(self, process_status_id):
        return [
            agent_process
            for agent_process in self.agent_processes
            if agent_process.process_status_id == process_status_id
        ]

    async def list_children(self, parent_agent_process_status_id):
        return [
            agent_process
            for agent_process in self.agent_processes
            if agent_process.parent_agent_process_status_id
            == parent_agent_process_status_id
        ]

    async def update_status(self, *, agent_process_status, status, finished_at, result):
        agent_process_status.status = status
        agent_process_status.finished_at = finished_at
        agent_process_status.result = result
        self.updated = agent_process_status
        return agent_process_status


def test_service_create_process_status_delegates_to_repository() -> None:
    repository = _ProcessRepositoryStub()
    service = ProcessStatusService(
        repository=repository,
        agent_repository=_AgentRepositoryStub(),
    )
    user_id = uuid4()

    async def _create() -> ProcessStatus:
        return await service.create_process_for_review(file="notes.md", user_id=user_id)

    result = anyio.run(_create)

    assert result is repository.created
    assert result.file == "notes.md"
    assert result.status == "IN_PROGRESS"
    assert result.user_id == user_id


def test_service_create_agent_process_delegates_to_repository() -> None:
    agent_repository = _AgentRepositoryStub()
    service = ProcessStatusService(
        repository=_ProcessRepositoryStub(),
        agent_repository=agent_repository,
    )
    process_id = uuid4()

    async def _create() -> AgentProcessStatus:
        return await service.create_agent_process(
            process_status_id=process_id,
            name="Labs Writer",
        )

    result = anyio.run(_create)

    assert result is agent_repository.created
    assert result.process_status_id == process_id
    assert result.name == "Labs Writer"


def test_service_get_process_status_is_user_scoped() -> None:
    repository = _ProcessRepositoryStub()
    service = ProcessStatusService(
        repository=repository,
        agent_repository=_AgentRepositoryStub(),
    )

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


def test_service_build_status_response_excludes_result_and_builds_tree() -> None:
    repository = _ProcessRepositoryStub()
    agent_repository = _AgentRepositoryStub()
    parent = _agent_process_status(
        process_status_id=repository.process_status.id,
        name="Labs Writer",
        status="SUCCEEDED",
        result="final markdown",
    )
    child = _agent_process_status(
        process_status_id=repository.process_status.id,
        parent_agent_process_status_id=parent.id,
        name="Labs Reviewer",
        status="SUCCEEDED",
        result="review result",
    )
    agent_repository.agent_processes = [parent, child]
    service = ProcessStatusService(
        repository=repository,
        agent_repository=agent_repository,
    )

    async def _get_response():
        return await service.get_process_with_agent_processes(
            process_id=repository.process_status.id,
            user_id=repository.process_status.user_id,
        )

    response = anyio.run(_get_response)
    payload = response.model_dump()

    assert payload["status"] == "IN_PROGRESS"
    assert "result" not in payload["data"][0]
    assert "result" not in payload["data"][0]["children"][0]
    assert payload["data"][0]["children"][0]["name"] == "Labs Reviewer"
    assert repository.saved is None


def test_service_agent_process_detail_includes_result() -> None:
    repository = _ProcessRepositoryStub()
    agent_repository = _AgentRepositoryStub()
    parent = _agent_process_status(
        process_status_id=repository.process_status.id,
        name="Labs Writer",
        status="SUCCEEDED",
        result="final markdown",
    )
    child = _agent_process_status(
        process_status_id=repository.process_status.id,
        parent_agent_process_status_id=parent.id,
        name="Labs Reviewer",
        status="SUCCEEDED",
        result="review result",
    )
    agent_repository.agent_processes = [parent, child]
    service = ProcessStatusService(
        repository=repository,
        agent_repository=agent_repository,
    )

    async def _get_response():
        return await service.get_agent_process_with_children(
            agent_process_id=parent.id,
            user_id=repository.process_status.user_id,
        )

    response = anyio.run(_get_response)
    payload = response.model_dump()

    assert payload["result"] == "final markdown"
    assert "result" not in payload["children"][0]


def test_service_derives_process_status_from_agent_processes() -> None:
    service = ProcessStatusService(
        repository=_ProcessRepositoryStub(),
        agent_repository=_AgentRepositoryStub(),
    )

    assert service._derive_process_status([]) == "IN_PROGRESS"
    assert (
        service._derive_process_status(
            [
                _agent_process_status(status="SUCCEEDED"),
                _agent_process_status(status="SUCCEEDED"),
            ]
        )
        == "SUCCEEDED"
    )
    assert (
        service._derive_process_status(
            [
                _agent_process_status(status="SUCCEEDED"),
                _agent_process_status(status="IN_PROGRESS"),
            ]
        )
        == "IN_PROGRESS"
    )
    assert (
        service._derive_process_status(
            [
                _agent_process_status(status="FAILED"),
                _agent_process_status(status="IN_PROGRESS"),
            ]
        )
        == "FAILED"
    )


def test_service_marking_one_agent_succeeded_keeps_parent_in_progress() -> None:
    repository = _ProcessRepositoryStub()
    agent_repository = _AgentRepositoryStub()
    first = _agent_process_status(
        process_status_id=repository.process_status.id,
        status="IN_PROGRESS",
    )
    second = _agent_process_status(
        process_status_id=repository.process_status.id,
        status="IN_PROGRESS",
    )
    agent_repository.agent_processes = [first, second]
    service = ProcessStatusService(
        repository=repository,
        agent_repository=agent_repository,
    )

    async def _mark() -> AgentProcessStatus:
        return await service.mark_agent_process_succeeded(agent_process_status=first)

    result = anyio.run(_mark)

    assert result.status == "SUCCEEDED"
    assert repository.process_status.status == "IN_PROGRESS"
    assert repository.saved is None


def test_service_marking_final_agent_succeeded_updates_parent_to_succeeded() -> None:
    repository = _ProcessRepositoryStub()
    agent_repository = _AgentRepositoryStub()
    first = _agent_process_status(
        process_status_id=repository.process_status.id,
        status="SUCCEEDED",
    )
    second = _agent_process_status(
        process_status_id=repository.process_status.id,
        status="IN_PROGRESS",
    )
    agent_repository.agent_processes = [first, second]
    service = ProcessStatusService(
        repository=repository,
        agent_repository=agent_repository,
    )

    async def _mark() -> AgentProcessStatus:
        return await service.mark_agent_process_succeeded(agent_process_status=second)

    result = anyio.run(_mark)

    assert result.status == "SUCCEEDED"
    assert repository.process_status.status == "SUCCEEDED"
    assert repository.saved is repository.process_status


def test_service_marking_any_agent_failed_updates_parent_to_failed() -> None:
    repository = _ProcessRepositoryStub()
    agent_repository = _AgentRepositoryStub()
    first = _agent_process_status(
        process_status_id=repository.process_status.id,
        status="SUCCEEDED",
    )
    second = _agent_process_status(
        process_status_id=repository.process_status.id,
        status="IN_PROGRESS",
    )
    agent_repository.agent_processes = [first, second]
    service = ProcessStatusService(
        repository=repository,
        agent_repository=agent_repository,
    )

    async def _mark() -> AgentProcessStatus:
        return await service.mark_agent_process_failed(agent_process_status=second)

    result = anyio.run(_mark)

    assert result.status == "FAILED"
    assert repository.process_status.status == "FAILED"
    assert repository.saved is repository.process_status
