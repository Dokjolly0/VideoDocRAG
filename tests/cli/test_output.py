from videodoc.cli.output import console, print_check_result, render_summary_table


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
