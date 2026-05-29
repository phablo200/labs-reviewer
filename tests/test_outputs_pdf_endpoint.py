from fastapi import FastAPI
import anyio
import httpx

from labs import router as lab_router


def test_get_outputs_pdf_returns_service_payload(monkeypatch) -> None:
    app = FastAPI()
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
