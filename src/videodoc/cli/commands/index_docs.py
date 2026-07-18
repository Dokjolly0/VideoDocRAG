import typer

from videodoc.cli.output import console, print_error, render_summary_table
from videodoc.core.errors import InvalidConfigError, InvalidVectorIndexError, ProjectNotFoundError
from videodoc.core.services.chat_service import DocumentationIndexService
from videodoc.core.services.project_service import ProjectService


def index_docs_command(project: str = typer.Argument(..., help="Project name or path")) -> None:
    try:
        service = ProjectService.load(project)
        index = DocumentationIndexService(service.project_dir, service.config).build()
    except (ProjectNotFoundError, InvalidConfigError, InvalidVectorIndexError, OSError) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    console.print(f"Project: {service.config.project.slug}")
    render_summary_table([
        ("Records", str(len(index.records))),
        ("Inputs", str(len(index.inputs))),
        ("Index", str(service.project_dir / service.config.paths.indexes / "documentation_index.json")),
    ])
