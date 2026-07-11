import typer

from videodoc.cli.output import console, print_error, print_warning, render_summary_table
from videodoc.cli.progress import RichProgressReporter
from videodoc.core.errors import (
    DatabaseError,
    InvalidConfigError,
    NoVideosFoundError,
    OCREngineNotSupportedError,
    OCREngineUnavailableError,
    ProjectNotFoundError,
)
from videodoc.core.services.ocr_service import OCRService
from videodoc.core.services.project_service import ProjectService


def ocr_command(
    project: str = typer.Argument(..., help="Project name or path"),
    workers: int | None = typer.Option(None, "--workers", min=1, help="Number of videos to run OCR on concurrently."),
    language: list[str] | None = typer.Option(None, "--language", help="OCR language override (repeatable), e.g. --language it --language en."),
    min_confidence: float | None = typer.Option(None, "--min-confidence", min=0.0, max=1.0, help="Confidence threshold below which OCR text is discarded (kept in the manifest as an empty string, confidence still recorded)."),
) -> None:
    try:
        service = ProjectService.load(project)
        with RichProgressReporter(console) as reporter:
            result = OCRService(
                service.project_dir,
                service.config,
                workers_override=workers,
                languages_override=language,
                min_confidence_override=min_confidence,
            ).run(progress=reporter)
    except (
        ProjectNotFoundError,
        InvalidConfigError,
        NoVideosFoundError,
        OCREngineNotSupportedError,
        OCREngineUnavailableError,
        DatabaseError,
    ) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    console.print(f"Project: {service.config.project.slug}")
    render_summary_table([
        ("Processed", str(len(result.processed))),
        ("Skipped", str(len(result.skipped))),
    ])

    for error in result.errors:
        print_warning(error)
