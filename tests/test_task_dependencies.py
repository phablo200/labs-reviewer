from labs.tasks import dependencies as dependencies_module
from labs.tasks.dependencies import build_markdown_processing_dependencies


def test_build_markdown_processing_dependencies_wires_role_models(monkeypatch) -> None:
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

    class _ProcessStatusServiceStub:
        pass

    monkeypatch.setattr(
        dependencies_module.LLMConfig,
        "build_chat_model_for_agent",
        _build_model,
    )
    monkeypatch.setattr(dependencies_module, "LabPostWriterAgent", _WriterStub)
    monkeypatch.setattr(dependencies_module, "LabPostTranslatorAgent", _TranslatorStub)
    monkeypatch.setattr(dependencies_module, "LabPostMetadataAgent", _MetadataStub)
    monkeypatch.setattr(dependencies_module, "LabReviewerAgent", _ReviewerStub)
    monkeypatch.setattr(dependencies_module, "LabCodeExampleAgent", _CodeExampleStub)
    monkeypatch.setattr(
        dependencies_module,
        "ProcessStatusService",
        _ProcessStatusServiceStub,
    )

    dependencies = build_markdown_processing_dependencies()

    assert set(built_roles) == {
        "reviewer",
        "code_example",
        "post_writer",
        "metadata",
        "translator",
    }
    assert dependencies.writer_agent.llm == "llm-post_writer"
    assert dependencies.translator_agent.llm == "llm-translator"
    assert dependencies.metadata_agent.llm == "llm-metadata"
    assert dependencies.reviewer_agent.llm == "llm-reviewer"
    assert dependencies.writer_agent.blog_reviwer.llm == "llm-reviewer"
    assert dependencies.writer_agent.code_example_agent.llm == "llm-code_example"
    assert isinstance(dependencies.process_status_service, _ProcessStatusServiceStub)
