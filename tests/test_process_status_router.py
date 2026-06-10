from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import FastAPI
import anyio
import httpx

from core.auth.dependencies import get_current_user
from core.auth.schemas import AuthenticatedUser
from labs.process_status import router as process_status_router
from labs.process_status.models import AgentProcessStatus, ProcessStatus
from labs.process_status.schemas import (
    AgentProcessStatusDetailResponse,
    AgentProcessStatusSummaryResponse,
    ProcessStatusResponse,
)


USER_ID = UUID("11111111-1111-1111-1111-111111111111")


def _process_status_response() -> ProcessStatusResponse:
    child = AgentProcessStatusSummaryResponse(
        id=uuid4(),
        name="Labs Reviewer",
        status="SUCCEEDED",
        children=[],
    )
    parent = AgentProcessStatusSummaryResponse(
        id=uuid4(),
        name="Labs Writer",
        status="SUCCEEDED",
        children=[child],
    )
    return ProcessStatusResponse(
        id=uuid4(),
        file="notes.md",
        created_at=datetime.now(timezone.utc),
        user_id=USER_ID,
        data=[parent],
    )


def _agent_process_detail_response() -> AgentProcessStatusDetailResponse:
    return AgentProcessStatusDetailResponse(
        id=uuid4(),
        name="Labs Writer",
        status="SUCCEEDED",
        result="MARKDOWN_CONTENT",
        children=[
            AgentProcessStatusSummaryResponse(
                id=uuid4(),
                name="Labs Reviewer",
                status="SUCCEEDED",
                children=[],
            )
        ],
    )


class _ServiceStub:
    def __init__(
        self,
        process_response: ProcessStatusResponse | None = None,
        agent_response: AgentProcessStatusDetailResponse | None = None,
    ) -> None:
        self.process_response = process_response
        self.agent_response = agent_response
        self.process_calls: list[tuple[UUID, UUID]] = []
        self.agent_calls: list[tuple[UUID, UUID]] = []

    async def get_process_with_agent_processes(self, *, process_id: UUID, user_id: UUID):
        self.process_calls.append((process_id, user_id))
        return self.process_response

    async def get_agent_process_with_children(
        self,
        *,
        agent_process_id: UUID,
        user_id: UUID,
    ):
        self.agent_calls.append((agent_process_id, user_id))
        return self.agent_response


def _app(user_id: UUID | None = USER_ID) -> FastAPI:
    app = FastAPI()
    if user_id is not None:

        async def _current_user_override() -> AuthenticatedUser:
            return AuthenticatedUser(
                id=str(user_id),
                email="user@example.com",
                profile_id="profile-id",
                application_id="00000000-0000-0000-0000-000000000002",
            )

        app.dependency_overrides[get_current_user] = _current_user_override
    app.include_router(process_status_router.router)
    app.include_router(process_status_router.agent_process_router)
    return app


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path)


def test_status_endpoint_requires_authorization(monkeypatch) -> None:
    monkeypatch.setattr(process_status_router, "service", _ServiceStub())

    response = anyio.run(_get, _app(user_id=None), f"/labs/processes/{uuid4()}/status")

    assert response.status_code == 401


def test_status_endpoint_returns_404_for_missing_process(monkeypatch) -> None:
    monkeypatch.setattr(process_status_router, "service", _ServiceStub())

    response = anyio.run(_get, _app(), f"/labs/processes/{uuid4()}/status")

    assert response.status_code == 404


def test_status_endpoint_returns_process_without_result(monkeypatch) -> None:
    monkeypatch.setattr(
        process_status_router,
        "service",
        _ServiceStub(process_response=_process_status_response()),
    )

    response = anyio.run(_get, _app(), f"/labs/processes/{uuid4()}/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["file"] == "notes.md"
    assert payload["user_id"] == str(USER_ID)
    assert payload["data"][0]["name"] == "Labs Writer"
    assert "result" not in payload["data"][0]
    assert "result" not in payload["data"][0]["children"][0]


def test_agent_process_endpoint_returns_detail_with_result(monkeypatch) -> None:
    monkeypatch.setattr(
        process_status_router,
        "service",
        _ServiceStub(agent_response=_agent_process_detail_response()),
    )

    response = anyio.run(_get, _app(), f"/labs/agent-process/{uuid4()}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"] == "MARKDOWN_CONTENT"
    assert "result" not in payload["children"][0]


def test_agent_process_endpoint_returns_404_for_missing_agent_process(monkeypatch) -> None:
    monkeypatch.setattr(process_status_router, "service", _ServiceStub())

    response = anyio.run(_get, _app(), f"/labs/agent-process/{uuid4()}")

    assert response.status_code == 404
