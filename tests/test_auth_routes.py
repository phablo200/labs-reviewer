from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
import anyio
import httpx
import jwt

from core.config import settings
from labs import router as lab_router


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
    app.include_router(lab_router.router)
    app.include_router(lab_router.outputs_router)
    return app


async def _get(path: str, headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path, headers=headers)


async def _post_review(headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(
            "/labs/review",
            headers=headers,
            files={"file": ("notes.md", b"# Notes", "text/markdown")},
        )


class _ServiceStub:
    def enqueue_markdown_organization(self, **_kwargs):
        return {
            "message": "Processing started.",
            "output_file": "public/markdown/notes_reviewd.md",
        }

    def list_markdown_outputs(self):
        return {
            "items": [{"filename": "post.md", "path": "public/markdown/post.md"}],
            "count": 1,
        }

    def list_pdf_outputs(self):
        return {
            "items": [{"filename": "post.pdf", "path": "public/pdf/post.pdf"}],
            "count": 1,
        }


def test_outputs_pdf_requires_authorization(monkeypatch) -> None:
    _configure_auth(monkeypatch)

    response = anyio.run(_get, "/outputs/pdf")

    assert response.status_code == 401


def test_outputs_pdf_rejects_malformed_token(monkeypatch) -> None:
    _configure_auth(monkeypatch)

    response = anyio.run(_get, "/outputs/pdf", {"Authorization": "Bearer invalid-token"})

    assert response.status_code == 401


def test_outputs_pdf_rejects_wrong_application_id(monkeypatch) -> None:
    _configure_auth(monkeypatch)
    token = _token(application_id="00000000-0000-0000-0000-000000000003")

    response = anyio.run(_get, "/outputs/pdf", {"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


def test_outputs_pdf_accepts_valid_token(monkeypatch) -> None:
    _configure_auth(monkeypatch)
    monkeypatch.setattr(lab_router, "service", _ServiceStub())
    token = _token()

    response = anyio.run(_get, "/outputs/pdf", {"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "items": [{"filename": "post.pdf", "path": "public/pdf/post.pdf"}],
        "count": 1,
    }


def test_outputs_markdown_accepts_valid_token(monkeypatch) -> None:
    _configure_auth(monkeypatch)
    monkeypatch.setattr(lab_router, "service", _ServiceStub())
    token = _token()

    response = anyio.run(_get, "/outputs/makdown", {"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "items": [{"filename": "post.md", "path": "public/markdown/post.md"}],
        "count": 1,
    }


def test_labs_review_accepts_valid_token(monkeypatch) -> None:
    _configure_auth(monkeypatch)
    monkeypatch.setattr(lab_router, "service", _ServiceStub())
    token = _token()

    response = anyio.run(_post_review, {"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "message": "Processing started.",
        "output_file": "public/markdown/notes_reviewd.md",
    }
