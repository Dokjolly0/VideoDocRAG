from typing import Literal

import typer

from videodoc.cli.output import console, print_error, print_warning, render_summary_table
from videodoc.cli.progress import RichProgressReporter
from videodoc.core.errors import (
    DatabaseError,
    ExternalToolNotFoundError,
    InvalidConfigError,
    NoVideosFoundError,
    ProjectNotFoundError,
)
from videodoc.core.services.frame_extraction_service import FrameExtractionService
from videodoc.core.services.project_service import ProjectService


def frames_command(
    project: str = typer.Argument(..., help="Project name or path"),
    workers: int | None = typer.Option(None, "--workers", min=1, help="Number of videos to extract frames from concurrently."),
    interval_seconds: int | None = typer.Option(None, "--interval-seconds", min=1, help="Fixed-interval frame extraction spacing override."),
    scene_detection: bool | None = typer.Option(None, "--scene-detection/--no-scene-detection", help="Enable or disable scene-change frame boosting."),
    keyword_boost: bool | None = typer.Option(None, "--keyword-boost/--no-keyword-boost", help="Enable or disable transcript-keyword frame boosting."),
    scene_threshold: float | None = typer.Option(None, "--scene-threshold", min=0.000001, max=0.999999, help="FFmpeg scene-score threshold override (0 < value < 1)."),
    hwaccel: Literal["auto", "cuda", "none"] | None = typer.Option(None, "--hwaccel", help="FFmpeg decode acceleration override."),
) -> None:
    try:
        service = ProjectService.load(project)
        with RichProgressReporter(console) as reporter:
            result = FrameExtractionService(
                service.project_dir,
                service.config,
                workers_override=workers,
                interval_seconds_override=interval_seconds,
                scene_detection_override=scene_detection,
                keyword_boost_override=keyword_boost,
                scene_threshold_override=scene_threshold,
                hwaccel_override=hwaccel,
            ).run(progress=reporter)
    except (
        ProjectNotFoundError,
        InvalidConfigError,
        NoVideosFoundError,
        ExternalToolNotFoundError,
        DatabaseError,
    ) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    console.print(f"Project: {service.config.project.slug}")
    render_summary_table([
        ("Extracted", str(len(result.extracted))),
        ("Skipped", str(len(result.skipped))),
    ])

    for error in result.errors:
        print_warning(error)