from types import SimpleNamespace
from uuid import uuid4

from labs.process_status.proxy import (
    MAX_STATUS_RESULT_CHARS,
    TRUNCATED_RESULT_NOTICE,
    AgentInvocationProxy,
    AgentProcessContext,
)


class _AgentStub:
    def organize_notes(self, request):
        return SimpleNamespace(reviewed_markdown=request.context)


class _TranslatorStub:
    def translate(self, request):
        return SimpleNamespace(translated_markdown=request.content)


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


class _ResultFailingStatusServiceStub(_StatusServiceStub):
    async def mark_agent_process_succeeded(self, *, agent_process_status, result=None):
        if result is not None:
            raise RuntimeError("result too large")

        return await super().mark_agent_process_succeeded(
            agent_process_status=agent_process_status,
            result=result,
        )


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


def test_proxy_truncates_large_status_result() -> None:
    status_service = _StatusServiceStub()
    proxy = AgentInvocationProxy(
        agent=_TranslatorStub(),
        agent_name="Labs Translator",
        context=AgentProcessContext(process_status_id=uuid4()),
        status_service=status_service,
        tracked_methods={"translate"},
    )
    content = "x" * (MAX_STATUS_RESULT_CHARS + 10)

    proxy.translate(SimpleNamespace(content=content))

    persisted_result = status_service.succeeded[0][1]
    assert persisted_result == (
        ("x" * MAX_STATUS_RESULT_CHARS) + TRUNCATED_RESULT_NOTICE
    )


def test_proxy_retries_success_status_without_result_when_result_update_fails() -> None:
    status_service = _ResultFailingStatusServiceStub()
    proxy = AgentInvocationProxy(
        agent=_TranslatorStub(),
        agent_name="Labs Translator",
        context=AgentProcessContext(process_status_id=uuid4()),
        status_service=status_service,
        tracked_methods={"translate"},
    )

    response = proxy.translate(SimpleNamespace(content="# Translated"))

    assert response.translated_markdown == "# Translated"
    assert status_service.succeeded[0][1] is None
    assert status_service.failed == []
