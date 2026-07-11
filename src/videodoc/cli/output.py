from typing import Literal

from rich.console import Console
from rich.table import Table

from videodoc.core.services.registry_service import ProjectEntry

# soft_wrap=True: status/error lines are log-like, one message per line, and
# must never be hard-wrapped mid-sentence by rich just because a project path
# happens to be long (rich defaults to an 80-column wrap when stdout isn't a
# real terminal, e.g. when captured by tests or piped).
console = Console(soft_wrap=True)
error_console = Console(stderr=True, style="bold red", soft_wrap=True)


def print_error(message: str) -> None:
    error_console.print(f"Error: {message}")


def print_warning(message: str) -> None:
    # stdout, not error_console: a warning never changes the exit code.
    console.print(f"Warning: {message}", style="yellow")


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
    word, style = {"ok": ("OK", "green"), "warning": ("WARN", "yellow"), "error": ("ERROR", "bold red")}[status]
    console.print(f"[{style}]{word:<5}[/{style}] {message}")


def render_summary_table(rows: list[tuple[str, str]]) -> None:
    # No header: a 2-4 row field/value summary (e.g. scan's Videos/
    # Attachments/Codebase counts) reads better as plain label: value pairs
    # than with a redundant "Field | Value" header row. overflow="fold" on
    # Value, not the default "ellipsis": a value can carry a long
    # "(external: <full path>)" suffix that must never be silently
    # truncated -- worse than the plain-text line this replaces, which
    # never truncated either.
    table = Table(show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value", overflow="fold")
    for label, value in rows:
        table.add_row(label, value)
    console.print(table)


def render_projects_table(entries: list[ProjectEntry]) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Path", overflow="fold")
    table.add_column("Created at")
    for e in entries:
        table.add_row(e.name, str(e.path), e.created_at.isoformat(timespec="seconds"))
    console.print(table)
