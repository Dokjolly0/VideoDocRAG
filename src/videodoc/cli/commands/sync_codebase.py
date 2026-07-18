import typer

from videodoc.cli.output import console, print_error, print_warning, render_summary_table
from videodoc.core.errors import InvalidConfigError, ProjectNotFoundError
from videodoc.core.services.codebase_sync_service import CodebaseSyncService
from videodoc.core.services.project_service import ProjectService


def sync_codebase_command(project: str = typer.Argument(..., help="Project name or path")) -> None:
    try:
        service = ProjectService.load(project)
        result = CodebaseSyncService(service.project_dir, service.config).run()
    except (ProjectNotFoundError, InvalidConfigError, OSError) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    console.print(f"Project: {service.config.project.slug}")
    render_summary_table([
        ("Synced", "yes" if result.synced else "no"),
        ("Skipped", "yes" if result.skipped else "no"),
        ("Files", str(result.files)),
        ("Snippets", str(result.snippets)),
        ("Added", str(result.added)),
        ("Modified", str(result.modified)),
        ("Removed", str(result.removed)),
        ("Manifest", str(result.manifest_path)),
        ("Index", str(result.index_path)),
    ])
    for error in result.errors:
        print_warning(error)
