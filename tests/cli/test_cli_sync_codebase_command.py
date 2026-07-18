from typer.testing import CliRunner

from videodoc.cli.app import app

runner = CliRunner()


def _init_project(tmp_path):
    custom = tmp_path / "demo"
    result = runner.invoke(app, ["init", "demo", "--path", str(custom)])
    assert result.exit_code == 0
    return custom


def test_sync_codebase_command_writes_index(tmp_path):
    custom = _init_project(tmp_path)
    path = custom / "codebase" / "src" / "app.py"
    path.parent.mkdir(parents=True)
    path.write_text("def create_app():\n    return 'ok'\n", encoding="utf-8")

    result = runner.invoke(app, ["sync-codebase", "demo"])

    assert result.exit_code == 0
    assert "Files" in result.stdout
    assert "Snippets" in result.stdout
    assert (custom / "indexes" / "codebase_manifest.json").is_file()
    assert (custom / "indexes" / "codebase_index.json").is_file()


def test_sync_codebase_command_missing_codebase_is_noop(tmp_path):
    _init_project(tmp_path)

    result = runner.invoke(app, ["sync-codebase", "demo"])

    assert result.exit_code == 0
    assert "Skipped" in result.stdout


def test_sync_codebase_unknown_project_fails():
    result = runner.invoke(app, ["sync-codebase", "missing"])

    assert result.exit_code == 1
    assert "Error:" in result.output
