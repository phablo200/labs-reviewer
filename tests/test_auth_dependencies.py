from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI
import anyio
import httpx
import jwt

from core.auth.dependencies import get_current_user
from core.auth.schemas import AuthenticatedUser
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


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/me")
    async def me(user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, str]:
        return {"id": user.id, "application_id": user.application_id}

    return app


async def _get(path: str, headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path, headers=headers)


def _configure_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "AUTH_TOKEN_VERIFIER", "jwt")
    monkeypatch.setattr(settings, "AUTH_JWT_SECRET", SECRET)
    monkeypatch.setattr(settings, "AUTH_JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(settings, "AUTH_EXPECTED_APPLICATION_ID", APPLICATION_ID)


def test_get_current_user_returns_401_without_authorization(monkeypatch) -> None:
    _configure_auth(monkeypatch)

    response = anyio.run(_get, "/me")

    assert response.status_code == 401


def test_get_current_user_returns_401_for_invalid_token(monkeypatch) -> None:
    _configure_auth(monkeypatch)

    response = anyio.run(_get, "/me", {"Authorization": "Bearer invalid-token"})

    assert response.status_code == 401


def test_get_current_user_returns_403_for_wrong_application_id(monkeypatch) -> None:
    _configure_auth(monkeypatch)
    token = _token(application_id="00000000-0000-0000-0000-000000000003")

    response = anyio.run(_get, "/me", {"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


def test_get_current_user_returns_user_for_valid_token(monkeypatch) -> None:
    _configure_auth(monkeypatch)
    token = _token()

    response = anyio.run(_get, "/me", {"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"id": "user-id", "application_id": APPLICATION_ID}
