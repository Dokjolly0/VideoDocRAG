from rich.text import Text
import typer

from videodoc.cli.output import console, print_error, print_warning, render_summary_table
from videodoc.core.errors import (
    DatabaseError,
    InspectionUnavailableError,
    InvalidConfigError,
    NoVideosFoundError,
    ProjectNotFoundError,
)
from videodoc.core.services.chat_service import parse_timecode
from videodoc.core.services.inspection_service import InspectionResult, TimestampInspectionService
from videodoc.core.services.project_service import ProjectService


def inspect_command(
    project: str = typer.Argument(..., help="Project name or path"),
    timestamp: str = typer.Option(..., "--timestamp", help="Timestamp to inspect, HH:MM:SS or MM:SS."),
    video: str | None = typer.Option(None, "--video", help="Video id, filename, or filename stem."),
) -> None:
    try:
        service = ProjectService.load(project)
        result = TimestampInspectionService(service.project_dir, service.config).inspect(
            video=video,
            timestamp_seconds=parse_timecode(timestamp) or 0.0,
        )
    except (
        ProjectNotFoundError,
        InvalidConfigError,
        NoVideosFoundError,
        InspectionUnavailableError,
        DatabaseError,
        ValueError,
    ) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    _render(result)


def _render(result: InspectionResult) -> None:
    console.print(f"Project: {result.project_slug}")
    rows = [
        ("Video", f"{result.video_name} ({result.video_id})"),
        ("Timestamp", _format_seconds(result.timestamp_seconds)),
        ("Transcript", _transcript(result)),
        ("Frame", _frame(result)),
        ("OCR", _ocr(result)),
        ("Chunk", _chunk(result)),
        ("Documentation hits", str(len(result.documentation_hits))),
    ]
    render_summary_table(rows)

    if result.code_blocks:
        console.print("Detected code:")
        for block in result.code_blocks:
            distance = "" if block.distance_seconds is None else f" distance={block.distance_seconds:.1f}s"
            header = f"- {block.block_id} {block.language or 'text'} @{_optional_seconds(block.timestamp_seconds)}{distance}"
            console.print(Text(header.rstrip()))
            console.print(Text(f"  {_excerpt(block.code)}"))

    if result.documentation_hits:
        console.print("Documentation:")
        for hit in result.documentation_hits:
            console.print(Text(
                f"- {hit.output_path} [{hit.rank}] {hit.section_title} "
                f"{_range(hit.start_seconds, hit.end_seconds)} {hit.topic or ''}".rstrip()
            ))

    for warning in result.warnings:
        print_warning(warning)


def _transcript(result: InspectionResult) -> str:
    if result.transcript is None:
        return "not found"
    segment = result.transcript
    suffix = "" if segment.distance_seconds == 0 else f" (nearest, distance {segment.distance_seconds:.1f}s)"
    confidence = "" if segment.confidence is None else f", confidence {segment.confidence:.2f}"
    return f"{_range(segment.start_seconds, segment.end_seconds)}{confidence}{suffix}: {_excerpt(segment.text)}"


def _frame(result: InspectionResult) -> str:
    if result.frame is None:
        return "not found"
    frame = result.frame
    return f"{frame.image_path} @{_format_seconds(frame.timestamp_seconds)} (distance {frame.distance_seconds:.1f}s)"


def _ocr(result: InspectionResult) -> str:
    if result.frame is None or not result.frame.ocr_text:
        return "not found"
    confidence = "" if result.frame.ocr_confidence is None else f" (confidence {result.frame.ocr_confidence:.2f})"
    return f"{_excerpt(result.frame.ocr_text)}{confidence}"


def _chunk(result: InspectionResult) -> str:
    if result.chunk is None:
        return "not found"
    chunk = result.chunk
    suffix = "" if chunk.distance_seconds == 0 else f" (nearest, distance {chunk.distance_seconds:.1f}s)"
    return f"{chunk.chunk_id} {_range(chunk.start_seconds, chunk.end_seconds)} {chunk.topic or ''}{suffix}".strip()


def _range(start_seconds: float | None, end_seconds: float | None) -> str:
    if start_seconds is None and end_seconds is None:
        return ""
    if end_seconds is None:
        return f"@{_format_seconds(start_seconds or 0.0)}"
    return f"{_format_seconds(start_seconds or 0.0)}-{_format_seconds(end_seconds)}"


def _optional_seconds(value: float | None) -> str:
    return "-" if value is None else _format_seconds(value)


def _format_seconds(value: float) -> str:
    total = max(0, int(round(value)))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _excerpt(text: str, max_chars: int = 220) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."
