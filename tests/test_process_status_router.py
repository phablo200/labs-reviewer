from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import FastAPI
import anyio
import httpx

from core.auth.dependencies import get_current_user
from core.auth.schemas import AuthenticatedUser
from labs.process_status import router as process_status_router
from labs.process_status.models import AgentStatus, ProcessStatus
from labs.process_status.schemas import ProcessStatusResponse


USER_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_USER_ID = UUID("22222222-2222-2222-2222-222222222222")


def _process_status(**kwargs) -> ProcessStatus:
    values = {
        "id": uuid4(),
        "file": "notes.md",
        "created_at": datetime.now(timezone.utc),
        "user_id": USER_ID,
        "data": [],
    }
    values.update(kwargs)
    return ProcessStatus.model_construct(**values)


class _ServiceStub:
    def __init__(self, process_status: ProcessStatus | None) -> None:
        self.process_status = process_status
        self.calls: list[tuple[UUID, UUID]] = []

    async def get_process_status(self, *, process_id: UUID, user_id: UUID):
        self.calls.append((process_id, user_id))
        if self.process_status is None:
            return None
        if self.process_status.id == process_id and self.process_status.user_id == user_id:
            return self.process_status
        return None

    def build_status_response(self, process_status: ProcessStatus) -> ProcessStatusResponse:
        return ProcessStatusResponse.from_process_status(process_status)


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
    return app


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path)


def test_status_endpoint_requires_authorization(monkeypatch) -> None:
    monkeypatch.setattr(process_status_router, "service", _ServiceStub(None))

    response = anyio.run(_get, _app(user_id=None), f"/labs/processes/{uuid4()}/status")

    assert response.status_code == 401


def test_status_endpoint_returns_404_for_missing_process(monkeypatch) -> None:
    monkeypatch.setattr(process_status_router, "service", _ServiceStub(None))

    response = anyio.run(_get, _app(), f"/labs/processes/{uuid4()}/status")

    assert response.status_code == 404


def test_status_endpoint_returns_owned_process_without_result(monkeypatch) -> None:
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
    stub = _ServiceStub(process_status)
    monkeypatch.setattr(process_status_router, "service", stub)

    response = anyio.run(
        _get,
        _app(),
        f"/labs/processes/{process_status.id}/status",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["file"] == "notes.md"
    assert payload["user_id"] == str(USER_ID)
    assert payload["data"][0]["name"] == "Labs Writer"
    assert "result" not in payload["data"][0]
    assert "result" not in payload["data"][0]["children"][0]


def test_status_endpoint_does_not_return_other_users_process(monkeypatch) -> None:
    process_status = _process_status(user_id=OTHER_USER_ID)
    monkeypatch.setattr(process_status_router, "service", _ServiceStub(process_status))

    response = anyio.run(
        _get,
        _app(user_id=USER_ID),
        f"/labs/processes/{process_status.id}/status",
    )

    assert response.status_code == 404
