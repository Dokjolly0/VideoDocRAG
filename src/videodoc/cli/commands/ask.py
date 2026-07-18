from rich.text import Text
import typer

from videodoc.cli.output import console, print_error
from videodoc.core.errors import (
    InvalidConfigError,
    InvalidVectorIndexError,
    ProjectNotFoundError,
    VectorIndexUnavailableError,
)
from videodoc.core.services.project_service import ProjectService
from videodoc.core.services.retrieval_service import AskResult, RetrievalService, RetrievedSource


def ask_command(
    project: str = typer.Argument(..., help="Project name or path"),
    question: str = typer.Argument(..., help="Question to answer from indexed project sources"),
    top_k: int | None = typer.Option(None, "--top-k", min=1, help="Maximum number of source chunks to retrieve."),
) -> None:
    try:
        service = ProjectService.load(project)
        result = RetrievalService(service.project_dir, service.config).ask(question, top_k=top_k)
    except (
        ProjectNotFoundError,
        InvalidConfigError,
        VectorIndexUnavailableError,
        InvalidVectorIndexError,
        ValueError,
    ) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    _render_answer(service.config.project.slug, result)


def _render_answer(project_slug: str, result: AskResult) -> None:
    console.print(f"Project: {project_slug}")
    console.print("Answer:")
    console.print(Text(result.answer))
    if not result.sources:
        return

    console.print("Sources:")
    for source in result.sources:
        console.print(Text(_source_header(source)))
        console.print(Text(f"    {_source_excerpt(source.text)}"))


def _source_header(source: RetrievedSource) -> str:
    time_range = _time_range(source.start_seconds, source.end_seconds)
    bits = [
        f"[{source.rank}]",
        source.video_name or source.video_id,
        time_range,
        f"score={source.score:.3f}",
        f"chunk={source.chunk_id}",
    ]
    if source.embedding_type:
        bits.append(f"type={source.embedding_type}")
    if source.source_type:
        bits.append(f"source={source.source_type}")
    if source.topic:
        bits.append(f"topic={source.topic}")
    return " ".join(bit for bit in bits if bit)


def _time_range(start_seconds: float | None, end_seconds: float | None) -> str:
    if start_seconds is None and end_seconds is None:
        return ""
    if end_seconds is None:
        return f"@{_format_seconds(start_seconds or 0.0)}"
    return f"{_format_seconds(start_seconds or 0.0)}-{_format_seconds(end_seconds)}"


def _format_seconds(value: float) -> str:
    total = max(0, int(round(value)))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _source_excerpt(text: str, max_chars: int = 220) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."
