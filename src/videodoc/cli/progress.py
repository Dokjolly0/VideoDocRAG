from __future__ import annotations

import threading
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID, TaskProgressColumn, TextColumn, TimeElapsedColumn

from videodoc.core.utils.progress import ProgressReporter


class RichProgressReporter(ProgressReporter):
    """Context manager: an 'Overall' bar plus one bar for each active item.

    The services may now call this from worker threads. Rich serializes its
    rendering internally, while this class protects its own mapping/state so
    item updates always hit the right task.
    """

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
        self._lock = threading.Lock()
        self._started = False
        self._overall_task: TaskID | None = None
        self._item_tasks: dict[str, TaskID] = {}

    def __enter__(self) -> "RichProgressReporter":
        return self

    def __exit__(self, *exc_info: object) -> None:
        with self._lock:
            if self._started:
                self._progress.stop()
                self._started = False
                self._overall_task = None
                self._item_tasks.clear()

    def start_item(self, item_id: str, index: int, total: int) -> None:
        del index  # The overall bar is completion-count based under concurrency.
        with self._lock:
            if not self._started:
                # Started lazily here, not in __enter__: a service can do
                # meaningful work before its first item (e.g. TranscriptionService
                # loading the whisper model, which on first use downloads
                # multiple GB via huggingface_hub's own tqdm progress bar).
                self._progress.start()
                self._started = True
            if self._overall_task is None:
                self._overall_task = self._progress.add_task("Overall", total=total)
            old_task = self._item_tasks.pop(item_id, None)
            if old_task is not None:
                self._progress.remove_task(old_task)
            self._item_tasks[item_id] = self._progress.add_task(_display_label(item_id), total=1.0)

    def update_item(self, item_id: str, fraction: float) -> None:
        with self._lock:
            task_id = self._item_tasks.get(item_id)
            if task_id is not None:
                self._progress.update(task_id, completed=max(0.0, min(1.0, fraction)))

    def finish_item(self, item_id: str) -> None:
        with self._lock:
            task_id = self._item_tasks.pop(item_id, None)
            if task_id is None:
                return
            self._progress.remove_task(task_id)
            if self._overall_task is not None:
                self._progress.advance(self._overall_task, 1)

    def announce(self, message: str) -> None:
        # Printed through self._progress.console (not a bare print()) so it
        # interleaves correctly with the bars once the Live display is running.
        with self._lock:
            self._progress.console.print(message)


def _display_label(item_id: str) -> str:
    path = Path(item_id)
    return path.name or item_id
