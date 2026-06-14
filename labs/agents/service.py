"""Service layer for blog post writing and revision workflows."""

from typing import Any
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException

from core.llm_config import AgentRole, LLMConfig
from labs.agents.labs_code_example.agent import LabCodeExampleAgent
from labs.agents.labs_post_metadata.agent import LabPostMetadataAgent
from labs.agents.labs_post_writer.agent import LabPostWriterAgent
from labs.agents.labs_post_translator.agent import LabPostTranslatorAgent
from labs.agents.labs_reviewer.agent import LabReviewerAgent
from labs.agents.labs_reviewer.schema import LabReviewerRequest, LabReviewerResponse
from labs.agents.contants import PUBLIC_MARKDOWN_DIR, PUBLIC_PDF_DIR
from labs.helpers.markdown_helper import MarkdownHelper
from labs.helpers.pdf_helper import PDFHelper
from labs.process_status.service import ProcessStatusService
from pathlib import Path


class LabPostService:
    """Orchestrates blog post generation/revision and file output."""

    def __init__(self) -> None:
        reviewer_llm = LLMConfig.build_chat_model_for_agent(AgentRole.REVIEWER)
        code_example_llm = LLMConfig.build_chat_model_for_agent(AgentRole.CODE_EXAMPLE)
        writer_llm = LLMConfig.build_chat_model_for_agent(AgentRole.POST_WRITER)
        metadata_llm = LLMConfig.build_chat_model_for_agent(AgentRole.METADATA)
        translator_llm = LLMConfig.build_chat_model_for_agent(AgentRole.TRANSLATOR)

        reviewer_agent = LabReviewerAgent(llm=reviewer_llm)
        code_example_agent = LabCodeExampleAgent(llm=code_example_llm)
        self.writer_agent = LabPostWriterAgent(llm=writer_llm)
        self.writer_agent.blog_reviwer = reviewer_agent
        self.writer_agent.code_example_agent = code_example_agent
        self.translator_agent = LabPostTranslatorAgent(llm=translator_llm)
        self.metadata_agent = LabPostMetadataAgent(llm=metadata_llm)
        self.reviewer_agent = reviewer_agent
        self.markdown_output_dir = PUBLIC_MARKDOWN_DIR
        self.pdf_output_dir = PUBLIC_PDF_DIR
        self.process_status_service = ProcessStatusService()

    async def enqueue_markdown_organization(
        self,
        background_tasks: BackgroundTasks,
        filename: str,
        context: str,
        user_id: UUID,
    ) -> dict[str, str]:
        """Validate file metadata and enqueue async processing for markdown generation."""
        original_name = Path(filename or "")
        safe_name = original_name.name
        if not safe_name:
            raise HTTPException(status_code=400, detail="A filename is required.")

        filename = safe_name
        if not filename.lower().endswith(".md"):
            raise HTTPException(status_code=400, detail="Only .md files are supported.")

        output_name = f"{original_name.stem}_reviewd{original_name.suffix or '.md'}"
        output_path = self.markdown_output_dir / output_name
        process_status = await self.process_status_service.create_process_for_review(
            file=filename,
            user_id=user_id,
        )
        background_tasks.add_task(
            MarkdownHelper.process_and_save_markdown_with_status,
            context,
            output_path,
            self.writer_agent,
            self.translator_agent,
            self.metadata_agent,
            process_status.id,
            self.process_status_service,
        )

        return {
            "message": "Processing started.",
            "process_id": str(process_status.id),
            "output_file": str(output_path),
        }

    def revise_blog_post(self, request: LabReviewerRequest) -> LabReviewerResponse:
        """Revise blog content through the revisor agent."""
        return self.reviewer_agent.revise(request)

    def list_markdown_outputs(self) -> dict[str, Any]:
        """List generated markdown outputs available in the public output folder."""
        items = MarkdownHelper.list_markdown_files(self.markdown_output_dir)
        return {"items": items, "count": len(items)}

    def list_pdf_outputs(self) -> dict[str, Any]:
        """List generated PDF outputs available in the public output folder."""
        items = PDFHelper.list_output_files(self.pdf_output_dir, ".pdf", "pdf")
        return {"items": items, "count": len(items)}
