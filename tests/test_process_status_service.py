from datetime import datetime, timezone
from uuid import uuid4

import anyio

from labs.process_status.models import (
    AgentProcessStatus,
    ProcessStatus,
    ProcessStatusNote,
)
from labs.process_status.schemas import ProcessStatusNoteRequest
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


def _process_status_note(**kwargs) -> ProcessStatusNote:
    values = {
        "id": uuid4(),
        "process_status_id": uuid4(),
        "description": "Draft note",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    values.update(kwargs)
    return ProcessStatusNote.model_construct(**values)


class _ProcessRepositoryStub:
    def __init__(self) -> None:
        self.created: ProcessStatus | None = None
        self.saved: ProcessStatus | None = None
        self.process_status = _process_status()
        self.process_statuses: list[ProcessStatus] = []
        self.list_call: tuple[object, object, int] | None = None

    async def create(self, *, file, user_id):
        self.created = _process_status(file=file, user_id=user_id)
        return self.created

    async def create_writing(self, *, user_id):
        self.created = _process_status(
            file="2026-06-18 10:00:00",
            status="WRITTING",
            user_id=user_id,
        )
        return self.created

    async def list_by_user_id(self, *, user_id, term=None, limit=100):
        self.list_call = (user_id, term, limit)
        return self.process_statuses

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


class _NoteRepositoryStub:
    def __init__(self) -> None:
        self.created: ProcessStatusNote | None = None
        self.updated: ProcessStatusNote | None = None
        self.notes: list[ProcessStatusNote] = []
        self.list_call: list | None = None

    async def create(self, *, process_status_id, description):
        self.created = _process_status_note(
            process_status_id=process_status_id,
            description=description,
        )
        return self.created

    async def get_by_id(self, note_id):
        for note in self.notes:
            if note.id == note_id:
                return note
        return None

    async def update(self, *, note, description):
        note.description = description
        note.updated_at = datetime.now(timezone.utc)
        self.updated = note
        return note

    async def list_by_process_status_ids(self, process_status_ids):
        self.list_call = process_status_ids
        return [
            note
            for note in self.notes
            if note.process_status_id in process_status_ids
        ]


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


def test_service_create_writing_process_status_returns_response() -> None:
    repository = _ProcessRepositoryStub()
    service = ProcessStatusService(
        repository=repository,
        agent_repository=_AgentRepositoryStub(),
        note_repository=_NoteRepositoryStub(),
    )
    user_id = uuid4()

    async def _create():
        return await service.create_writing_process_status(user_id=user_id)

    result = anyio.run(_create)

    assert repository.created.file == "2026-06-18 10:00:00"
    assert repository.created.status == "WRITTING"
    assert result.file == "2026-06-18 10:00:00"
    assert result.status == "WRITTING"
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


def test_service_lists_latest_process_statuses_for_user() -> None:
    repository = _ProcessRepositoryStub()
    first = _process_status(file="first.md", user_id=repository.process_status.user_id)
    second = _process_status(file="second.md", user_id=repository.process_status.user_id)
    repository.process_statuses = [first, second]
    service = ProcessStatusService(
        repository=repository,
        agent_repository=_AgentRepositoryStub(),
    )

    async def _list():
        return await service.list_process_statuses(user_id=repository.process_status.user_id)

    response = anyio.run(_list)
    payload = [item.model_dump() for item in response]

    assert repository.list_call == (repository.process_status.user_id, None, 100)
    assert [item["file"] for item in payload] == ["first.md", "second.md"]
    assert payload[0]["data"] == []


def test_service_passes_search_term_to_process_repository() -> None:
    repository = _ProcessRepositoryStub()
    service = ProcessStatusService(
        repository=repository,
        agent_repository=_AgentRepositoryStub(),
    )

    async def _list():
        return await service.list_process_statuses(
            user_id=repository.process_status.user_id,
            term="notes",
        )

    anyio.run(_list)

    assert repository.list_call == (repository.process_status.user_id, "notes", 100)


def test_service_create_note_requires_owned_parent_process() -> None:
    repository = _ProcessRepositoryStub()
    note_repository = _NoteRepositoryStub()
    service = ProcessStatusService(
        repository=repository,
        agent_repository=_AgentRepositoryStub(),
        note_repository=note_repository,
    )
    request = ProcessStatusNoteRequest(
        process_status_id=repository.process_status.id,
        note="Draft note",
    )

    async def _create_owned():
        return await service.create_or_update_note(
            user_id=repository.process_status.user_id,
            request=request,
        )

    async def _create_unowned():
        return await service.create_or_update_note(
            user_id=uuid4(),
            request=request,
        )

    owned = anyio.run(_create_owned)
    unowned = anyio.run(_create_unowned)

    assert owned.description == "Draft note"
    assert owned.process_status_id == repository.process_status.id
    assert unowned is None


def test_service_update_note_requires_existing_owned_parent_process() -> None:
    repository = _ProcessRepositoryStub()
    note_repository = _NoteRepositoryStub()
    note = _process_status_note(
        process_status_id=repository.process_status.id,
        description="Old note",
    )
    note_repository.notes = [note]
    service = ProcessStatusService(
        repository=repository,
        agent_repository=_AgentRepositoryStub(),
        note_repository=note_repository,
    )
    request = ProcessStatusNoteRequest(
        process_status_id=uuid4(),
        note="New note",
    )

    async def _update_owned():
        return await service.create_or_update_note(
            user_id=repository.process_status.user_id,
            request=request,
            note_id=note.id,
        )

    async def _update_unowned():
        return await service.create_or_update_note(
            user_id=uuid4(),
            request=request,
            note_id=note.id,
        )

    owned = anyio.run(_update_owned)
    unowned = anyio.run(_update_unowned)

    assert owned.id == note.id
    assert owned.description == "New note"
    assert note_repository.updated is note
    assert unowned is None


def test_service_update_note_returns_none_when_note_is_missing() -> None:
    repository = _ProcessRepositoryStub()
    service = ProcessStatusService(
        repository=repository,
        agent_repository=_AgentRepositoryStub(),
        note_repository=_NoteRepositoryStub(),
    )
    request = ProcessStatusNoteRequest(
        process_status_id=repository.process_status.id,
        note="New note",
    )

    async def _update_missing():
        return await service.create_or_update_note(
            user_id=repository.process_status.user_id,
            request=request,
            note_id=uuid4(),
        )

    assert anyio.run(_update_missing) is None


def test_service_list_notes_filters_to_owned_process_ids() -> None:
    repository = _ProcessRepositoryStub()
    owned_first = _process_status(user_id=repository.process_status.user_id)
    owned_second = _process_status(user_id=repository.process_status.user_id)
    repository.process_statuses = [owned_first, owned_second]
    note_repository = _NoteRepositoryStub()
    visible_note = _process_status_note(process_status_id=owned_first.id)
    hidden_note = _process_status_note(process_status_id=uuid4())
    note_repository.notes = [visible_note, hidden_note]
    service = ProcessStatusService(
        repository=repository,
        agent_repository=_AgentRepositoryStub(),
        note_repository=note_repository,
    )

    async def _list():
        return await service.list_notes(user_id=repository.process_status.user_id)

    response = anyio.run(_list)

    assert repository.list_call == (repository.process_status.user_id, None, 0)
    assert note_repository.list_call == [owned_first.id, owned_second.id]
    assert [item.id for item in response] == [visible_note.id]


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
