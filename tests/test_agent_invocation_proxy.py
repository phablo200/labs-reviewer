from types import SimpleNamespace
from uuid import uuid4

from labs.process_status.proxy import AgentInvocationProxy, AgentProcessContext


class _AgentStub:
    def organize_notes(self, request):
        return SimpleNamespace(reviewed_markdown=request.context)


class _FailingAgentStub:
    def organize_notes(self, _request):
        raise RuntimeError("agent failed")


class _StatusServiceStub:
    def __init__(self) -> None:
        self.created = []
        self.succeeded = []
        self.failed = []

    async def create_agent_process(self, **kwargs):
        agent_process_status = SimpleNamespace(id=uuid4(), **kwargs)
        self.created.append(agent_process_status)
        return agent_process_status

    async def mark_agent_process_succeeded(self, *, agent_process_status, result=None):
        self.succeeded.append((agent_process_status, result))
        return agent_process_status

    async def mark_agent_process_failed(self, *, agent_process_status, result=None):
        self.failed.append((agent_process_status, result))
        return agent_process_status


def test_proxy_tracks_successful_agent_invocation() -> None:
    status_service = _StatusServiceStub()
    proxy = AgentInvocationProxy(
        agent=_AgentStub(),
        agent_name="Labs Writer",
        context=AgentProcessContext(process_status_id=uuid4()),
        status_service=status_service,
        tracked_methods={"organize_notes"},
    )

    response = proxy.organize_notes(SimpleNamespace(context="# Notes"))

    assert response.reviewed_markdown == "# Notes"
    assert status_service.created[0].name == "Labs Writer"
    assert status_service.succeeded[0][1] == "# Notes"
    assert status_service.failed == []


def test_proxy_tracks_failed_agent_invocation() -> None:
    status_service = _StatusServiceStub()
    proxy = AgentInvocationProxy(
        agent=_FailingAgentStub(),
        agent_name="Labs Writer",
        context=AgentProcessContext(process_status_id=uuid4()),
        status_service=status_service,
        tracked_methods={"organize_notes"},
    )

    try:
        proxy.organize_notes(SimpleNamespace(context="# Notes"))
    except RuntimeError:
        pass

    assert status_service.succeeded == []
    assert status_service.failed[0][1] == "agent failed"
