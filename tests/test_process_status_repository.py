from uuid import uuid4

import anyio

from labs.process_status.models import AgentStatus
import labs.process_status.repository as repository_module
from labs.process_status.repository import ProcessStatusRepository


class _FakeProcessStatus:
    def __init__(self, *, file, user_id, data=None):
        self.id = uuid4()
        self.file = file
        self.user_id = user_id
        self.data = data or []
        self.inserted = False
        self.saved = False

    async def insert(self):
        self.inserted = True
        return self

    async def save(self):
        self.saved = True
        return self


def test_repository_create_inserts_process_status(monkeypatch) -> None:
    monkeypatch.setattr(repository_module, "ProcessStatus", _FakeProcessStatus)
    repository = ProcessStatusRepository()
    user_id = uuid4()
    data = [AgentStatus(name="Labs Writer", status="IN_PROGRESS")]

    async def _create():
        return await repository.create(file="notes.md", user_id=user_id, data=data)

    process_status = anyio.run(_create)

    assert process_status.inserted is True
    assert process_status.file == "notes.md"
    assert process_status.user_id == user_id
    assert process_status.data == data


def test_repository_save_persists_process_status() -> None:
    repository = ProcessStatusRepository()
    process_status = _FakeProcessStatus(file="notes.md", user_id=uuid4())

    async def _save():
        return await repository.save(process_status)

    result = anyio.run(_save)

    assert result is process_status
    assert process_status.saved is True
