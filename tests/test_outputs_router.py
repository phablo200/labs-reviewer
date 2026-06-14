from pathlib import Path

from labs.helpers.markdown_helper import MarkdownHelper
from labs.helpers.pdf_helper import PDFHelper
from labs.agents.service import LabPostService


def test_list_markdown_files_returns_sorted_markdown_files(tmp_path) -> None:
    (tmp_path / "b-file.md").write_text("b", encoding="utf-8")
    (tmp_path / "a-file.md").write_text("a", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")

    items = MarkdownHelper.list_markdown_files(tmp_path)

    assert items == [
        {"filename": "a-file.md", "path": "public/markdown/a-file.md"},
        {"filename": "b-file.md", "path": "public/markdown/b-file.md"},
    ]


def test_list_markdown_files_returns_empty_for_missing_directory(tmp_path) -> None:
    items = MarkdownHelper.list_markdown_files(tmp_path / "missing")
    assert items == []


def test_list_markdown_outputs_response_shape(tmp_path) -> None:
    (tmp_path / "post.md").write_text("# Post", encoding="utf-8")
    service = LabPostService.__new__(LabPostService)
    service.markdown_output_dir = Path(tmp_path)
    service.pdf_output_dir = Path(tmp_path / "pdf")

    payload = service.list_markdown_outputs()

    assert payload == {
        "items": [{"filename": "post.md", "path": "public/markdown/post.md"}],
        "count": 1,
    }


def test_list_output_files_returns_sorted_pdf_files(tmp_path) -> None:
    (tmp_path / "b-file.pdf").write_text("b", encoding="utf-8")
    (tmp_path / "a-file.pdf").write_text("a", encoding="utf-8")
    (tmp_path / "notes.md").write_text("x", encoding="utf-8")

    items = PDFHelper.list_output_files(tmp_path, ".pdf", "pdf")

    assert items == [
        {"filename": "a-file.pdf", "path": "public/pdf/a-file.pdf"},
        {"filename": "b-file.pdf", "path": "public/pdf/b-file.pdf"},
    ]


def test_list_pdf_outputs_response_shape(tmp_path) -> None:
    (tmp_path / "post.pdf").write_text("pdf", encoding="utf-8")
    service = LabPostService.__new__(LabPostService)
    service.markdown_output_dir = Path(tmp_path / "markdown")
    service.pdf_output_dir = Path(tmp_path)

    payload = service.list_pdf_outputs()

    assert payload == {
        "items": [{"filename": "post.pdf", "path": "public/pdf/post.pdf"}],
        "count": 1,
    }
