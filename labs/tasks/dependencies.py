"""Dependency builders shared by API and background workers."""

from dataclasses import dataclass

from core.llm_config import AgentRole, LLMConfig
from labs.agents.labs_code_example.agent import LabCodeExampleAgent
from labs.agents.labs_post_metadata.agent import LabPostMetadataAgent
from labs.agents.labs_post_translator.agent import LabPostTranslatorAgent
from labs.agents.labs_post_writer.agent import LabPostWriterAgent
from labs.agents.labs_reviewer.agent import LabReviewerAgent
from labs.process_status.service import ProcessStatusService


@dataclass(frozen=True)
class MarkdownProcessingDependencies:
    """Runtime dependencies for markdown processing jobs."""

    writer_agent: LabPostWriterAgent
    translator_agent: LabPostTranslatorAgent
    metadata_agent: LabPostMetadataAgent
    reviewer_agent: LabReviewerAgent
    process_status_service: ProcessStatusService


def build_markdown_processing_dependencies() -> MarkdownProcessingDependencies:
    """Build agents and services required by markdown processing."""
    reviewer_llm = LLMConfig.build_chat_model_for_agent(AgentRole.REVIEWER)
    code_example_llm = LLMConfig.build_chat_model_for_agent(AgentRole.CODE_EXAMPLE)
    writer_llm = LLMConfig.build_chat_model_for_agent(AgentRole.POST_WRITER)
    metadata_llm = LLMConfig.build_chat_model_for_agent(AgentRole.METADATA)
    translator_llm = LLMConfig.build_chat_model_for_agent(AgentRole.TRANSLATOR)

    reviewer_agent = LabReviewerAgent(llm=reviewer_llm)
    code_example_agent = LabCodeExampleAgent(llm=code_example_llm)
    writer_agent = LabPostWriterAgent(llm=writer_llm)
    writer_agent.blog_reviwer = reviewer_agent
    writer_agent.code_example_agent = code_example_agent

    return MarkdownProcessingDependencies(
        writer_agent=writer_agent,
        translator_agent=LabPostTranslatorAgent(llm=translator_llm),
        metadata_agent=LabPostMetadataAgent(llm=metadata_llm),
        reviewer_agent=reviewer_agent,
        process_status_service=ProcessStatusService(),
    )

