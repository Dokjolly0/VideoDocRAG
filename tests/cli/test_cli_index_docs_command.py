from typer.testing import CliRunner

from videodoc.cli.app import app
from videodoc.core.models.vector_index import VectorIndex

runner = CliRunner()


def _init_project(tmp_path):
    custom = tmp_path / "demo"
    result = runner.invoke(app, ["init", "demo", "--path", str(custom)])
    assert result.exit_code == 0
    return custom


def test_index_docs_writes_documentation_index(tmp_path):
    custom = _init_project(tmp_path)
    docs = custom / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "01-introduzione.md").write_text("# Introduzione\n\nContenuto PostgreSQL.\n", encoding="utf-8")

    result = runner.invoke(app, ["index-docs", "demo"])

    assert result.exit_code == 0
    assert "Records" in result.stdout
    index = VectorIndex.load(custom / "indexes" / "documentation_index.json")
    assert len(index.records) == 1
    assert index.records[0].payload["source_type"] == "generated_documentation"


def test_index_docs_without_docs_writes_empty_index(tmp_path):
    custom = _init_project(tmp_path)

    result = runner.invoke(app, ["index-docs", "demo"])

    assert result.exit_code == 0
    index = VectorIndex.load(custom / "indexes" / "documentation_index.json")
    assert index.records == []


def test_index_docs_unknown_project_fails():
    result = runner.invoke(app, ["index-docs", "missing"])

    assert result.exit_code == 1
    assert "Error:" in result.output
