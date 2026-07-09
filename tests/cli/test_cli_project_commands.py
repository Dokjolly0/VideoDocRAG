from pathlib import Path

from typer.testing import CliRunner

from videodoc.cli.app import app

runner = CliRunner()


def test_init_creates_project_under_default_home(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEODOC_HOME", str(tmp_path / "home"))
    result = runner.invoke(app, ["init", "demo"])
    assert result.exit_code == 0
    assert "initialized" in result.stdout
    assert (tmp_path / "home" / "demo" / "config.yaml").is_file()


def test_init_with_custom_path(tmp_path):
    custom = tmp_path / "custom-project"
    result = runner.invoke(app, ["init", "demo", "--path", str(custom)])
    assert result.exit_code == 0
    assert (custom / "config.yaml").is_file()


def test_init_rerun_reports_already_initialized(tmp_path):
    custom = tmp_path / "custom-project"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])
    result = runner.invoke(app, ["init", "demo", "--path", str(custom)])
    assert result.exit_code == 0
    assert "already initialized" in result.stdout


def test_init_conflicting_path_fails(tmp_path):
    runner.invoke(app, ["init", "demo", "--path", str(tmp_path / "path-a")])
    result = runner.invoke(app, ["init", "demo", "--path", str(tmp_path / "path-b")])
    assert result.exit_code == 1


def test_list_empty_registry(tmp_path):
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No registered projects" in result.stdout


def test_list_shows_registered_projects(tmp_path):
    runner.invoke(app, ["init", "alpha", "--path", str(tmp_path / "alpha")])
    runner.invoke(app, ["init", "beta", "--path", str(tmp_path / "beta")])
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "alpha" in result.stdout
    assert "beta" in result.stdout


def test_link_registers_manually_created_project(tmp_path):
    from videodoc.core.config import ProjectConfig
    from videodoc.core.storage import filesystem

    project_dir = tmp_path / "manual-project"
    filesystem.ensure_project_structure(project_dir)
    ProjectConfig.default(name="Manual", slug="manual-project").save(project_dir / "config.yaml")

    result = runner.invoke(app, ["link", str(project_dir)])
    assert result.exit_code == 0

    list_result = runner.invoke(app, ["list"])
    assert "manual-project" in list_result.stdout


def test_link_without_config_fails(tmp_path):
    empty_dir = tmp_path / "not-a-project"
    empty_dir.mkdir()
    result = runner.invoke(app, ["link", str(empty_dir)])
    assert result.exit_code == 1


def test_unlink_does_not_delete_files(tmp_path):
    custom = tmp_path / "demo"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])

    result = runner.invoke(app, ["unlink", "demo"])
    assert result.exit_code == 0
    assert "were not deleted" in result.stdout
    assert custom.exists()

    list_result = runner.invoke(app, ["list"])
    assert "demo" not in list_result.stdout


def test_unlink_unknown_project_fails():
    result = runner.invoke(app, ["unlink", "nope"])
    assert result.exit_code == 1


def test_path_prints_absolute_path(tmp_path):
    custom = tmp_path / "demo"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])
    result = runner.invoke(app, ["path", "demo"])
    assert result.exit_code == 0
    assert str(custom.resolve()) in result.stdout


def test_path_unknown_project_fails():
    result = runner.invoke(app, ["path", "nope"])
    assert result.exit_code == 1


def test_end_to_end_flow(tmp_path):
    custom = tmp_path / "demo"

    assert runner.invoke(app, ["init", "demo", "--path", str(custom)]).exit_code == 0
    assert "demo" in runner.invoke(app, ["list"]).stdout

    path_result = runner.invoke(app, ["path", "demo"])
    assert Path(path_result.stdout.strip()) == custom.resolve()

    assert runner.invoke(app, ["unlink", "demo"]).exit_code == 0
    assert "demo" not in runner.invoke(app, ["list"]).stdout

    assert runner.invoke(app, ["link", str(custom)]).exit_code == 0
    assert "demo" in runner.invoke(app, ["list"]).stdout
