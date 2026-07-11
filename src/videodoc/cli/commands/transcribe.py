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
    workers: int | None = typer.Option(None, "--workers", min=1, help="Number of videos to transcribe concurrently."),
    device: Literal["auto", "cpu", "cuda"] | None = typer.Option(None, "--device", help="Transcription device override."),
    compute_type: str | None = typer.Option(None, "--compute-type", help="CTranslate2 compute type override, e.g. int8_float16 or float16."),
    mode: Literal["auto", "standard", "batched"] | None = typer.Option(None, "--mode", help="Transcription mode override."),
    batch_size: int | None = typer.Option(None, "--batch-size", min=1, help="GPU batch size for batched transcription."),
    beam_size: int | None = typer.Option(None, "--beam-size", min=1, help="Beam size for decoding; 1 is fastest."),
    word_timestamps: bool | None = typer.Option(None, "--word-timestamps/--no-word-timestamps", help="Enable or disable word-level timestamps."),
) -> None:
    try:
        service = ProjectService.load(project)
        with RichProgressReporter(console) as reporter:
            result = TranscriptionService(
                service.project_dir,
                service.config,
                workers_override=workers,
                device_override=device,
                compute_type_override=compute_type,
                mode_override=mode,
                batch_size_override=batch_size,
                beam_size_override=beam_size,
                word_timestamps_override=word_timestamps,
            ).run(progress=reporter)
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
