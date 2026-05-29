"""Blog Reviewer agent implementation."""

import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from core.llm_config import AgentRole, LLMConfig

from .helper import parse_markdown_response
from .prompts import LabReviewerPrompt
from .schema import (
    LabReviewerRequest,
    LabReviewerResponse,
)


class LabReviewerAgent:
    """Agent responsible for revising blog posts in Markdown."""

    def __init__(self, llm: BaseChatModel | None = None) -> None:
        self.logger = logging.getLogger(__name__)
        self.agent_name = AgentRole.REVIEWER
        self.llm = llm or LLMConfig.build_chat_model_for_agent(AgentRole.REVIEWER)

    def revise(self, request: LabReviewerRequest) -> LabReviewerResponse:
        system_prompt = LabReviewerPrompt.build_system_prompt()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=request.content),
        ]

        try:
            response = self.llm.invoke(messages)
        except Exception:
            self.logger.exception(
                "agent=%s | revision generation failed, using original content",
                self.agent_name,
            )
            return LabReviewerResponse(
                revised_post=request.content,
                errors_found=[],
                improvement_tips=[],
                next_revision_checklist=[],
            )

        raw_text = str(getattr(response, "content", "")).strip()
        return parse_markdown_response(raw_text, request.content)
