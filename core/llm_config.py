import os
from enum import Enum
import logging
from typing import Callable

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from core.contants import (
    DEFAULT_GROQ_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_TEMPERATURE,
    LLM,
    LLM_MODELS,
)

load_dotenv()
logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    GROQ = "groq"
    OPENAI = "openai"


class AgentRole(str, Enum):
    POST_WRITER = "post_writer"
    CODE_EXAMPLE = "code_example"
    REVIEWER = "reviewer"
    METADATA = "metadata"
    TRANSLATOR = "translator"


class LLMConfig:
    ROLE_DEFAULT_PROVIDER: dict[AgentRole, LLMProvider] = {
        AgentRole.POST_WRITER: LLMProvider.OPENAI,
        AgentRole.CODE_EXAMPLE: LLMProvider.GROQ,
        AgentRole.REVIEWER: LLMProvider.GROQ,
        AgentRole.METADATA: LLMProvider.GROQ,
        AgentRole.TRANSLATOR: LLMProvider.OPENAI,
    }

    @staticmethod
    def _build_groq_chat() -> BaseChatModel:
        model_name = LLMConfig._provider_default_model(LLMProvider.GROQ)
        temperature = LLMConfig._provider_default_temperature(LLMProvider.GROQ)
        api_key = os.getenv("GROQ_API_KEY")
        return ChatGroq(
            model=model_name,
            temperature=temperature,
            api_key=api_key,
        )

    @staticmethod
    def _build_openai_chat() -> BaseChatModel:
        model_name = LLMConfig._provider_default_model(LLMProvider.OPENAI)
        temperature = LLMConfig._provider_default_temperature(LLMProvider.OPENAI)
        api_key = os.getenv("OPENAI_API_KEY")
        return ChatOpenAI(
            model=model_name,
            temperature=temperature,
            openai_api_key=api_key,
        )

    MODEL_BUILDERS: dict[LLMProvider, Callable[[], BaseChatModel]] = {
        LLMProvider.GROQ: _build_groq_chat.__func__,
        LLMProvider.OPENAI: _build_openai_chat.__func__,
    }

    @classmethod
    def build_chat_model(cls, provider: LLMProvider = LLMProvider.GROQ) -> BaseChatModel:
        return cls.MODEL_BUILDERS[provider]()

    @staticmethod
    def _provider_builtin_default_model(provider: LLMProvider) -> str:
        if provider == LLMProvider.OPENAI:
            return DEFAULT_OPENAI_MODEL
        return DEFAULT_GROQ_MODEL

    @classmethod
    def _provider_default_model(cls, provider: LLMProvider) -> str:
        fallback = cls._provider_builtin_default_model(provider)
        if provider == LLMProvider.OPENAI:
            return os.getenv("OPENAI_MODEL", fallback).strip() or fallback
        return os.getenv("GROQ_MODEL", fallback).strip() or fallback

    @staticmethod
    def _provider_default_temperature(provider: LLMProvider) -> float:
        raw = (
            os.getenv("OPENAI_TEMPERATURE", str(DEFAULT_TEMPERATURE))
            if provider == LLMProvider.OPENAI
            else os.getenv("GROQ_TEMPERATURE", str(DEFAULT_TEMPERATURE))
        )
        try:
            value = float(raw)
        except (TypeError, ValueError):
            logger.warning(
                "llm_config: invalid global temperature '%s' for provider '%s'; using default=%s",
                raw,
                provider.value,
                DEFAULT_TEMPERATURE,
            )
            return DEFAULT_TEMPERATURE
        if not 0 <= value <= 1:
            logger.warning(
                "llm_config: global temperature out of range for provider '%s'; using default=%s",
                provider.value,
                DEFAULT_TEMPERATURE,
            )
            return DEFAULT_TEMPERATURE
        return value

    @classmethod
    def _resolve_provider(cls, role: AgentRole) -> LLMProvider:
        key = f"LLM_{role.value.upper()}_PROVIDER"
        raw_provider = os.getenv(key, cls.ROLE_DEFAULT_PROVIDER[role].value).strip().lower()
        try:
            return LLMProvider(raw_provider)
        except ValueError:
            fallback = cls.ROLE_DEFAULT_PROVIDER[role]
            logger.warning(
                "llm_config: invalid provider '%s' for role '%s'; using '%s'",
                raw_provider,
                role.value,
                fallback.value,
            )
            return fallback

    @classmethod
    def _resolve_model(cls, role: AgentRole, provider: LLMProvider) -> str:
        key = f"LLM_{role.value.upper()}_MODEL"
        role_model = os.getenv(key, "").strip()
        candidate = role_model or cls._provider_default_model(provider)
        allowed = LLM_MODELS[LLM(provider.value)]
        if candidate not in allowed:
            provider_default = cls._provider_default_model(provider)
            fallback = (
                provider_default
                if provider_default in allowed
                else cls._provider_builtin_default_model(provider)
            )
            logger.warning(
                "llm_config: model '%s' invalid for provider '%s' (role=%s); using '%s'",
                candidate,
                provider.value,
                role.value,
                fallback,
            )
            return fallback
        return candidate

    @classmethod
    def _resolve_temperature(cls, role: AgentRole, provider: LLMProvider) -> float:
        key = f"LLM_{role.value.upper()}_TEMPERATURE"
        raw = os.getenv(key, "").strip()
        if not raw:
            return cls._provider_default_temperature(provider)
        try:
            value = float(raw)
        except ValueError:
            logger.warning(
                "llm_config: invalid temperature '%s' for role '%s'; using provider default",
                raw,
                role.value,
            )
            return cls._provider_default_temperature(provider)
        if not 0 <= value <= 1:
            logger.warning(
                "llm_config: temperature out of range for role '%s'; using provider default",
                role.value,
            )
            return cls._provider_default_temperature(provider)
        return value

    @classmethod
    def build_chat_model_for_agent(cls, agent_role: AgentRole) -> BaseChatModel:
        provider = cls._resolve_provider(agent_role)
        model = cls._resolve_model(agent_role, provider)
        temperature = cls._resolve_temperature(agent_role, provider)

        if provider == LLMProvider.OPENAI:
            return ChatOpenAI(
                model=model,
                temperature=temperature,
                openai_api_key=os.getenv("OPENAI_API_KEY"),
            )
        return ChatGroq(
            model=model,
            temperature=temperature,
            api_key=os.getenv("GROQ_API_KEY"),
        )
