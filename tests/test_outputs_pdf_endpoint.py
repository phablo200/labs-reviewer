from fastapi import FastAPI
import anyio
import httpx

from core.auth.dependencies import get_current_user
from core.auth.schemas import AuthenticatedUser
from labs import router as lab_router


def test_get_outputs_pdf_returns_service_payload(monkeypatch) -> None:
    app = FastAPI()

    async def _current_user_override() -> AuthenticatedUser:
        return AuthenticatedUser(
            id="user-id",
            email="user@example.com",
            profile_id="profile-id",
            application_id="00000000-0000-0000-0000-000000000002",
        )

    app.dependency_overrides[get_current_user] = _current_user_override
    app.include_router(lab_router.outputs_router)

    class _ServiceStub:
        def list_pdf_outputs(self):
            return {
                "items": [{"filename": "post.pdf", "path": "public/pdf/post.pdf"}],
                "count": 1,
            }

    monkeypatch.setattr(lab_router, "service", _ServiceStub())

    async def _request_output() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.get("/outputs/pdf")

    response = anyio.run(_request_output)

    assert response.status_code == 200
    assert response.json() == {
        "items": [{"filename": "post.pdf", "path": "public/pdf/post.pdf"}],
        "count": 1,
    }
