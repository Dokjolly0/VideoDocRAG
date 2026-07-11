import pytest

import videodoc.core.services.setup_service as setup_service_module
from videodoc.core.services.doctor_service import CheckResult
from videodoc.core.services.setup_service import SetupService
from videodoc.core.utils.setup_actions import SetupActionError


def test_apply_no_fix_kind_is_skipped():
    check = CheckResult("x", "X", "error", "broken")
    result = SetupService().apply(check)
    assert result.status == "skipped"


def test_apply_pip_kind_without_fix_command_fails_defensively():
    # Not reachable via any real doctor check today (every pip/system check
    # always sets fix_command) -- a defensive guard against a malformed
    # CheckResult, still worth confirming it fails cleanly, not with an
    # IndexError on command[0].
    check = CheckResult("x", "X", "error", "broken", fix_kind="pip", fix_command=None)
    result = SetupService().apply(check)
    assert result.status == "failed"
    assert "no fix command" in result.detail


def test_apply_manual_fix_never_runs_a_command(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(setup_service_module, "run_fix_command", lambda *a, **k: called.__setitem__("n", called["n"] + 1))

    check = CheckResult("x", "X", "error", "broken", fix_kind="manual", fix_description="do it yourself")
    result = SetupService().apply(check)

    assert result.status == "manual"
    assert result.detail == "do it yourself"
    assert called["n"] == 0


def test_apply_pip_fix_success(monkeypatch):
    monkeypatch.setattr(setup_service_module, "run_fix_command", lambda command, **k: "installed")
    monkeypatch.setattr(setup_service_module.shutil, "which", lambda tool: r"C:\python\Scripts\python.exe")

    check = CheckResult("cuda", "GPU / CUDA", "warning", "broken", fix_kind="pip", fix_command=("python", "-m", "pip", "install", "x"))
    result = SetupService().apply(check)

    assert result.status == "applied"
    assert result.detail == "installed"


def test_apply_system_fix_tool_missing_from_path_never_calls_run_fix_command(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(setup_service_module, "run_fix_command", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    monkeypatch.setattr(setup_service_module.shutil, "which", lambda tool: None)

    check = CheckResult("ffmpeg", "FFmpeg", "error", "missing", fix_kind="system", fix_command=("winget", "install", "Gyan.FFmpeg"))
    result = SetupService().apply(check)

    assert result.status == "failed"
    assert "not found on PATH" in result.detail
    assert called["n"] == 0


def test_apply_system_fix_failure_reported(monkeypatch):
    def failing(command, **kwargs):
        raise SetupActionError("exit code 1")

    monkeypatch.setattr(setup_service_module, "run_fix_command", failing)
    monkeypatch.setattr(setup_service_module.shutil, "which", lambda tool: "/usr/bin/brew")

    check = CheckResult("ffmpeg", "FFmpeg", "error", "missing", fix_kind="system", fix_command=("brew", "install", "ffmpeg"))
    result = SetupService().apply(check)

    assert result.status == "failed"
    assert "exit code 1" in result.detail


def test_apply_apt_system_fix_uses_capture_false(monkeypatch):
    captured = {}

    def fake_run(command, *, capture):
        captured["capture"] = capture
        return "ok"

    monkeypatch.setattr(setup_service_module, "run_fix_command", fake_run)
    monkeypatch.setattr(setup_service_module.shutil, "which", lambda tool: "/usr/bin/sudo")

    check = CheckResult("ffmpeg", "FFmpeg", "error", "missing", fix_kind="system", fix_command=("sudo", "apt", "install", "-y", "ffmpeg"))
    SetupService().apply(check)

    assert captured["capture"] is False


def test_apply_non_apt_system_fix_uses_capture_true(monkeypatch):
    captured = {}

    def fake_run(command, *, capture):
        captured["capture"] = capture
        return "ok"

    monkeypatch.setattr(setup_service_module, "run_fix_command", fake_run)
    monkeypatch.setattr(setup_service_module.shutil, "which", lambda tool: "C:\\winget.exe")

    check = CheckResult("ffmpeg", "FFmpeg", "error", "missing", fix_kind="system", fix_command=("winget", "install", "Gyan.FFmpeg"))
    SetupService().apply(check)

    assert captured["capture"] is True
