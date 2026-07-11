from typing import Literal

from rich.console import Console
from rich.table import Table
from rich.text import Text

from videodoc.core.services.registry_service import ProjectEntry

# soft_wrap=True: status/error lines are log-like, one message per line, and
# must never be hard-wrapped mid-sentence by rich just because a project path
# happens to be long (rich defaults to an 80-column wrap when stdout isn't a
# real terminal, e.g. when captured by tests or piped).
console = Console(soft_wrap=True)
error_console = Console(stderr=True, style="bold red", soft_wrap=True)


def print_error(message: str) -> None:
    # markup=False: `message` is dynamic (exception text, file paths --
    # e.g. a real "codebase: [Errno 13] Permission denied: '...'" or a
    # Windows path containing '[', ']') and must never be parsed as Rich
    # markup -- an unmatched closing tag like "[/red]" inside it would
    # raise rich.errors.MarkupError, and any bracketed substring that
    # happens to look like a tag would be silently swallowed.
    error_console.print(f"Error: {message}", markup=False)


def print_warning(message: str) -> None:
    # stdout, not error_console: a warning never changes the exit code.
    # markup=False: see print_error -- `message` is dynamic, never parsed.
    console.print(f"Warning: {message}", style="yellow", markup=False)


def print_check_result(status: Literal["ok", "warning", "error"], message: str) -> None:
    # doctor/setup print multiple per-check lines that must stay interleaved
    # together in one readable report, unlike every other command's single
    # fatal "Error: ..." line printed right before typer.Exit(1) -- the exit
    # code here is computed separately from DoctorResult.has_errors, not
    # from this print call itself.
    #
    # ASCII status words only, never Unicode glyphs (checkmarks/warning
    # triangles): verified directly that they crash with UnicodeEncodeError
    # on a real Windows console in this project's target environment, via
    # both a bare print() and Rich's own Console.print() (Rich's legacy-
    # Windows box-drawing substitution table does not cover arbitrary
    # Unicode symbols, only its own box characters).
    #
    # Padding is applied to the raw word BEFORE it is wrapped in Rich markup
    # tags -- padding an already-tagged string would count the tags' own
    # bracket characters, and "[green]"/"[yellow]"/"[bold red]" have
    # different lengths, which would silently misalign the three status
    # words relative to each other.
    #
    # Only the fixed "[style]WORD[/style]" fragment (built entirely from our
    # own literals, never from `message`) goes through Text.from_markup().
    # `message` is dynamic (e.g. a real ffprobe/ffmpeg error string, or a
    # path) and is appended as plain text afterwards -- Text.append() never
    # parses markup, so a stray '[' / ']' in it can neither crash nor be
    # silently swallowed the way it would if concatenated into the markup
    # string directly.
    word, style = {"ok": ("OK", "green"), "warning": ("WARN", "yellow"), "error": ("ERROR", "bold red")}[status]
    text = Text.from_markup(f"[{style}]{word:<5}[/{style}]")
    text.append(f" {message}")
    console.print(text)


def render_summary_table(rows: list[tuple[str, str]]) -> None:
    # No header: a 2-4 row field/value summary (e.g. scan's Videos/
    # Attachments/Codebase counts) reads better as plain label: value pairs
    # than with a redundant "Field | Value" header row. overflow="fold" on
    # Value, not the default "ellipsis": a value can carry a long
    # "(external: <full path>)" suffix that must never be silently
    # truncated -- worse than the plain-text line this replaces, which
    # never truncated either.
    # Rows are passed as Text, not str: Table.add_row() parses a bare str
    # cell as Rich markup at render time, and `value` is dynamic (e.g. a
    # scan summary's "(external: <full path>)" suffix) -- a path containing
    # '[' / ']' would otherwise be silently corrupted (verified: a literal
    # '[' is dropped from the rendered cell) instead of merely mis-styled.
    table = Table(show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value", overflow="fold")
    for label, value in rows:
        table.add_row(Text(label), Text(value))
    console.print(table)


def render_projects_table(entries: list[ProjectEntry]) -> None:
    # Text(...), not str: see render_summary_table -- e.path is a real
    # filesystem path that can legally contain '[' / ']' on Windows/Linux.
    table = Table(show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Path", overflow="fold")
    table.add_column("Created at")
    for e in entries:
        table.add_row(Text(e.name), Text(str(e.path)), Text(e.created_at.isoformat(timespec="seconds")))
    console.print(table)
