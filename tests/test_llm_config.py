import core.llm_config as llm_config
from core.contants import DEFAULT_OPENAI_MODEL
from core.llm_config import AgentRole, LLMProvider


class _ModelStub:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_build_chat_model_for_agent_uses_role_specific_values(monkeypatch) -> None:
    monkeypatch.setattr(llm_config, "ChatOpenAI", _ModelStub)
    monkeypatch.setattr(llm_config, "ChatGroq", _ModelStub)

    monkeypatch.setenv("LLM_POST_WRITER_PROVIDER", "openai")
    monkeypatch.setenv("LLM_POST_WRITER_MODEL", "gpt-4o")
    monkeypatch.setenv("LLM_POST_WRITER_TEMPERATURE", "0.42")

    model = llm_config.LLMConfig.build_chat_model_for_agent(AgentRole.POST_WRITER)

    assert model.kwargs["model"] == "gpt-4o"
    assert model.kwargs["temperature"] == 0.42


def test_build_chat_model_for_agent_falls_back_to_global_model(monkeypatch) -> None:
    monkeypatch.setattr(llm_config, "ChatOpenAI", _ModelStub)
    monkeypatch.setattr(llm_config, "ChatGroq", _ModelStub)

    monkeypatch.delenv("LLM_METADATA_MODEL", raising=False)
    monkeypatch.setenv("LLM_METADATA_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

    model = llm_config.LLMConfig.build_chat_model_for_agent(AgentRole.METADATA)
    assert model.kwargs["model"] == "gpt-4o-mini"


def test_resolve_model_invalid_role_model_fallback(monkeypatch) -> None:
    monkeypatch.setenv("LLM_REVIEWER_PROVIDER", "groq")
    monkeypatch.setenv("LLM_REVIEWER_MODEL", "gpt-4o")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.1-8b-instant")

    resolved = llm_config.LLMConfig._resolve_model(AgentRole.REVIEWER, LLMProvider.GROQ)
    assert resolved == "llama-3.1-8b-instant"


def test_resolve_model_blank_openai_env_falls_back_to_builtin(monkeypatch) -> None:
    monkeypatch.setenv("LLM_TRANSLATOR_PROVIDER", "openai")
    monkeypatch.setenv("LLM_TRANSLATOR_MODEL", "")
    monkeypatch.setenv("OPENAI_MODEL", "")

    resolved = llm_config.LLMConfig._resolve_model(
        AgentRole.TRANSLATOR, LLMProvider.OPENAI
    )

    assert resolved == DEFAULT_OPENAI_MODEL


def test_resolve_model_invalid_global_env_falls_back_to_builtin(monkeypatch) -> None:
    monkeypatch.setenv("LLM_TRANSLATOR_PROVIDER", "openai")
    monkeypatch.setenv("LLM_TRANSLATOR_MODEL", "not-a-real-openai-model")
    monkeypatch.setenv("OPENAI_MODEL", "also-invalid")

    resolved = llm_config.LLMConfig._resolve_model(
        AgentRole.TRANSLATOR, LLMProvider.OPENAI
    )

    assert resolved == DEFAULT_OPENAI_MODEL
