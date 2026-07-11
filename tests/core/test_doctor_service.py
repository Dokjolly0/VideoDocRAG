import pytest

import videodoc.core.services.doctor_service as doctor_service_module
from videodoc.core.services.doctor_service import DoctorService
from videodoc.core.services.registry_service import ProjectRegistry
from videodoc.core.utils.cuda import CudaProbeError


def _find(result, check_id):
    return next(c for c in result.checks if c.id == check_id)


# --- Python version -------------------------------------------------------


def test_python_version_ok(tmp_path):
    result = DoctorService(version_info=(3, 12, 1), registry=ProjectRegistry(tmp_path / "r.json"), projects_home=tmp_path).run()
    assert _find(result, "python_version").status == "ok"


def test_python_version_too_old_is_error(tmp_path):
    result = DoctorService(version_info=(3, 9, 0), registry=ProjectRegistry(tmp_path / "r.json"), projects_home=tmp_path).run()
    check = _find(result, "python_version")
    assert check.status == "error"
    assert check.fix_kind == "manual"


# --- FFmpeg (ffprobe + ffmpeg merged into one check) -----------------------


def test_ffmpeg_both_present_is_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_service_module.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    result = DoctorService(registry=ProjectRegistry(tmp_path / "r.json"), projects_home=tmp_path).run()
    assert _find(result, "ffmpeg").status == "ok"


def test_ffmpeg_one_missing_is_error(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_service_module.shutil, "which", lambda tool: None if tool == "ffmpeg" else "/usr/bin/ffprobe")
    result = DoctorService(registry=ProjectRegistry(tmp_path / "r.json"), projects_home=tmp_path).run()
    check = _find(result, "ffmpeg")
    assert check.status == "error"
    assert "ffmpeg" in check.message
    assert "ffprobe" not in check.message  # only the actually-missing binary is named


def test_ffmpeg_neither_present_reports_system_fix_per_os(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_service_module.shutil, "which", lambda tool: None)
    result = DoctorService(platform_name="Windows", registry=ProjectRegistry(tmp_path / "r.json"), projects_home=tmp_path).run()
    check = _find(result, "ffmpeg")
    assert check.status == "error"
    assert check.fix_kind == "system"
    assert check.fix_command[0] == "winget"


def test_ffmpeg_unknown_platform_is_manual_fix(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_service_module.shutil, "which", lambda tool: None)
    result = DoctorService(platform_name="FreeBSD", registry=ProjectRegistry(tmp_path / "r.json"), projects_home=tmp_path).run()
    check = _find(result, "ffmpeg")
    assert check.fix_kind == "manual"


# --- faster-whisper ---------------------------------------------------------


def test_faster_whisper_importable_is_ok(tmp_path):
    result = DoctorService(registry=ProjectRegistry(tmp_path / "r.json"), projects_home=tmp_path).run()
    assert _find(result, "faster_whisper").status == "ok"


def test_faster_whisper_import_failure_is_error(tmp_path, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if name == "faster_whisper":
            raise ImportError("no module named faster_whisper")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing_import)
    result = DoctorService(registry=ProjectRegistry(tmp_path / "r.json"), projects_home=tmp_path).run()
    check = _find(result, "faster_whisper")
    assert check.status == "error"
    assert check.fix_kind == "manual"


# --- CUDA / GPU --------------------------------------------------------------


def test_cuda_zero_devices_is_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_service_module, "get_cuda_device_count", lambda: 0)
    result = DoctorService(registry=ProjectRegistry(tmp_path / "r.json"), projects_home=tmp_path).run()
    check = _find(result, "cuda")
    assert check.status == "ok"
    assert "no CUDA device" in check.message


def test_cuda_device_count_probe_failure_treated_as_zero(tmp_path, monkeypatch):
    def raising():
        raise CudaProbeError("ctranslate2 not importable")

    monkeypatch.setattr(doctor_service_module, "get_cuda_device_count", raising)
    result = DoctorService(registry=ProjectRegistry(tmp_path / "r.json"), projects_home=tmp_path).run()
    assert _find(result, "cuda").status == "ok"


def test_cuda_devices_present_and_cublas_loadable_is_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_service_module, "get_cuda_device_count", lambda: 1)
    monkeypatch.setattr(doctor_service_module, "probe_cublas_loadable", lambda name: None)
    result = DoctorService(platform_name="Windows", registry=ProjectRegistry(tmp_path / "r.json"), projects_home=tmp_path).run()
    assert _find(result, "cuda").status == "ok"


def test_cuda_devices_present_but_cublas_unloadable_is_warning_with_pip_fix_windows(tmp_path, monkeypatch):
    def raising(name):
        raise CudaProbeError(f"Could not load {name}")

    monkeypatch.setattr(doctor_service_module, "get_cuda_device_count", lambda: 1)
    monkeypatch.setattr(doctor_service_module, "probe_cublas_loadable", raising)
    result = DoctorService(platform_name="Windows", registry=ProjectRegistry(tmp_path / "r.json"), projects_home=tmp_path).run()
    check = _find(result, "cuda")
    assert check.status == "warning"  # never "error": transcribe still works per-video
    assert check.fix_kind == "pip"
    assert "nvidia-cublas-cu12" in check.fix_command
    assert check.fix_description is not None  # Windows-only PATH note


def test_cuda_devices_present_but_cublas_unloadable_no_path_note_on_linux(tmp_path, monkeypatch):
    def raising(name):
        raise CudaProbeError(f"Could not load {name}")

    monkeypatch.setattr(doctor_service_module, "get_cuda_device_count", lambda: 1)
    monkeypatch.setattr(doctor_service_module, "probe_cublas_loadable", raising)
    result = DoctorService(platform_name="Linux", registry=ProjectRegistry(tmp_path / "r.json"), projects_home=tmp_path).run()
    check = _find(result, "cuda")
    assert check.status == "warning"
    assert check.fix_description is None


def test_cuda_macos_short_circuits_without_probing(tmp_path, monkeypatch):
    called = {"n": 0}

    def counting_probe(name):
        called["n"] += 1

    monkeypatch.setattr(doctor_service_module, "get_cuda_device_count", lambda: 1)
    monkeypatch.setattr(doctor_service_module, "probe_cublas_loadable", counting_probe)
    result = DoctorService(platform_name="Darwin", registry=ProjectRegistry(tmp_path / "r.json"), projects_home=tmp_path).run()
    assert _find(result, "cuda").status == "ok"
    assert called["n"] == 0


# --- Registry ----------------------------------------------------------------


def test_registry_healthy_reports_count(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    registry.register("demo", tmp_path / "demo")
    result = DoctorService(registry=registry, projects_home=tmp_path).run()
    check = _find(result, "registry")
    assert check.status == "ok"
    assert "1 project" in check.message


def test_registry_corrupted_reports_warning(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text("not valid json", encoding="utf-8")
    registry = ProjectRegistry(registry_path)
    result = DoctorService(registry=registry, projects_home=tmp_path).run()
    check = _find(result, "registry")
    assert check.status == "warning"
    assert "quarantined" in check.message


def test_registry_empty_is_ok(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    result = DoctorService(registry=registry, projects_home=tmp_path).run()
    check = _find(result, "registry")
    assert check.status == "ok"
    assert "0 project" in check.message


# --- Projects home -------------------------------------------------------


def test_projects_home_writable_is_ok(tmp_path):
    home = tmp_path / "projects"
    home.mkdir()
    result = DoctorService(registry=ProjectRegistry(tmp_path / "r.json"), projects_home=home).run()
    assert _find(result, "projects_home").status == "ok"


def test_projects_home_reports_env_override(tmp_path, monkeypatch):
    home = tmp_path / "projects"
    home.mkdir()
    monkeypatch.setenv("VIDEODOC_HOME", str(home))
    result = DoctorService(registry=ProjectRegistry(tmp_path / "r.json"), projects_home=home).run()
    assert "VIDEODOC_HOME" in _find(result, "projects_home").message


def test_projects_home_not_writable_is_error(tmp_path, monkeypatch):
    # projects_home itself doesn't exist yet -- the check must walk up to
    # the nearest existing ancestor (tmp_path) and check that instead.
    home = tmp_path / "projects" / "nested"
    monkeypatch.setattr(doctor_service_module.os, "access", lambda path, mode: False)
    result = DoctorService(registry=ProjectRegistry(tmp_path / "r.json"), projects_home=home).run()
    check = _find(result, "projects_home")
    assert check.status == "error"
    assert check.fix_kind == "manual"
    assert str(tmp_path) in check.message  # walked up to the existing ancestor


# --- Resilience: one check's crash never aborts the whole run --------------


def test_one_check_crashing_does_not_abort_the_run(tmp_path, monkeypatch):
    # _check_cuda only catches CudaProbeError internally -- a different,
    # unexpected exception type must still be caught by run()'s own
    # defensive wrapper around each check, not crash the whole command.
    def raising():
        raise RuntimeError("boom")

    monkeypatch.setattr(doctor_service_module, "get_cuda_device_count", raising)
    result = DoctorService(registry=ProjectRegistry(tmp_path / "r.json"), projects_home=tmp_path).run()

    cuda_check = _find(result, "cuda")
    assert cuda_check.status == "error"
    assert "boom" in cuda_check.message
    # every other check still ran and reported normally
    assert _find(result, "python_version").status == "ok"
    assert len(result.checks) == 6


# --- DoctorResult.has_errors -------------------------------------------------


def test_has_errors_true_when_any_check_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_service_module.shutil, "which", lambda tool: None)
    result = DoctorService(platform_name="Windows", registry=ProjectRegistry(tmp_path / "r.json"), projects_home=tmp_path).run()
    assert result.has_errors is True


def test_has_errors_false_when_only_warnings_or_ok(tmp_path, monkeypatch):
    def raising(name):
        raise CudaProbeError("boom")

    monkeypatch.setattr(doctor_service_module, "get_cuda_device_count", lambda: 1)
    monkeypatch.setattr(doctor_service_module, "probe_cublas_loadable", raising)
    result = DoctorService(platform_name="Windows", registry=ProjectRegistry(tmp_path / "r.json"), projects_home=tmp_path).run()
    assert _find(result, "cuda").status == "warning"
    assert result.has_errors is False
