import subprocess

import pytest

import videodoc.core.utils.setup_actions as setup_actions_module
from videodoc.core.utils.setup_actions import SetupActionError, run_fix_command


def test_run_fix_command_success_returns_output(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args, 0, stdout="done\n", stderr="")

    monkeypatch.setattr(setup_actions_module.subprocess, "run", fake_run)

    output = run_fix_command(("pip", "install", "x"))
    assert output == "done\n"
    assert captured["args"] == ["pip", "install", "x"]
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["check"] is True


def test_run_fix_command_capture_false_passed_through(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(setup_actions_module.subprocess, "run", fake_run)

    result = run_fix_command(("sudo", "apt", "install", "-y", "ffmpeg"), capture=False)
    assert captured["kwargs"]["capture_output"] is False
    assert result == ""


def test_run_fix_command_raises_on_called_process_error(monkeypatch):
    def fake_run(args, **kwargs):
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(setup_actions_module.subprocess, "run", fake_run)
    with pytest.raises(SetupActionError):
        run_fix_command(("winget", "install", "x"))


def test_run_fix_command_raises_on_oserror(monkeypatch):
    def fake_run(args, **kwargs):
        raise OSError("command not found")

    monkeypatch.setattr(setup_actions_module.subprocess, "run", fake_run)
    with pytest.raises(SetupActionError):
        run_fix_command(("nonexistent-tool",))
