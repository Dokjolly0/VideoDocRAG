from typing import Literal

import typer

from videodoc.cli.output import console, print_error, print_warning, render_summary_table
from videodoc.cli.progress import RichProgressReporter
from videodoc.core.errors import (
    DatabaseError,
    InvalidConfigError,
    NoVideosFoundError,
    ProjectNotFoundError,
    TranscriptionEngineError,
)
from videodoc.core.services.project_service import ProjectService
from videodoc.core.services.transcription_service import TranscriptionService


def transcribe_command(
    project: str = typer.Argument(..., help="Project name or path"),
    workers: int | None = typer.Option(None, "--workers", min=1, help="Number of transcriptions to run concurrently."),
    device: Literal["auto", "cpu", "cuda"] | None = typer.Option(None, "--device", help="Transcription device override."),
) -> None:
    try:
        service = ProjectService.load(project)
        with RichProgressReporter(console) as reporter:
            result = TranscriptionService(service.project_dir, service.config, workers_override=workers, device_override=device).run(progress=reporter)
    except (
        ProjectNotFoundError,
        InvalidConfigError,
        NoVideosFoundError,
        TranscriptionEngineError,
        DatabaseError,
    ) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    console.print(f"Project: {service.config.project.slug}")
    render_summary_table([
        ("Transcribed", str(len(result.transcribed))),
        ("Skipped", str(len(result.skipped))),
    ])

    for error in result.errors:
        print_warning(error)
