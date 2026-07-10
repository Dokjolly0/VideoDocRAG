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


def test_init_with_videos_option_end_to_end(tmp_path):
    custom = tmp_path / "demo"
    external = tmp_path / "external-videos"
    result = runner.invoke(app, ["init", "demo", "--path", str(custom), "--videos", str(external)])
    assert result.exit_code == 0
    assert str(external) in (custom / "config.yaml").read_text(encoding="utf-8")


def test_init_invalid_videos_option_fails_cleanly(tmp_path):
    # "../outside" is invalid on every supported OS (unlike a Windows-only
    # ambiguous form like "C:foo", which POSIX accepts as a harmless
    # relative filename -- see core/utils/paths.py).
    custom = tmp_path / "demo"
    result = runner.invoke(app, ["init", "demo", "--path", str(custom), "--videos", "../outside"])
    assert result.exit_code == 1
    # No unhandled exception (a raw pydantic.ValidationError would show up here
    # as a genuine crash, not a clean SystemExit(1) from typer.Exit).
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "Traceback" not in result.output
    assert "Error:" in result.output
    assert "paths.videos" in result.output


def test_init_rerun_with_videos_option_prints_warning(tmp_path):
    custom = tmp_path / "demo"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])
    result = runner.invoke(app, ["init", "demo", "--path", str(custom), "--videos", str(tmp_path / "external")])
    assert result.exit_code == 0
    assert "ignored" in result.stdout


def test_init_registers_by_slug_not_raw_display_name(tmp_path):
    custom = tmp_path / "corso"
    result = runner.invoke(app, ["init", "Corso Software X", "--path", str(custom)])
    assert result.exit_code == 0
    assert "corso-software-x" in result.stdout

    list_result = runner.invoke(app, ["list"])
    assert "corso-software-x" in list_result.stdout

    path_result = runner.invoke(app, ["path", "corso-software-x"])
    assert path_result.exit_code == 0


def test_init_on_path_with_different_existing_project_fails(tmp_path):
    shared = tmp_path / "shared"
    runner.invoke(app, ["init", "Original Project", "--path", str(shared)])

    result = runner.invoke(app, ["init", "Different Project", "--path", str(shared)])
    assert result.exit_code == 1


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


def test_link_with_explicit_alias_is_flagged_in_output(tmp_path):
    custom = tmp_path / "corso"
    runner.invoke(app, ["init", "Corso Software X", "--path", str(custom)])

    result = runner.invoke(app, ["link", str(custom), "--name", "Alias Locale!!"])
    assert result.exit_code == 0
    assert "alias" in result.stdout.lower()
    assert "alias-locale" in result.stdout
    assert "corso-software-x" in result.stdout

    list_result = runner.invoke(app, ["list"])
    assert "alias-locale" in list_result.stdout


def test_link_with_invalid_alias_fails(tmp_path):
    custom = tmp_path / "demo"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])

    result = runner.invoke(app, ["link", str(custom), "--name", "!!!"])
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
