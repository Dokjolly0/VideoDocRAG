import typer

from videodoc.cli.output import console, print_error, print_warning, render_summary_table
from videodoc.core.errors import DatabaseError, InvalidConfigError, ProjectNotFoundError
from videodoc.core.services.project_service import ProjectService
from videodoc.core.services.status_service import PipelineStatusResult, PipelineStatusService


def status_command(project: str = typer.Argument(..., help="Project name or path")) -> None:
    try:
        service = ProjectService.load(project)
        result = PipelineStatusService(service.project_dir, service.config).run()
    except (ProjectNotFoundError, InvalidConfigError, DatabaseError) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    console.print(f"Project: {result.project_slug}")
    render_summary_table(_rows(result))
    for warning in result.warnings:
        print_warning(warning)


def _rows(result: PipelineStatusResult) -> list[tuple[str, str]]:
    total = len(result.videos)
    docs = result.documentation
    return [
        ("Path", str(result.project_dir)),
        ("Sources scan", _sources(result)),
        ("Videos", str(total)),
        ("Audio extracted", _count(result.videos, "audio")),
        ("Transcribed", _count(result.videos, "transcript")),
        ("Frames extracted", _count(result.videos, "frames")),
        ("OCR completed", _count(result.videos, "ocr")),
        ("Code extracted", _count(result.videos, "code")),
        ("Chunks generated", _count(result.videos, "chunks")),
        ("Embeddings generated", _count(result.videos, "embeddings")),
        ("Raw index", _index(result.raw_index)),
        ("Codebase index", _index(result.codebase_index)),
        ("Documentation index", _index(result.documentation_index)),
        ("Documentation", _documentation(docs)),
        ("Chat sessions", str(result.chat_sessions)),
    ]


def _sources(result: PipelineStatusResult) -> str:
    if not result.sources.scanned:
        return "no"
    return (
        f"yes (videos={result.sources.videos}, attachments={result.sources.attachments}, "
        f"codebase_files={result.sources.codebase_files})"
    )


def _count(videos, attribute: str) -> str:
    total = len(videos)
    complete = sum(1 for video in videos if getattr(video, attribute))
    return f"{complete}/{total}"


def _index(index) -> str:
    if not index.present:
        return "no"
    if not index.valid:
        return "present but invalid"
    return f"yes ({index.records} records, {index.inputs} inputs)"


def _documentation(docs) -> str:
    parts = [
        f"outline={'yes' if docs.outline else 'no'}",
        f"sections={docs.sections}",
        f"sources={docs.source_manifests}",
        f"review={'yes' if docs.review_report and docs.review_json else 'no'}",
    ]
    if docs.export_formats:
        parts.append(f"exports={', '.join(docs.export_formats)}")
    else:
        parts.append("exports=none")
    return ", ".join(parts)
