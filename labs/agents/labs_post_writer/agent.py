"""Blog Post Writer agent implementation."""

import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from labs.agents.labs_code_example.agent import LabCodeExampleAgent
from labs.agents.labs_code_example.schema import LabCodeExampleRequest
from labs.agents.labs_reviewer.agent import LabReviewerAgent
from labs.agents.labs_reviewer.schema import LabReviewerRequest
from core.llm_config import AgentRole, LLMConfig

from .helper import build_code_examples_context, enrich_context_with_repositories
from .prompts import LabPostWriterPrompt
from .schema import LabPostWriterRequest, LabPostWriterResponse


class LabPostWriterAgent:
    """Agent responsible for turning sketch notes into structured blog posts."""

    def __init__(self, llm: BaseChatModel | None = None) -> None:
        """Initialize the chat model used by the agent."""
        self.logger = logging.getLogger(__name__)
        self.agent_name = AgentRole.POST_WRITER
        self.llm = llm or LLMConfig.build_chat_model_for_agent(AgentRole.POST_WRITER)
        self.blog_reviwer = LabReviewerAgent()
        self.code_example_agent = LabCodeExampleAgent()

    def organize_notes(self, request: LabPostWriterRequest) -> LabPostWriterResponse:
        """Transform raw notes into a reviewed markdown blog post."""
        self.logger.info("agent=%s | starting organize_notes pipeline", self.agent_name)
        enriched_context = enrich_context_with_repositories(request.context, self.logger)
        examples_response = self.code_example_agent.extract_examples(
            LabCodeExampleRequest(
                notes_context=request.context,
                max_examples=3,
            )
        )
        for warning in examples_response.warnings:
            self.logger.warning(
                "agent=%s | code example warning: %s", self.agent_name, warning
            )

        code_examples_context = build_code_examples_context(examples_response)
        final_context = enriched_context
        if code_examples_context:
            final_context = f"{enriched_context}\n\n{code_examples_context}"
        system_prompt = LabPostWriterPrompt.build_system_prompt()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=final_context),
        ]

        self.logger.info("agent=%s | generating initial draft", self.agent_name)
        response = self.llm.invoke(messages)
        current_markdown = str(getattr(response, "content", "")).strip()
        if not current_markdown:
            self.logger.warning(
                "agent=%s | initial draft empty, using fallback message",
                self.agent_name,
            )
            current_markdown = "Unable to generate blog content from the provided notes."
        else:
            self.logger.info(
                "agent=%s | initial draft generated (chars=%s)",
                self.agent_name,
                len(current_markdown),
            )

        # Run 3 full review/improvement cycles using both agents.
        for iteration in range(1, 4):
            self.logger.info(
                "agent=%s | cycle %s/3 - requesting revision",
                self.agent_name,
                iteration,
            )
            try:
                revised = self.blog_reviwer.revise(
                    LabReviewerRequest(content=current_markdown)
                )
                self.logger.info(
                    (
                        "agent=%s | cycle %s/3 - revision received "
                        "(errors=%s, tips=%s, checklist=%s)"
                    ),
                    self.agent_name,
                    iteration,
                    len(revised.errors_found),
                    len(revised.improvement_tips),
                    len(revised.next_revision_checklist),
                )
            except Exception:
                self.logger.exception(
                    "agent=%s | cycle %s/3 - revision failed, stopping loop",
                    self.agent_name,
                    iteration,
                )
                break

            improvement_prompt = LabPostWriterPrompt.build_improvement_prompt(
                current_markdown=current_markdown,
                revised_post=revised.revised_post,
                errors_found=revised.errors_found,
                improvement_tips=revised.improvement_tips,
                next_revision_checklist=revised.next_revision_checklist,
            )

            self.logger.info(
                "agent=%s | cycle %s/3 - improving post", self.agent_name, iteration
            )
            improved_response = self.llm.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=improvement_prompt),
                ]
            )
            improved_markdown = str(getattr(improved_response, "content", "")).strip()
            if improved_markdown:
                current_markdown = improved_markdown
                self.logger.info(
                    "agent=%s | cycle %s/3 - improvement applied (chars=%s)",
                    self.agent_name,
                    iteration,
                    len(current_markdown),
                )
            else:
                current_markdown = revised.revised_post.strip() or current_markdown
                self.logger.warning(
                    (
                        "agent=%s | cycle %s/3 - empty improved response, "
                        "using revised fallback (chars=%s)"
                    ),
                    self.agent_name,
                    iteration,
                    len(current_markdown),
                )

        self.logger.info(
            "agent=%s | pipeline finished (final_chars=%s)",
            self.agent_name,
            len(current_markdown),
        )
        return LabPostWriterResponse(reviewed_markdown=current_markdown)
