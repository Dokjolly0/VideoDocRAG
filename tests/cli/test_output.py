from datetime import datetime, timezone
from pathlib import Path

from videodoc.cli.output import (
    console,
    error_console,
    print_check_result,
    print_error,
    print_warning,
    render_projects_table,
    render_summary_table,
)
from videodoc.core.services.registry_service import ProjectEntry


def _capture(fn) -> str:
    with console.capture() as capture:
        fn()
    return capture.get()


def test_print_check_result_ok_uses_green_ok_word():
    output = _capture(lambda: print_check_result("ok", "everything fine"))
    assert "OK" in output
    assert "everything fine" in output


def test_print_check_result_warning_uses_yellow_warn_word():
    output = _capture(lambda: print_check_result("warning", "something to watch"))
    assert "WARN" in output
    assert "something to watch" in output


def test_print_check_result_error_uses_red_error_word():
    output = _capture(lambda: print_check_result("error", "something broken"))
    assert "ERROR" in output
    assert "something broken" in output


def test_print_check_result_never_emits_unicode_status_glyphs():
    """Regression test: raw Unicode status glyphs (checkmarks/warning
    triangles) were verified to crash with UnicodeEncodeError on a real
    Windows console during this feature's own design -- this function must
    only ever use ASCII status words."""
    for status in ("ok", "warning", "error"):
        output = _capture(lambda status=status: print_check_result(status, "msg"))
        output.encode("ascii")  # raises UnicodeEncodeError if any non-ASCII char slipped in


def test_render_summary_table_shows_all_rows():
    output = _capture(lambda: render_summary_table([("Videos", "8 found"), ("Attachments", "0 found")]))
    assert "Videos" in output
    assert "8 found" in output
    assert "Attachments" in output
    assert "0 found" in output


def test_render_summary_table_empty_rows_does_not_crash():
    _capture(lambda: render_summary_table([]))  # must not raise


# --- Regression: dynamic content must never be parsed as Rich markup -------
#
# Every function below used to interpolate a caller-supplied string (an
# error message, a warning, a filesystem path) directly into a string handed
# to Console.print()/Table.add_row(), which by default parses '[...]' as
# Rich markup. Two real, reproduced failure modes:
#   1. A message containing an unmatched closing tag (e.g. a stray
#      "[/red]") raises rich.errors.MarkupError -- a warning/error about to
#      be *printed* would instead crash the whole command.
#   2. A Windows path containing literal brackets (e.g. "D:\[work]\..." --
#      a legal folder name) silently loses characters: '[work]' is consumed
#      as if it were a markup tag instead of being displayed.


def _error_capture(fn) -> str:
    with error_console.capture() as capture:
        fn()
    return capture.get()


def test_print_error_with_unmatched_bracket_does_not_crash():
    output = _error_capture(lambda: print_error("boom [/red] not a real tag"))
    assert "[/red]" in output


def test_print_error_preserves_bracketed_path():
    path = r"D:\[work]\registry.json"
    output = _error_capture(lambda: print_error(f"cannot write {path}"))
    assert path in output


def test_print_warning_with_unmatched_bracket_does_not_crash():
    output = _capture(lambda: print_warning("boom [/red] not a real tag"))
    assert "[/red]" in output


def test_print_warning_preserves_bracketed_path():
    path = r"D:\[work]\registry.json"
    output = _capture(lambda: print_warning(f"stale artifact at {path}"))
    assert path in output


def test_print_check_result_with_unmatched_bracket_does_not_crash():
    output = _capture(lambda: print_check_result("error", "boom [/red] not a real tag"))
    assert "[/red]" in output


def test_print_check_result_preserves_bracketed_path():
    path = r"D:\[work]\registry.json"
    output = _capture(lambda: print_check_result("ok", f"registry at {path}"))
    assert path in output


def test_render_summary_table_with_unmatched_bracket_does_not_crash():
    output = _capture(lambda: render_summary_table([("Videos", "8 found [/red]")]))
    assert "[/red]" in output


def test_render_summary_table_preserves_bracketed_path():
    path = r"D:\[work]\Videos"
    output = _capture(lambda: render_summary_table([("Videos", f"8 found (external: {path})")]))
    assert path in output


def test_render_projects_table_preserves_bracketed_path():
    entry = ProjectEntry(name="demo", path=Path(r"D:\[work]\demo"), created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    output = _capture(lambda: render_projects_table([entry]))
    assert r"D:\[work]\demo" in output
