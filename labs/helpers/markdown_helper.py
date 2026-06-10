"""Markdown-related helper methods for the lab workflow."""

from datetime import date
import logging
from pathlib import Path

from labs.agents.labs_post_metadata.schema import LabPostMetadataRequest, LabPostMetadataResponse
from labs.agents.labs_post_translator.schema import LabPostTranslatorRequest
from labs.agents.labs_post_writer.schema import LabPostWriterRequest
from labs.agents.contants import PUBLIC_PDF_DIR
from labs.helpers.pdf_helper import PDFHelper

logger = logging.getLogger(__name__)


class MarkdownHelper:
    """Coordinates markdown generation, normalization, and persistence."""

    REQUIRED_FRONTMATTER_TEMPLATE = """---
title: "{title}"
date: "{date}"
summary: "{summary}"
tags: ["Carreira", "Meta"]
published: true
---
"""

    @staticmethod
    def _extract_frontmatter(markdown: str) -> tuple[str | None, str]:
        text = markdown.lstrip()
        if not text.startswith("---\n"):
            return None, markdown

        end_marker = "\n---\n"
        end_idx = text.find(end_marker, 4)
        if end_idx == -1:
            return None, markdown

        frontmatter = text[: end_idx + len("\n---")]
        body = text[end_idx + len(end_marker) :]
        return frontmatter, body

    @staticmethod
    def ensure_required_frontmatter(markdown: str) -> str:
        """Guarantee required metadata keys are present in post frontmatter."""
        frontmatter, body = MarkdownHelper._extract_frontmatter(markdown)
        body = body.lstrip("\n") if frontmatter is not None else markdown.lstrip("\n")

        default_title = "Olá, mundo: por que comecei este blog"
        default_date = date.today().isoformat()
        default_summary = (
            "Depois de 9+ anos construindo software, decidi escrever sobre o que "
            "aprendo no caminho. Aqui está o porquê — e o que esperar."
        )

        if frontmatter is None:
            template = MarkdownHelper.REQUIRED_FRONTMATTER_TEMPLATE.format(
                title=default_title,
                date=default_date,
                summary=default_summary,
            )
            return f"{template}\n{body}".rstrip() + "\n"

        required_lines = {
            "title:": f'title: "{default_title}"',
            "date:": f'date: "{default_date}"',
            "summary:": f'summary: "{default_summary}"',
            "tags:": 'tags: ["Carreira", "Meta"]',
            "published:": "published: true",
        }

        lines = frontmatter.splitlines()
        if lines and lines[0] == "---" and lines[-1] == "---":
            inner = lines[1:-1]
        else:
            inner = lines

        for key, line in required_lines.items():
            if not any(item.strip().startswith(key) for item in inner):
                inner.append(line)

        normalized_frontmatter = "---\n" + "\n".join(inner) + "\n---\n"
        return f"{normalized_frontmatter}\n{body}".rstrip() + "\n"

    @staticmethod
    def _default_metadata() -> LabPostMetadataResponse:
        return LabPostMetadataResponse(
            title="Hello, world: why I started this blog",
            date=date.today().isoformat(),
            summary=(
                "After 9+ years building software, I decided to write about what I learn "
                "along the way. Here is why and what to expect."
            ),
            tags=["Career", "Meta"],
            published=True,
        )

    @staticmethod
    def _normalize_metadata(metadata: LabPostMetadataResponse | None) -> LabPostMetadataResponse:
        defaults = MarkdownHelper._default_metadata()
        if metadata is None:
            return defaults

        title = metadata.title.strip() or defaults.title
        metadata_date = metadata.date.strip() or defaults.date
        summary = metadata.summary.strip() or defaults.summary
        tags = [tag.strip() for tag in metadata.tags if str(tag).strip()] or defaults.tags
        published = metadata.published
        return LabPostMetadataResponse(
            title=title,
            date=metadata_date,
            summary=summary,
            tags=tags,
            published=published,
        )

    @staticmethod
    def build_frontmatter(metadata: LabPostMetadataResponse | None) -> str:
        """Build deterministic frontmatter block from normalized metadata."""
        normalized = MarkdownHelper._normalize_metadata(metadata)
        tags = ", ".join(f'"{tag}"' for tag in normalized.tags)
        published_text = "true" if normalized.published else "false"
        return (
            "---\n"
            f'title: "{normalized.title}"\n'
            f'date: "{normalized.date}"\n'
            f'summary: "{normalized.summary}"\n'
            f"tags: [{tags}]\n"
            f"published: {published_text}\n"
            "---\n"
        )

    @staticmethod
    def compose_markdown_with_metadata(
        markdown_body: str, metadata: LabPostMetadataResponse | None
    ) -> str:
        """Replace any existing frontmatter with metadata frontmatter."""
        _, body = MarkdownHelper._extract_frontmatter(markdown_body)
        clean_body = body.strip() if body else markdown_body.strip()
        frontmatter = MarkdownHelper.build_frontmatter(metadata)
        return f"{frontmatter}\n{clean_body}\n"

    @staticmethod
    def process_and_save_markdown(
        context: str,
        output_path: Path,
        writer_agent,
        translator_agent,
        metadata_agent,
    ) -> None:
        """Generate reviewed + translated markdown, then persist markdown and PDFs."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        PUBLIC_PDF_DIR.mkdir(parents=True, exist_ok=True)
        reviewed_markdown_written = False
        try:
            response = writer_agent.organize_notes(LabPostWriterRequest(context=context))
            metadata_response: LabPostMetadataResponse | None = None
            try:
                metadata_response = metadata_agent.generate(
                    LabPostMetadataRequest(content=response.reviewed_markdown)
                )
            except Exception:
                logger.exception("Metadata generation failed, using fallback metadata")

            normalized_reviewed_markdown = MarkdownHelper.compose_markdown_with_metadata(
                response.reviewed_markdown,
                metadata_response,
            )
            output_path.write_text(normalized_reviewed_markdown, encoding="utf-8")
            reviewed_markdown_written = True

            translated_response = translator_agent.translate(
                LabPostTranslatorRequest(content=normalized_reviewed_markdown)
            )
            pt_br_output_path = output_path.with_name(
                f"{output_path.stem}_pt_br{output_path.suffix}"
            )
            normalized_translated_markdown = MarkdownHelper.compose_markdown_with_metadata(
                translated_response.translated_markdown,
                metadata_response,
            )
            pt_br_output_path.write_text(
                normalized_translated_markdown,
                encoding="utf-8",
            )
            reviewed_pdf_path = PUBLIC_PDF_DIR / f"{output_path.stem}.pdf"
            pt_br_pdf_path = PUBLIC_PDF_DIR / f"{pt_br_output_path.stem}.pdf"
            try:
                PDFHelper.render_markdown_to_pdf(
                    normalized_reviewed_markdown,
                    reviewed_pdf_path,
                )
                PDFHelper.render_markdown_to_pdf(
                    normalized_translated_markdown,
                    pt_br_pdf_path,
                )
            except Exception:
                logger.exception("PDF generation failed, markdown files were kept")
        except Exception as exc:
            if not reviewed_markdown_written:
                output_path.write_text(
                    f"Failed to process markdown notes.\n\nError: {exc}",
                    encoding="utf-8",
                )
            else:
                logger.exception(
                    "Processing failed after markdown write; preserving markdown file"
                )

    @staticmethod
    def list_markdown_files(base_dir: Path) -> list[dict[str, str]]:
        """List markdown files in the output directory in deterministic order."""
        return PDFHelper.list_output_files(base_dir, ".md", "markdown")
