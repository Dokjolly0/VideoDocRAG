from typer.testing import CliRunner

import videodoc.cli.commands.run as run_command_module
from videodoc.cli.app import app
from videodoc.core.services.pipeline_service import PipelineRunResult, PipelineStepResult

runner = CliRunner()


def _init_project(tmp_path):
    custom = tmp_path / "demo"
    result = runner.invoke(app, ["init", "demo", "--path", str(custom)])
    assert result.exit_code == 0
    return custom


def test_run_command_prints_pipeline_summary(monkeypatch, tmp_path):
    _init_project(tmp_path)

    class DummyPipelineService:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, **kwargs):
            return PipelineRunResult(
                steps=(
                    PipelineStepResult("scan", "completed", "videos=1, attachments=0, codebase_files=0"),
                    PipelineStepResult("export", "completed", "format=mkdocs, files=1, output=exports/mkdocs"),
                ),
                export_format="mkdocs",
            )

    monkeypatch.setattr(run_command_module, "PipelineService", DummyPipelineService)

    result = runner.invoke(app, ["run", "demo"])

    assert result.exit_code == 0
    assert "Project: demo" in result.stdout
    assert "Steps" in result.stdout
    assert "scan" in result.stdout
    assert "export" in result.stdout


def test_run_command_passes_options_to_pipeline(monkeypatch, tmp_path):
    _init_project(tmp_path)
    seen = {}

    class DummyPipelineService:
        def __init__(self, project_dir, config, **kwargs):
            seen["project_dir"] = project_dir
            seen["slug"] = config.project.slug
            seen.update(kwargs)

        def run(self, **kwargs):
            return PipelineRunResult(steps=(), export_format=seen["export_format"])

    monkeypatch.setattr(run_command_module, "PipelineService", DummyPipelineService)

    result = runner.invoke(app, ["run", "demo", "--format", "html", "--top-k", "3"])

    assert result.exit_code == 0
    assert seen["slug"] == "demo"
    assert seen["export_format"] == "html"
    assert seen["top_k"] == 3


def test_run_command_unknown_project_fails():
    result = runner.invoke(app, ["run", "missing"])

    assert result.exit_code == 1
    assert "Error:" in result.output


def test_run_command_rejects_unknown_export_format(tmp_path):
    _init_project(tmp_path)

    result = runner.invoke(app, ["run", "demo", "--format", "unknown"])

    assert result.exit_code == 1
    assert "Export format 'unknown' is not supported" in result.output
