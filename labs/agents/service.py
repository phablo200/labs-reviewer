"""Service layer for blog post writing and revision workflows."""

from pathlib import Path
import re
from typing import Any
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException

from core.tasks.exceptions import TaskDispatchEnqueueError
from labs.agents.labs_reviewer.schema import LabReviewerRequest, LabReviewerResponse
from labs.agents.contants import PUBLIC_MARKDOWN_DIR, PUBLIC_PDF_DIR
from labs.helpers.markdown_helper import MarkdownHelper
from labs.helpers.pdf_helper import PDFHelper
from labs.tasks.dependencies import build_markdown_processing_dependencies
from labs.tasks.factory import build_markdown_dispatcher
from labs.tasks.markdown_jobs import MarkdownOrganizationJob


class LabPostService:
    """Orchestrates blog post generation/revision and file output."""

    def __init__(self) -> None:
        dependencies = build_markdown_processing_dependencies()
        self.writer_agent = dependencies.writer_agent
        self.translator_agent = dependencies.translator_agent
        self.metadata_agent = dependencies.metadata_agent
        self.reviewer_agent = dependencies.reviewer_agent
        self.markdown_output_dir = PUBLIC_MARKDOWN_DIR
        self.pdf_output_dir = PUBLIC_PDF_DIR
        self.process_status_service = dependencies.process_status_service
        self.markdown_dispatcher = build_markdown_dispatcher(
            writer_agent=self.writer_agent,
            translator_agent=self.translator_agent,
            metadata_agent=self.metadata_agent,
            process_status_service=self.process_status_service,
        )

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
        job = MarkdownOrganizationJob(
            context=context,
            output_path=output_path,
            process_status_id=process_status.id,
        )
        try:
            await self.markdown_dispatcher.enqueue(
                job=job,
                background_tasks=background_tasks,
            )
        except TaskDispatchEnqueueError as exc:
            raise HTTPException(
                status_code=503,
                detail="Failed to enqueue markdown processing job.",
            ) from exc

        return {
            "message": "Processing started.",
            "process_id": str(process_status.id),
            "output_file": str(output_path),
        }

    async def enqueue_markdown_organization_for_process(
        self,
        *,
        background_tasks: BackgroundTasks,
        process_status_id: UUID,
        user_id: UUID,
    ) -> dict[str, str]:
        """Enqueue markdown generation for notes attached to an existing process."""
        process_notes = await self.process_status_service.get_process_notes(
            process_status_id=process_status_id,
            user_id=user_id,
        )
        if process_notes is None:
            raise HTTPException(status_code=404, detail="Process status not found.")

        if not process_notes.notes:
            raise HTTPException(
                status_code=400,
                detail="Process status has no notes to review.",
            )

        context = "\n\n".join(note.description for note in process_notes.notes)
        output_path = self._build_process_output_path(
            process_status_id=process_notes.process_status.id,
            filename=process_notes.process_status.file,
        )
        job = MarkdownOrganizationJob(
            context=context,
            output_path=output_path,
            process_status_id=process_notes.process_status.id,
        )
        try:
            await self.markdown_dispatcher.enqueue(
                job=job,
                background_tasks=background_tasks,
            )
        except TaskDispatchEnqueueError as exc:
            raise HTTPException(
                status_code=503,
                detail="Failed to enqueue markdown processing job.",
            ) from exc

        return {
            "message": "Processing started.",
            "process_id": str(process_notes.process_status.id),
            "output_file": str(output_path),
        }

    def _build_process_output_path(
        self,
        *,
        process_status_id: UUID,
        filename: str | None,
    ) -> Path:
        safe_name = Path(filename or "").name
        if not safe_name:
            return self.markdown_output_dir / f"process_{process_status_id}.md"

        stem = Path(safe_name).stem or safe_name
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
        if not safe_stem:
            return self.markdown_output_dir / f"process_{process_status_id}.md"

        return self.markdown_output_dir / f"{safe_stem}_reviewd.md"

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
