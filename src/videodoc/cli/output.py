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


def render_projects_table(entries: list[ProjectEntry]) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Path", overflow="fold")
    table.add_column("Created at")
    for e in entries:
        table.add_row(e.name, str(e.path), e.created_at.isoformat(timespec="seconds"))
    console.print(table)
