from __future__ import annotations


class ProgressReporter:
    """No-op by default. The CLI passes a concrete (Rich-backed) subclass to
    observe batch progress; services stay agnostic to whether/how progress
    is shown -- core must never depend on rich."""

    def start_item(self, item_id: str, index: int, total: int) -> None:
        pass

    def update_item(self, item_id: str, fraction: float) -> None:
        pass

    def finish_item(self, item_id: str) -> None:
        pass
