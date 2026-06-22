from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import FastAPI
import anyio
import httpx
import jwt

from core.config import settings
from labs.agents import router as lab_router
from labs.process_status.routers import process_status_router


SECRET = "test-secret"
APPLICATION_ID = "00000000-0000-0000-0000-000000000002"
USER_ID = "11111111-1111-1111-1111-111111111111"


def _token(
    *,
    secret: str = SECRET,
    user_id: str = USER_ID,
    application_id: str = APPLICATION_ID,
    expires_delta: timedelta = timedelta(minutes=5),
) -> str:
    return jwt.encode(
        {
            "sub": user_id,
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
    app.include_router(process_status_router.router)
    return app


async def _get(path: str, headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path, headers=headers)


async def _post_review(headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(
            "/labs/review/00000000-0000-0000-0000-000000000001",
            headers=headers,
        )


async def _post_old_review(headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(
            "/labs/review",
            headers=headers,
            files={"file": ("notes.md", b"# Notes", "text/markdown")},
        )


async def _post_file_note(
    filename: str,
    content: bytes,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(
            "/labs/processes/files-note/00000000-0000-0000-0000-000000000001",
            headers=headers,
            files={"file": (filename, content, "text/plain")},
        )


class _ServiceStub:
    def __init__(self, *, note_response=None) -> None:
        self.review_calls = []
        self.note_calls = []
        self.note_response = note_response

    async def enqueue_markdown_organization_for_process(self, **kwargs):
        self.review_calls.append(kwargs)
        return {
            "message": "Processing started.",
            "process_id": "00000000-0000-0000-0000-000000000001",
            "output_file": "public/markdown/notes_reviewd.md",
        }

    async def create_note_from_file(self, **kwargs):
        self.note_calls.append(kwargs)
        if self.note_response is None:
            return {
                "id": str(uuid4()),
                "process_status_id": str(kwargs["process_status_id"]),
                "description": kwargs["description"],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        return self.note_response

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
    service = _ServiceStub()
    monkeypatch.setattr(lab_router, "service", service)
    token = jwt.encode(
        {
            "sub": USER_ID,
            "email": "user@example.com",
            "profile_id": "profile-id",
            "application_id": APPLICATION_ID,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        SECRET,
        algorithm="HS256",
    )

    response = anyio.run(_post_review, {"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "message": "Processing started.",
        "process_id": "00000000-0000-0000-0000-000000000001",
        "output_file": "public/markdown/notes_reviewd.md",
    }
    assert service.review_calls[0]["process_status_id"] == UUID(
        "00000000-0000-0000-0000-000000000001"
    )


def test_labs_review_old_route_is_removed(monkeypatch) -> None:
    _configure_auth(monkeypatch)
    monkeypatch.setattr(lab_router, "service", _ServiceStub())
    token = _token()

    response = anyio.run(_post_old_review, {"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


def test_file_note_accepts_md_and_txt_uploads(monkeypatch) -> None:
    _configure_auth(monkeypatch)
    service = _ServiceStub()
    monkeypatch.setattr(process_status_router, "service", service)
    token = _token()

    md_response = anyio.run(
        _post_file_note,
        "notes.md",
        b"# Notes",
        {"Authorization": f"Bearer {token}"},
    )
    txt_response = anyio.run(
        _post_file_note,
        "NOTES.TXT",
        b"Plain notes",
        {"Authorization": f"Bearer {token}"},
    )

    assert md_response.status_code == 200
    assert md_response.json()["description"] == "# Notes"
    assert txt_response.status_code == 200
    assert txt_response.json()["description"] == "Plain notes"
    assert [call["description"] for call in service.note_calls] == [
        "# Notes",
        "Plain notes",
    ]


def test_file_note_requires_authorization(monkeypatch) -> None:
    _configure_auth(monkeypatch)
    monkeypatch.setattr(process_status_router, "service", _ServiceStub())

    response = anyio.run(
        _post_file_note,
        "notes.md",
        b"# Notes",
    )

    assert response.status_code == 401


def test_file_note_rejects_invalid_uploads(monkeypatch) -> None:
    _configure_auth(monkeypatch)
    monkeypatch.setattr(process_status_router, "service", _ServiceStub())
    token = _token()
    headers = {"Authorization": f"Bearer {token}"}

    unsupported = anyio.run(
        _post_file_note,
        "notes.pdf",
        b"# Notes",
        headers,
    )
    invalid_utf8 = anyio.run(
        _post_file_note,
        "notes.md",
        b"\xff",
        headers,
    )
    empty = anyio.run(
        _post_file_note,
        "notes.md",
        b"",
        headers,
    )
    oversized = anyio.run(
        _post_file_note,
        "notes.txt",
        b"x" * ((10 * 1024) + 1),
        headers,
    )

    assert unsupported.status_code == 400
    assert invalid_utf8.status_code == 400
    assert empty.status_code == 422
    assert oversized.status_code == 422


def test_file_note_returns_404_when_process_is_missing(monkeypatch) -> None:
    _configure_auth(monkeypatch)
    monkeypatch.setattr(process_status_router, "service", _ServiceStub(note_response=None))
    token = _token()

    class _MissingProcessService(_ServiceStub):
        async def create_note_from_file(self, **kwargs):
            self.note_calls.append(kwargs)
            return None

    service = _MissingProcessService()
    monkeypatch.setattr(process_status_router, "service", service)

    response = anyio.run(
        _post_file_note,
        "notes.md",
        b"# Notes",
        {"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
