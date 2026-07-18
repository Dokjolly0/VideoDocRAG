import typer

from videodoc.cli.output import console, print_error, print_warning, render_summary_table
from videodoc.cli.progress import RichProgressReporter
from videodoc.core.errors import DatabaseError, InvalidConfigError, NoVideosFoundError, ProjectNotFoundError
from videodoc.core.services.code_service import CodeService
from videodoc.core.services.project_service import ProjectService


def code_command(
    project: str = typer.Argument(..., help="Project name or path"),
    workers: int | None = typer.Option(None, "--workers", min=1, help="Number of videos to analyze concurrently."),
) -> None:
    try:
        service = ProjectService.load(project)
        with RichProgressReporter(console) as reporter:
            result = CodeService(service.project_dir, service.config, workers_override=workers).run(progress=reporter)
    except (ProjectNotFoundError, InvalidConfigError, NoVideosFoundError, DatabaseError) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    console.print(f"Project: {service.config.project.slug}")
    render_summary_table([
        ("Processed", str(len(result.processed))),
        ("Skipped", str(len(result.skipped))),
    ])

    for error in result.errors:
        print_warning(error)
