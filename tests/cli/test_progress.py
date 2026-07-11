import io
from concurrent.futures import ThreadPoolExecutor

from rich.console import Console

from videodoc.cli.progress import RichProgressReporter


def test_rich_progress_reporter_handles_concurrent_items():
    console = Console(file=io.StringIO(), force_terminal=False, width=120)
    total = 16

    with RichProgressReporter(console) as reporter:
        def run_one(i):
            item_id = f"C:/videos/folder-{i}/Demo.mp4"
            reporter.start_item(item_id, i, total)
            reporter.update_item(item_id, 0.25)
            reporter.update_item(item_id, 1.0)
            reporter.finish_item(item_id)

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(run_one, range(total)))

        assert reporter._item_tasks == {}
