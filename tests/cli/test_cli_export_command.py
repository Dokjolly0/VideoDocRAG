from typer.testing import CliRunner

from videodoc.cli.app import app

runner = CliRunner()


def _init_project(tmp_path, name="demo"):
    custom = tmp_path / name
    result = runner.invoke(app, ["init", name, "--path", str(custom)])
    assert result.exit_code == 0
    return custom


def _seed_docs(project_dir):
    docs = project_dir / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "01-introduzione.md").write_text("# Introduzione\n", encoding="utf-8")


def test_export_success_prints_summary_and_writes_mkdocs(tmp_path):
    custom = _init_project(tmp_path)
    _seed_docs(custom)

    result = runner.invoke(app, ["export", "demo", "--format", "mkdocs"])

    assert result.exit_code == 0
    assert "Format" in result.stdout
    assert "mkdocs" in result.stdout
    assert (custom / "exports" / "mkdocs" / "mkdocs.yml").is_file()


def test_export_missing_sections_fails_with_hint(tmp_path):
    _init_project(tmp_path)

    result = runner.invoke(app, ["export", "demo"])

    assert result.exit_code == 1
    assert "videodoc generate" in result.output


def test_export_unknown_format_fails(tmp_path):
    custom = _init_project(tmp_path)
    _seed_docs(custom)

    result = runner.invoke(app, ["export", "demo", "--format", "epub"])

    assert result.exit_code == 1
    assert "not supported" in result.output
