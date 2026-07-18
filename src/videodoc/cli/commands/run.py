import typer
from rich.table import Table
from rich.text import Text

from videodoc.cli.output import console, print_error, print_warning, render_summary_table
from videodoc.cli.progress import RichProgressReporter
from videodoc.core.errors import VideoDocError
from videodoc.core.services.export_service import SUPPORTED_EXPORT_FORMATS
from videodoc.core.services.pipeline_service import PipelineService, PipelineStepResult
from videodoc.core.services.project_service import ProjectService


def run_command(
    project: str = typer.Argument(..., help="Project name or path"),
    export_format: str = typer.Option(
        "mkdocs",
        "--format",
        help=f"Export format for the final export step: {', '.join(SUPPORTED_EXPORT_FORMATS)}.",
    ),
    top_k: int | None = typer.Option(None, "--top-k", min=1, help="Maximum number of source chunks per generated section."),
) -> None:
    try:
        service = ProjectService.load(project)
        with RichProgressReporter(console) as reporter:
            result = PipelineService(
                service.project_dir,
                service.config,
                export_format=export_format,
                top_k=top_k,
            ).run(progress=reporter)
    except (VideoDocError, ValueError, OSError) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    console.print(f"Project: {service.config.project.slug}")
    render_summary_table([
        ("Steps", str(len(result.steps))),
        ("Export format", result.export_format),
    ])
    _render_steps(result.steps)
    for step in result.steps:
        for warning in step.warnings:
            print_warning(f"{step.name}: {warning}")


def _render_steps(steps: tuple[PipelineStepResult, ...]) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Step")
    table.add_column("Status")
    table.add_column("Detail", overflow="fold")
    for step in steps:
        table.add_row(Text(step.name), Text(step.status), Text(step.detail))
    console.print(table)
