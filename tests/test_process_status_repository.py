from uuid import uuid4

import anyio

from labs.process_status.repository import (
    AgentProcessStatusRepository,
    ProcessStatusRepository,
)
import labs.process_status.repository as repository_module


class _FakeProcessStatus:
    def __init__(self, *, file, user_id, status="IN_PROGRESS"):
        self.id = uuid4()
        self.file = file
        self.status = status
        self.user_id = user_id
        self.inserted = False
        self.saved = False

    async def insert(self):
        self.inserted = True
        return self

    async def save(self):
        self.saved = True
        return self


class _ComparableField:
    def __init__(self, name):
        self.name = name

    def __eq__(self, value):
        return self.name, value


class _FakeProcessStatusQuery:
    def __init__(self, results):
        self.results = results
        self.sort_value = None
        self.limit_value = None

    def sort(self, value):
        self.sort_value = value
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    async def to_list(self):
        return self.results


class _FakeProcessStatusFinder:
    user_id = _ComparableField("user_id")
    find_expressions = None
    query = None

    @classmethod
    def find(cls, *expressions):
        cls.find_expressions = expressions
        cls.query = _FakeProcessStatusQuery(
            [_FakeProcessStatus(file="notes.md", user_id=uuid4())]
        )
        return cls.query


class _FakeAgentProcessStatus:
    def __init__(
        self,
        *,
        process_status_id,
        parent_agent_process_status_id=None,
        name,
        status,
        loop_from=None,
        loop_to=None,
        result=None,
    ):
        self.id = uuid4()
        self.process_status_id = process_status_id
        self.parent_agent_process_status_id = parent_agent_process_status_id
        self.name = name
        self.status = status
        self.loop_from = loop_from
        self.loop_to = loop_to
        self.finished_at = None
        self.result = result
        self.inserted = False
        self.saved = False

    async def insert(self):
        self.inserted = True
        return self

    async def save(self):
        self.saved = True
        return self


def test_process_repository_create_inserts_process_status(monkeypatch) -> None:
    monkeypatch.setattr(repository_module, "ProcessStatus", _FakeProcessStatus)
    repository = ProcessStatusRepository()
    user_id = uuid4()

    async def _create():
        return await repository.create(file="notes.md", user_id=user_id)

    process_status = anyio.run(_create)

    assert process_status.inserted is True
    assert process_status.file == "notes.md"
    assert process_status.status == "IN_PROGRESS"
    assert process_status.user_id == user_id


def test_process_repository_save_persists_process_status() -> None:
    repository = ProcessStatusRepository()
    process_status = _FakeProcessStatus(file="notes.md", user_id=uuid4())

    async def _save():
        return await repository.save(process_status)

    result = anyio.run(_save)

    assert result is process_status
    assert process_status.saved is True


def test_process_repository_lists_latest_processes_by_user(monkeypatch) -> None:
    monkeypatch.setattr(repository_module, "ProcessStatus", _FakeProcessStatusFinder)
    repository = ProcessStatusRepository()
    user_id = uuid4()

    async def _list():
        return await repository.list_by_user_id(user_id=user_id)

    result = anyio.run(_list)

    assert result == _FakeProcessStatusFinder.query.results
    assert _FakeProcessStatusFinder.find_expressions == (("user_id", user_id),)
    assert _FakeProcessStatusFinder.query.sort_value == "-created_at"
    assert _FakeProcessStatusFinder.query.limit_value == 100


def test_process_repository_filters_processes_by_file_term(monkeypatch) -> None:
    monkeypatch.setattr(repository_module, "ProcessStatus", _FakeProcessStatusFinder)
    repository = ProcessStatusRepository()
    user_id = uuid4()

    async def _list():
        return await repository.list_by_user_id(user_id=user_id, term="notes.md")

    anyio.run(_list)

    user_filter, term_filter = _FakeProcessStatusFinder.find_expressions
    assert user_filter == ("user_id", user_id)
    assert term_filter.query == {
        "file": {
            "$regex": "notes\\.md",
            "$options": "i",
        }
    }
    assert _FakeProcessStatusFinder.query.limit_value == 100


def test_agent_repository_create_inserts_agent_process_status(monkeypatch) -> None:
    monkeypatch.setattr(
        repository_module,
        "AgentProcessStatus",
        _FakeAgentProcessStatus,
    )
    repository = AgentProcessStatusRepository()
    process_id = uuid4()
    parent_id = uuid4()

    async def _create():
        return await repository.create(
            process_status_id=process_id,
            parent_agent_process_status_id=parent_id,
            name="Labs Writer",
            loop_from=1,
            loop_to=3,
        )

    agent_process_status = anyio.run(_create)

    assert agent_process_status.inserted is True
    assert agent_process_status.process_status_id == process_id
    assert agent_process_status.parent_agent_process_status_id == parent_id
    assert agent_process_status.name == "Labs Writer"
    assert agent_process_status.status == "IN_PROGRESS"
    assert agent_process_status.loop_from == 1
    assert agent_process_status.loop_to == 3


def test_agent_repository_update_status_persists_result() -> None:
    repository = AgentProcessStatusRepository()
    agent_process_status = _FakeAgentProcessStatus(
        process_status_id=uuid4(),
        name="Labs Writer",
        status="IN_PROGRESS",
    )

    async def _update():
        return await repository.update_status(
            agent_process_status=agent_process_status,
            status="SUCCEEDED",
            finished_at="now",
            result="MARKDOWN_CONTENT",
        )

    result = anyio.run(_update)

    assert result is agent_process_status
    assert agent_process_status.status == "SUCCEEDED"
    assert agent_process_status.finished_at == "now"
    assert agent_process_status.result == "MARKDOWN_CONTENT"
    assert agent_process_status.saved is True
