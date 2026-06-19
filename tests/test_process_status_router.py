from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import FastAPI
import anyio
import httpx

from core.auth.dependencies import get_current_user
from core.auth.schemas import AuthenticatedUser
from labs.process_status import agent_router as agent_process_router
from labs.process_status import router as process_status_router
from labs.process_status.models import AgentProcessStatus, ProcessStatus
from labs.process_status.schemas import (
    AgentProcessStatusDetailResponse,
    AgentProcessStatusSummaryResponse,
    ProcessStatusNoteResponse,
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
        status="SUCCEEDED",
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


def _note_response(process_status_id: UUID | None = None) -> ProcessStatusNoteResponse:
    return ProcessStatusNoteResponse(
        id=uuid4(),
        process_status_id=process_status_id or uuid4(),
        description="Draft note",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class _ServiceStub:
    def __init__(
        self,
        process_response: ProcessStatusResponse | None = None,
        agent_response: AgentProcessStatusDetailResponse | None = None,
        process_list_response: list[ProcessStatusResponse] | None = None,
        note_response: ProcessStatusNoteResponse | None = None,
        note_list_response: list[ProcessStatusNoteResponse] | None = None,
    ) -> None:
        self.process_response = process_response
        self.agent_response = agent_response
        self.process_list_response = process_list_response or []
        self.note_response = note_response
        self.note_list_response = note_list_response or []
        self.list_calls: list[tuple[UUID, str | None]] = []
        self.process_calls: list[tuple[UUID, UUID]] = []
        self.agent_calls: list[tuple[UUID, UUID]] = []
        self.create_writing_calls: list[UUID] = []
        self.note_calls: list[tuple[UUID, object, UUID | None]] = []
        self.file_note_calls: list[tuple[UUID, UUID, str]] = []
        self.note_list_calls: list[UUID] = []

    async def list_process_statuses(self, *, user_id: UUID, term: str | None = None):
        self.list_calls.append((user_id, term))
        return self.process_list_response

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

    async def create_writing_process_status(self, *, user_id: UUID):
        self.create_writing_calls.append(user_id)
        return ProcessStatusResponse(
            id=uuid4(),
            file="2026-06-18 10:00:00",
            status="WRITTING",
            created_at=datetime.now(timezone.utc),
            user_id=user_id,
            data=[],
        )

    async def create_or_update_note(self, *, user_id: UUID, request, note_id=None):
        self.note_calls.append((user_id, request, note_id))
        return self.note_response

    async def create_note_from_file(
        self,
        *,
        process_status_id: UUID,
        user_id: UUID,
        description: str,
    ):
        self.file_note_calls.append((process_status_id, user_id, description))
        if self.note_response is None:
            return ProcessStatusNoteResponse(
                id=uuid4(),
                process_status_id=process_status_id,
                description=description,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

        return self.note_response

    async def list_notes(self, *, user_id: UUID):
        self.note_list_calls.append(user_id)
        return self.note_list_response


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
    app.include_router(agent_process_router.agent_process_router)
    return app


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path)


async def _post(app: FastAPI, path: str, json: dict | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(path, json=json)


async def _post_file(
    app: FastAPI,
    path: str,
    filename: str,
    content: bytes,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(
            path,
            files={"file": (filename, content, "text/plain")},
        )


def test_status_endpoint_requires_authorization(monkeypatch) -> None:
    monkeypatch.setattr(process_status_router, "service", _ServiceStub())

    response = anyio.run(_get, _app(user_id=None), f"/labs/processes/{uuid4()}/status")

    assert response.status_code == 401


def test_new_process_and_note_endpoints_require_authorization(monkeypatch) -> None:
    monkeypatch.setattr(process_status_router, "service", _ServiceStub())
    process_id = uuid4()

    create_response = anyio.run(_post, _app(user_id=None), "/labs/processes/create")
    note_response = anyio.run(
        _post,
        _app(user_id=None),
        f"/labs/processes/notes/{process_id}",
        {"note": "Draft note"},
    )
    list_response = anyio.run(_get, _app(user_id=None), "/labs/processes/notes")

    assert create_response.status_code == 401
    assert note_response.status_code == 401
    assert list_response.status_code == 401


def test_list_endpoint_returns_latest_processes_for_authenticated_user(monkeypatch) -> None:
    service = _ServiceStub(process_list_response=[_process_status_response()])
    monkeypatch.setattr(process_status_router, "service", service)

    response = anyio.run(_get, _app(), "/labs/processes/")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["file"] == "notes.md"
    assert payload[0]["user_id"] == str(USER_ID)
    assert payload[0]["data"][0]["name"] == "Labs Writer"
    assert service.list_calls == [(USER_ID, None)]


def test_list_endpoint_passes_term_query_to_service(monkeypatch) -> None:
    service = _ServiceStub(process_list_response=[_process_status_response()])
    monkeypatch.setattr(process_status_router, "service", service)

    response = anyio.run(_get, _app(), "/labs/processes/?term=notes")

    assert response.status_code == 200
    assert service.list_calls == [(USER_ID, "notes")]


def test_create_process_endpoint_accepts_empty_body_and_returns_writting(
    monkeypatch,
) -> None:
    service = _ServiceStub()
    monkeypatch.setattr(process_status_router, "service", service)

    response = anyio.run(_post, _app(), "/labs/processes/create")

    assert response.status_code == 200
    payload = response.json()
    assert payload["file"] == "2026-06-18 10:00:00"
    assert payload["status"] == "WRITTING"
    assert payload["user_id"] == str(USER_ID)
    assert "data" not in payload
    assert service.create_writing_calls == [USER_ID]


def test_create_process_openapi_documents_empty_body_and_create_response() -> None:
    schema = _app().openapi()
    operation = schema["paths"]["/labs/processes/create"]["post"]

    assert "requestBody" not in operation
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/WritingProcessStatusResponse"
    }

    response_schema = schema["components"]["schemas"]["WritingProcessStatusResponse"]
    assert "data" not in response_schema["properties"]
    assert response_schema["properties"]["file"]["type"] == "string"
    assert response_schema["properties"]["status"]["const"] == "WRITTING"


def test_note_create_endpoint_returns_only_note_fields(monkeypatch) -> None:
    process_id = uuid4()
    note_response = _note_response(process_status_id=process_id)
    service = _ServiceStub(note_response=note_response)
    monkeypatch.setattr(process_status_router, "service", service)

    response = anyio.run(
        _post,
        _app(),
        f"/labs/processes/notes/{process_id}",
        {"note": "  Draft note  "},
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "id",
        "process_status_id",
        "description",
        "created_at",
        "updated_at",
    }
    assert payload["description"] == "Draft note"
    assert service.note_calls[0][0] == USER_ID
    assert service.note_calls[0][1].process_status_id == process_id
    assert service.note_calls[0][1].note == "Draft note"
    assert service.note_calls[0][2] is None


def test_note_create_openapi_uses_process_status_id_path() -> None:
    schema = _app().openapi()

    assert "/labs/processes/notes/{process_status_id}" in schema["paths"]
    operation = schema["paths"]["/labs/processes/notes/{process_status_id}"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ProcessStatusNoteBodyRequest"
    }
    assert "post" not in schema["paths"]["/labs/processes/notes"]


def test_note_update_endpoint_passes_note_id_and_returns_note(monkeypatch) -> None:
    process_id = uuid4()
    note_id = uuid4()
    note_response = _note_response(process_status_id=process_id)
    service = _ServiceStub(note_response=note_response)
    monkeypatch.setattr(process_status_router, "service", service)

    response = anyio.run(
        _post,
        _app(),
        f"/labs/processes/notes/{process_id}?id={note_id}",
        {"note": "Updated note"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "id",
        "process_status_id",
        "description",
        "created_at",
        "updated_at",
    }
    assert service.note_calls == [
        (USER_ID, service.note_calls[0][1], note_id),
    ]
    assert service.note_calls[0][1].process_status_id == process_id


def test_note_list_endpoint_returns_authenticated_user_notes(monkeypatch) -> None:
    first = _note_response()
    second = _note_response()
    service = _ServiceStub(note_list_response=[first, second])
    monkeypatch.setattr(process_status_router, "service", service)

    response = anyio.run(_get, _app(), "/labs/processes/notes")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == [str(first.id), str(second.id)]
    assert service.note_list_calls == [USER_ID]


def test_file_note_endpoint_stores_raw_uploaded_note(monkeypatch) -> None:
    service = _ServiceStub()
    monkeypatch.setattr(process_status_router, "service", service)
    process_id = uuid4()

    response = anyio.run(
        _post_file,
        _app(),
        f"/labs/processes/files-note/{process_id}",
        "NOTES.MD",
        b"  # Raw note\n",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["process_status_id"] == str(process_id)
    assert payload["description"] == "  # Raw note\n"
    assert service.file_note_calls == [(process_id, USER_ID, "  # Raw note\n")]


def test_file_note_openapi_is_documented_on_process_status_router() -> None:
    schema = _app().openapi()

    assert "/labs/processes/files-note/{process_status_id}" in schema["paths"]
    operation = schema["paths"]["/labs/processes/files-note/{process_status_id}"]["post"]
    assert operation["tags"] == ["Process Status"]
    assert "multipart/form-data" in operation["requestBody"]["content"]


def test_note_endpoints_return_404_for_missing_or_unauthorized_resource(
    monkeypatch,
) -> None:
    service = _ServiceStub(note_response=None)
    monkeypatch.setattr(process_status_router, "service", service)

    response = anyio.run(
        _post,
        _app(),
        f"/labs/processes/notes/{uuid4()}",
        {"note": "Draft note"},
    )

    assert response.status_code == 404


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
    assert payload["status"] == "SUCCEEDED"
    assert payload["user_id"] == str(USER_ID)
    assert payload["data"][0]["name"] == "Labs Writer"
    assert "result" not in payload["data"][0]
    assert "result" not in payload["data"][0]["children"][0]


def test_agent_process_endpoint_returns_detail_with_result(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_process_router,
        "service",
        _ServiceStub(agent_response=_agent_process_detail_response()),
    )

    response = anyio.run(_get, _app(), f"/labs/agent-process/{uuid4()}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"] == "MARKDOWN_CONTENT"
    assert "result" not in payload["children"][0]


def test_agent_process_endpoint_returns_404_for_missing_agent_process(monkeypatch) -> None:
    monkeypatch.setattr(agent_process_router, "service", _ServiceStub())

    response = anyio.run(_get, _app(), f"/labs/agent-process/{uuid4()}")

    assert response.status_code == 404
