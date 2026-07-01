from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import anyio
from fastapi import BackgroundTasks
import pytest

from core.tasks.exceptions import TaskDispatchEnqueueError
import labs.agents.service as service_module
from labs.agents.service import LabPostService


def test_enqueue_markdown_organization_uses_public_markdowns_path() -> None:
    service = LabPostService.__new__(LabPostService)
    service.markdown_output_dir = Path("public/markdown")
    service.pdf_output_dir = Path("public/pdf")
    service.writer_agent = object()
    service.translator_agent = object()
    service.metadata_agent = object()
    service.process_status_service = _ProcessStatusServiceStub()
    service.markdown_dispatcher = _DispatcherStub()

    async def _enqueue():
        return await service.enqueue_markdown_organization(
            background_tasks=BackgroundTasks(),
            filename="example.md",
            context="# Notes",
            user_id=UUID("11111111-1111-1111-1111-111111111111"),
        )

    result = anyio.run(_enqueue)

    assert "public/markdown/example_reviewd.md" in result["output_file"]
    assert result["process_id"] == "00000000-0000-0000-0000-000000000001"
    assert service.markdown_dispatcher.jobs[0].context == "# Notes"
    assert str(service.markdown_dispatcher.jobs[0].output_path).endswith(
        "public/markdown/example_reviewd.md"
    )
    assert (
        str(service.markdown_dispatcher.jobs[0].process_status_id)
        == "00000000-0000-0000-0000-000000000001"
    )


def test_enqueue_markdown_organization_returns_error_when_dispatch_fails() -> None:
    service = LabPostService.__new__(LabPostService)
    service.markdown_output_dir = Path("public/markdown")
    service.pdf_output_dir = Path("public/pdf")
    service.writer_agent = object()
    service.translator_agent = object()
    service.metadata_agent = object()
    service.process_status_service = _ProcessStatusServiceStub()
    service.markdown_dispatcher = _FailingDispatcherStub()

    async def _enqueue():
        return await service.enqueue_markdown_organization(
            background_tasks=BackgroundTasks(),
            filename="example.md",
            context="# Notes",
            user_id=UUID("11111111-1111-1111-1111-111111111111"),
        )

    with pytest.raises(service_module.HTTPException) as exc_info:
        anyio.run(_enqueue)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Failed to enqueue markdown processing job."


def test_enqueue_markdown_organization_for_process_uses_existing_process_notes() -> None:
    process_id = UUID("00000000-0000-0000-0000-000000000001")
    service = LabPostService.__new__(LabPostService)
    service.markdown_output_dir = Path("public/markdown")
    service.process_status_service = _ProcessStatusServiceStub(
        process_status=SimpleNamespace(id=process_id, file="daily notes.txt"),
        notes=[
            SimpleNamespace(description="# First note"),
            SimpleNamespace(description="Second note"),
        ],
    )
    service.markdown_dispatcher = _DispatcherStub()

    async def _enqueue():
        return await service.enqueue_markdown_organization_for_process(
            background_tasks=BackgroundTasks(),
            process_status_id=process_id,
            user_id=UUID("11111111-1111-1111-1111-111111111111"),
        )

    result = anyio.run(_enqueue)

    assert result["process_id"] == str(process_id)
    assert result["output_file"] == "public/markdown/daily_notes_reviewd.md"
    assert service.markdown_dispatcher.jobs[0].process_status_id == process_id
    assert service.markdown_dispatcher.jobs[0].context == "# First note\n\nSecond note"
    assert service.process_status_service.created_for_review_calls == []


def test_enqueue_markdown_organization_for_process_uses_fallback_output_name() -> None:
    process_id = UUID("00000000-0000-0000-0000-000000000001")
    service = LabPostService.__new__(LabPostService)
    service.markdown_output_dir = Path("public/markdown")
    service.process_status_service = _ProcessStatusServiceStub(
        process_status=SimpleNamespace(id=process_id, file=None),
        notes=[SimpleNamespace(description="# Notes")],
    )
    service.markdown_dispatcher = _DispatcherStub()

    async def _enqueue():
        return await service.enqueue_markdown_organization_for_process(
            background_tasks=BackgroundTasks(),
            process_status_id=process_id,
            user_id=UUID("11111111-1111-1111-1111-111111111111"),
        )

    result = anyio.run(_enqueue)

    assert result["output_file"] == f"public/markdown/process_{process_id}.md"


def test_enqueue_markdown_organization_for_process_returns_404_when_process_missing() -> None:
    service = LabPostService.__new__(LabPostService)
    service.markdown_output_dir = Path("public/markdown")
    service.process_status_service = _ProcessStatusServiceStub(process_notes=None)
    service.markdown_dispatcher = _DispatcherStub()

    async def _enqueue():
        return await service.enqueue_markdown_organization_for_process(
            background_tasks=BackgroundTasks(),
            process_status_id=UUID("00000000-0000-0000-0000-000000000001"),
            user_id=UUID("11111111-1111-1111-1111-111111111111"),
        )

    with pytest.raises(service_module.HTTPException) as exc_info:
        anyio.run(_enqueue)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Process status not found."


def test_enqueue_markdown_organization_for_process_rejects_process_without_notes() -> None:
    service = LabPostService.__new__(LabPostService)
    service.markdown_output_dir = Path("public/markdown")
    service.process_status_service = _ProcessStatusServiceStub(notes=[])
    service.markdown_dispatcher = _DispatcherStub()

    async def _enqueue():
        return await service.enqueue_markdown_organization_for_process(
            background_tasks=BackgroundTasks(),
            process_status_id=UUID("00000000-0000-0000-0000-000000000001"),
            user_id=UUID("11111111-1111-1111-1111-111111111111"),
        )

    with pytest.raises(service_module.HTTPException) as exc_info:
        anyio.run(_enqueue)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Process status has no notes to review."


def test_enqueue_markdown_organization_for_process_returns_error_when_dispatch_fails() -> None:
    service = LabPostService.__new__(LabPostService)
    service.markdown_output_dir = Path("public/markdown")
    service.process_status_service = _ProcessStatusServiceStub(
        notes=[SimpleNamespace(description="# Notes")],
    )
    service.markdown_dispatcher = _FailingDispatcherStub()

    async def _enqueue():
        return await service.enqueue_markdown_organization_for_process(
            background_tasks=BackgroundTasks(),
            process_status_id=UUID("00000000-0000-0000-0000-000000000001"),
            user_id=UUID("11111111-1111-1111-1111-111111111111"),
        )

    with pytest.raises(service_module.HTTPException) as exc_info:
        anyio.run(_enqueue)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Failed to enqueue markdown processing job."


class _ProcessStatus:
    id = UUID("00000000-0000-0000-0000-000000000001")
    file = "notes.md"


class _ProcessStatusServiceStub:
    def __init__(
        self,
        *,
        process_status=None,
        notes=None,
        process_notes="default",
    ) -> None:
        self.created_for_review_calls = []
        self.process_status = process_status or _ProcessStatus()
        self.notes = (
            [SimpleNamespace(description="# Notes")]
            if notes is None
            else notes
        )
        self.process_notes = process_notes

    async def create_process_for_review(self, **_kwargs):
        self.created_for_review_calls.append(_kwargs)
        return _ProcessStatus()

    async def get_process_notes(self, **_kwargs):
        if self.process_notes is None:
            return None

        return SimpleNamespace(
            process_status=self.process_status,
            notes=self.notes,
        )


class _DispatcherStub:
    def __init__(self) -> None:
        self.jobs = []

    async def enqueue(self, *, job, background_tasks=None):
        self.jobs.append(job)


class _FailingDispatcherStub:
    async def enqueue(self, *, job, background_tasks=None):
        raise TaskDispatchEnqueueError("boom")


def test_service_initialization_wires_role_models(monkeypatch) -> None:
    built_roles: list[str] = []

    def _build_model(role):
        built_roles.append(role.value)
        return f"llm-{role.value}"

    class _WriterStub:
        def __init__(self, llm=None):
            self.llm = llm
            self.blog_reviwer = None
            self.code_example_agent = None

    class _TranslatorStub:
        def __init__(self, llm=None):
            self.llm = llm

    class _MetadataStub:
        def __init__(self, llm=None):
            self.llm = llm

    class _ReviewerStub:
        def __init__(self, llm=None):
            self.llm = llm

    class _CodeExampleStub:
        def __init__(self, llm=None):
            self.llm = llm

    monkeypatch.setattr(
        service_module,
        "build_markdown_dispatcher",
        lambda **_kwargs: _DispatcherStub(),
    )
    monkeypatch.setattr(
        "labs.tasks.dependencies.LLMConfig.build_chat_model_for_agent",
        _build_model,
    )
    monkeypatch.setattr("labs.tasks.dependencies.LabPostWriterAgent", _WriterStub)
    monkeypatch.setattr("labs.tasks.dependencies.LabPostTranslatorAgent", _TranslatorStub)
    monkeypatch.setattr("labs.tasks.dependencies.LabPostMetadataAgent", _MetadataStub)
    monkeypatch.setattr("labs.tasks.dependencies.LabReviewerAgent", _ReviewerStub)
    monkeypatch.setattr("labs.tasks.dependencies.LabCodeExampleAgent", _CodeExampleStub)

    service = LabPostService()

    assert set(built_roles) == {
        "reviewer",
        "code_example",
        "post_writer",
        "metadata",
        "translator",
    }
    assert service.writer_agent.llm == "llm-post_writer"
    assert service.translator_agent.llm == "llm-translator"
    assert service.metadata_agent.llm == "llm-metadata"
    assert service.reviewer_agent.llm == "llm-reviewer"
    assert service.writer_agent.blog_reviwer.llm == "llm-reviewer"
    assert service.writer_agent.code_example_agent.llm == "llm-code_example"
    assert isinstance(service.markdown_dispatcher, _DispatcherStub)
