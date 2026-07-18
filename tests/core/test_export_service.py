import pytest

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DocumentationExportFormatError, DocumentationExportUnavailableError
from videodoc.core.services.export_service import DocumentationExportService


def _config():
    return ProjectConfig.default(name="Demo Software", slug="demo")


def _seed_docs(project_dir):
    docs = project_dir / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "outline.md").write_text("# Documentazione Demo\n", encoding="utf-8")
    (docs / "01-introduzione.md").write_text(
        "# Introduzione\n\n## Obiettivo\n\nPresentare il progetto.\n",
        encoding="utf-8",
    )
    (docs / "02-configurazione.md").write_text(
        "# Configurazione\n\n## Obiettivo\n\nConfigurare il database.\n",
        encoding="utf-8",
    )
    (docs / "review_report.md").write_text("# Report\n", encoding="utf-8")


def test_markdown_export_copies_docs(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _seed_docs(project_dir)

    result = DocumentationExportService(project_dir, _config()).run("markdown")

    assert result.format == "markdown"
    assert (project_dir / "exports" / "markdown" / "01-introduzione.md").is_file()
    assert (project_dir / "exports" / "markdown" / "review_report.md").is_file()


def test_mkdocs_export_writes_config_and_docs(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _seed_docs(project_dir)

    result = DocumentationExportService(project_dir, _config()).run("mkdocs")

    assert result.format == "mkdocs"
    assert "site_name: Demo Software" in (project_dir / "exports" / "mkdocs" / "mkdocs.yml").read_text(encoding="utf-8")
    assert (project_dir / "exports" / "mkdocs" / "docs" / "index.md").is_file()


def test_docusaurus_export_writes_scaffold(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _seed_docs(project_dir)

    result = DocumentationExportService(project_dir, _config()).run("docusaurus")

    assert result.format == "docusaurus"
    assert (project_dir / "exports" / "docusaurus" / "sidebars.js").is_file()
    assert (project_dir / "exports" / "docusaurus" / "docs" / "intro.md").is_file()


def test_html_exports_write_index_and_pages(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _seed_docs(project_dir)

    html_result = DocumentationExportService(project_dir, _config()).run("html")
    pages_result = DocumentationExportService(project_dir, _config()).run("github-pages")

    assert html_result.format == "html"
    assert (project_dir / "exports" / "html" / "index.html").is_file()
    assert (project_dir / "exports" / "github-pages" / ".nojekyll").is_file()
    assert pages_result.format == "github-pages"


def test_pdf_export_writes_pdf_file(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _seed_docs(project_dir)

    result = DocumentationExportService(project_dir, _config()).run("pdf")

    pdf = project_dir / "exports" / "pdf" / "documentation.pdf"
    assert result.files == (pdf,)
    assert pdf.read_bytes().startswith(b"%PDF-1.4")


def test_missing_generated_sections_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()

    with pytest.raises(DocumentationExportUnavailableError, match="videodoc generate"):
        DocumentationExportService(project_dir, _config()).run("markdown")


def test_unknown_format_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _seed_docs(project_dir)

    with pytest.raises(DocumentationExportFormatError, match="not supported"):
        DocumentationExportService(project_dir, _config()).run("epub")
