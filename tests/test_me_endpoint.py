from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
import anyio
import httpx
import jwt

from core.auth import router as auth_router
from core.config import settings


SECRET = "test-secret"
APPLICATION_ID = "00000000-0000-0000-0000-000000000002"


def _token(
    *,
    secret: str = SECRET,
    application_id: str = APPLICATION_ID,
    expires_delta: timedelta = timedelta(minutes=5),
) -> str:
    return jwt.encode(
        {
            "sub": "user-id",
            "email": "user@example.com",
            "profile_id": "profile-id",
            "application_id": application_id,
            "exp": datetime.now(timezone.utc) + expires_delta,
        },
        secret,
        algorithm="HS256",
    )


def _configure_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "AUTH_TOKEN_VERIFIER", "jwt")
    monkeypatch.setattr(settings, "AUTH_JWT_SECRET", SECRET)
    monkeypatch.setattr(settings, "AUTH_JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(settings, "AUTH_EXPECTED_APPLICATION_ID", APPLICATION_ID)


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router.router)
    return app


async def _get_me(headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get("/me", headers=headers)


def test_me_requires_authorization(monkeypatch) -> None:
    _configure_auth(monkeypatch)

    response = anyio.run(_get_me)

    assert response.status_code == 401


def test_me_rejects_invalid_token(monkeypatch) -> None:
    _configure_auth(monkeypatch)

    response = anyio.run(_get_me, {"Authorization": "Bearer invalid-token"})

    assert response.status_code == 401


def test_me_rejects_wrong_application_id(monkeypatch) -> None:
    _configure_auth(monkeypatch)
    token = _token(application_id="00000000-0000-0000-0000-000000000003")

    response = anyio.run(_get_me, {"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


def test_me_returns_authenticated_user(monkeypatch) -> None:
    _configure_auth(monkeypatch)
    token = _token()

    response = anyio.run(_get_me, {"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "id": "user-id",
        "email": "user@example.com",
        "profile_id": "profile-id",
        "application_id": APPLICATION_ID,
    }


def test_me_openapi_documents_authorization_header() -> None:
    schema = _app().openapi()

    assert schema["components"]["securitySchemes"]["BearerAuth"] == {
        "type": "http",
        "description": (
            "Paste a JWT bearer token. Swagger UI sends it as "
            "`Authorization: Bearer <token>`."
        ),
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    assert schema["paths"]["/me"]["get"]["security"] == [{"BearerAuth": []}]
