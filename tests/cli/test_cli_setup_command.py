import typer
from typer.testing import CliRunner

import videodoc.cli.commands.setup as setup_command_module
import videodoc.core.services.doctor_service as doctor_service_module
import videodoc.core.services.setup_service as setup_service_module
from videodoc.cli.app import app
from videodoc.core.services.doctor_service import CheckResult, DoctorResult
from videodoc.core.utils.cuda import CudaProbeError

runner = CliRunner()


def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEODOC_HOME", str(tmp_path))
    monkeypatch.setenv("VIDEODOC_DATA_DIR", str(tmp_path))


def test_setup_clean_state_applies_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_service_module.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(doctor_service_module, "get_cuda_device_count", lambda: 0)
    _env(tmp_path, monkeypatch)

    result = runner.invoke(app, ["setup"])
    assert result.exit_code == 0
    assert "Applying fix" not in result.stdout


def test_setup_pip_fix_applies_without_prompting(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_service_module.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(doctor_service_module, "get_cuda_device_count", lambda: 1)
    monkeypatch.setattr(doctor_service_module, "probe_cublas_loadable", lambda name: (_ for _ in ()).throw(CudaProbeError("boom")))
    monkeypatch.setattr(setup_service_module, "run_fix_command", lambda command, **k: "installed")
    _env(tmp_path, monkeypatch)

    # No typer.confirm stub provided -- if the code wrongly prompted for a
    # pip-kind fix, CliRunner (no stdin) would fail rather than hang, which
    # is itself proof the flow never asks.
    result = runner.invoke(app, ["setup"])
    assert result.exit_code == 0
    assert "Applying fix" in result.stdout
    assert "Applied" in result.stdout


def test_setup_system_fix_prompts_and_respects_no(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_service_module.shutil, "which", lambda tool: None)
    monkeypatch.setattr(doctor_service_module, "get_cuda_device_count", lambda: 0)
    monkeypatch.setattr(doctor_service_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(typer, "confirm", lambda *a, **k: False)
    _env(tmp_path, monkeypatch)

    result = runner.invoke(app, ["setup"])
    assert "Skipped." in result.stdout
    assert result.exit_code == 1  # ffmpeg error was declined, still unresolved


def test_setup_system_fix_prompts_and_respects_yes(tmp_path, monkeypatch):
    # doctor_service_module.shutil and setup_service_module.shutil are the
    # SAME module object (both do a plain `import shutil`) -- one combined
    # stub distinguishing ffprobe/ffmpeg (missing, drives the doctor check)
    # from winget (present, so SetupService's own pre-check passes), not two
    # separate monkeypatch.setattr calls that would silently overwrite
    # each other.
    monkeypatch.setattr(doctor_service_module.shutil, "which", lambda tool: None if tool in ("ffprobe", "ffmpeg") else r"C:\winget.exe")
    monkeypatch.setattr(doctor_service_module, "get_cuda_device_count", lambda: 0)
    monkeypatch.setattr(doctor_service_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(typer, "confirm", lambda *a, **k: True)
    monkeypatch.setattr(setup_service_module, "run_fix_command", lambda command, **k: "ffmpeg installed")
    _env(tmp_path, monkeypatch)

    result = runner.invoke(app, ["setup"])
    assert "Applied" in result.stdout
    assert result.exit_code == 0  # a successful system fix counts as resolved (v1)


def test_setup_fix_failure_reported_without_aborting(tmp_path, monkeypatch):
    # ffprobe/ffmpeg AND winget itself all missing -- SetupService.apply
    # must report "not found on PATH" without ever calling run_fix_command.
    monkeypatch.setattr(doctor_service_module.shutil, "which", lambda tool: None)
    monkeypatch.setattr(doctor_service_module, "get_cuda_device_count", lambda: 0)
    monkeypatch.setattr(doctor_service_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(typer, "confirm", lambda *a, **k: True)
    _env(tmp_path, monkeypatch)

    result = runner.invoke(app, ["setup"])
    assert "Fix failed" in result.stdout
    assert result.exit_code == 1


def test_setup_manual_fix_only_prints_instructions(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_service_module.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(doctor_service_module, "get_cuda_device_count", lambda: 0)
    monkeypatch.setattr(doctor_service_module.sys, "version_info", (3, 9, 0))
    _env(tmp_path, monkeypatch)

    # No confirm/run_fix_command stub needed: a manual fix must never reach
    # either -- if it did, this test would hang (no stdin) or fail loudly.
    result = runner.invoke(app, ["setup"])
    assert "Manual fix required" in result.stdout
    assert result.exit_code == 1  # never auto-resolved


def test_setup_check_with_no_fix_available_is_reported_and_left_unresolved(tmp_path, monkeypatch):
    broken = CheckResult("mystery", "Mystery check", "error", "something is wrong, no fix known")
    fake_result = DoctorResult((broken,))

    class FakeDoctorService:
        def __init__(self, *a, **k):
            pass

        def run(self):
            return fake_result

    monkeypatch.setattr(setup_command_module, "DoctorService", FakeDoctorService)
    _env(tmp_path, monkeypatch)

    result = runner.invoke(app, ["setup"])
    assert "Mystery check" in result.stdout
    assert "Applying fix" not in result.stdout
    assert result.exit_code == 1
