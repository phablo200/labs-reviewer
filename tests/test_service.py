from pathlib import Path

from fastapi import BackgroundTasks

import labs.agents.service as service_module
from labs.agents.service import LabPostService


def test_enqueue_markdown_organization_uses_public_markdowns_path() -> None:
    service = LabPostService.__new__(LabPostService)
    service.markdown_output_dir = Path("public/markdown")
    service.pdf_output_dir = Path("public/pdf")
    service.writer_agent = object()
    service.translator_agent = object()
    service.metadata_agent = object()

    result = service.enqueue_markdown_organization(
        background_tasks=BackgroundTasks(),
        filename="example.md",
        context="# Notes",
    )

    assert "public/markdown/example_reviewd.md" in result["output_file"]


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

    monkeypatch.setattr(service_module.LLMConfig, "build_chat_model_for_agent", _build_model)
    monkeypatch.setattr(service_module, "LabPostWriterAgent", _WriterStub)
    monkeypatch.setattr(service_module, "LabPostTranslatorAgent", _TranslatorStub)
    monkeypatch.setattr(service_module, "LabPostMetadataAgent", _MetadataStub)
    monkeypatch.setattr(service_module, "LabReviewerAgent", _ReviewerStub)
    monkeypatch.setattr(service_module, "LabCodeExampleAgent", _CodeExampleStub)

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
