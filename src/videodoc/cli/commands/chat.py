from rich.text import Text
import typer

from videodoc.cli.commands.ask import _chat_mode, _source_excerpt, _source_header
from videodoc.cli.output import console, print_error
from videodoc.core.errors import DatabaseError, InvalidConfigError, InvalidVectorIndexError, ProjectNotFoundError, VectorIndexUnavailableError
from videodoc.core.services.chat_service import ChatAnswerService, ChatFilters, parse_timecode
from videodoc.core.services.project_service import ProjectService


def chat_command(
    project: str = typer.Argument(..., help="Project name or path"),
    message: str | None = typer.Option(None, "--message", help="Send one message and exit."),
    session: str | None = typer.Option(None, "--session", help="Continue an existing chat session id."),
    source: str | None = typer.Option(None, "--source", help="Retrieval source: docs, raw, or hybrid."),
    videos: list[str] | None = typer.Option(None, "--video", help="Limit retrieval to a video id or filename."),
    from_time: str | None = typer.Option(None, "--from", help="Start time filter, HH:MM:SS or MM:SS."),
    to_time: str | None = typer.Option(None, "--to", help="End time filter, HH:MM:SS or MM:SS."),
    top_k: int | None = typer.Option(None, "--top-k", min=1, help="Maximum number of sources per turn."),
) -> None:
    try:
        project_service = ProjectService.load(project)
        chat = ChatAnswerService(project_service.project_dir, project_service.config)
        filters = ChatFilters(
            videos=tuple(videos or ()),
            start_seconds=parse_timecode(from_time),
            end_seconds=parse_timecode(to_time),
        )
        mode = _chat_mode(source, project_service.config.chat.default_source)
        if message is not None:
            result = chat.answer(message, mode=mode, filters=filters, top_k=top_k, session_id=session, save_session=True)
            _render_turn(project_service.config.project.slug, result)
            return

        current_session = session
        console.print(f"Project: {project_service.config.project.slug}")
        console.print("Type 'exit' or an empty line to stop.")
        while True:
            user_message = typer.prompt("You", default="", show_default=False)
            if not user_message.strip() or user_message.strip().lower() in {"exit", "quit"}:
                break
            result = chat.answer(user_message, mode=mode, filters=filters, top_k=top_k, session_id=current_session, save_session=True)
            current_session = result.session_id
            console.print(Text(result.answer))
    except (
        ProjectNotFoundError,
        InvalidConfigError,
        VectorIndexUnavailableError,
        InvalidVectorIndexError,
        DatabaseError,
        ValueError,
    ) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)


def _render_turn(project_slug: str, result) -> None:
    console.print(f"Project: {project_slug}")
    if result.session_id:
        console.print(f"Session: {result.session_id}")
    console.print("Answer:")
    console.print(Text(result.answer))
    if result.sources:
        console.print("Sources:")
        for source in result.sources:
            console.print(Text(_source_header(source)))
            console.print(Text(f"    {_source_excerpt(source.text)}"))
