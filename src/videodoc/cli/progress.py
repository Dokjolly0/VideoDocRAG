from __future__ import annotations

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn

from videodoc.core.utils.progress import ProgressReporter


class RichProgressReporter(ProgressReporter):
    """Context manager: an 'Overall' bar (video X/N) plus a bar for the
    current file's own fraction, rendered on the same shared console as the
    rest of the CLI's Rich output. transient=True erases both bars on exit
    so the final summary table (printed right after) is all that's left
    behind -- consistent with the log-like, no-permanent-noise style the
    rest of cli/output.py already follows."""

    def __init__(self, console: Console) -> None:
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        )
        self._started = False
        self._overall_task: int | None = None
        self._item_task: int | None = None

    def __enter__(self) -> "RichProgressReporter":
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._started:
            self._progress.stop()

    def start_item(self, item_id: str, index: int, total: int) -> None:
        if not self._started:
            # Started lazily here, not in __enter__: a service can do
            # meaningful work before its first item (e.g. TranscriptionService
            # loading the whisper model, which on first use downloads
            # multiple GB via huggingface_hub's own tqdm progress bar).
            # Progress.start() redirects stdout/stderr so our bars render
            # cleanly -- but that redirect breaks tqdm's \r-based in-place
            # updates, making a real, in-progress download look frozen.
            # Deferring start() until there's actually a bar to show keeps
            # that earlier output untouched.
            self._progress.start()
            self._started = True
        if self._overall_task is None:
            self._overall_task = self._progress.add_task("Overall", total=total)
        self._item_task = self._progress.add_task(item_id, total=1.0)

    def update_item(self, item_id: str, fraction: float) -> None:
        if self._item_task is not None:
            self._progress.update(self._item_task, completed=fraction)

    def finish_item(self, item_id: str) -> None:
        if self._item_task is not None:
            self._progress.remove_task(self._item_task)
            self._item_task = None
        if self._overall_task is not None:
            self._progress.advance(self._overall_task, 1)
