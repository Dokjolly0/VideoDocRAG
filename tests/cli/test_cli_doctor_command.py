from typer.testing import CliRunner

import videodoc.core.services.doctor_service as doctor_service_module
from videodoc.cli.app import app

runner = CliRunner()


def _make_everything_ok(monkeypatch):
    monkeypatch.setattr(doctor_service_module.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(doctor_service_module, "get_cuda_device_count", lambda: 0)


def test_doctor_exit_code_0_when_clean(tmp_path, monkeypatch):
    _make_everything_ok(monkeypatch)
    monkeypatch.setenv("VIDEODOC_HOME", str(tmp_path))
    monkeypatch.setenv("VIDEODOC_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "OK" in result.stdout


def test_doctor_exit_code_1_when_any_error(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_service_module.shutil, "which", lambda tool: None)
    monkeypatch.setattr(doctor_service_module, "get_cuda_device_count", lambda: 0)
    monkeypatch.setenv("VIDEODOC_HOME", str(tmp_path))
    monkeypatch.setenv("VIDEODOC_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "ERROR" in result.stdout


def test_doctor_warning_alone_keeps_exit_code_0(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_service_module.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(doctor_service_module, "get_cuda_device_count", lambda: 1)

    def raising(name):
        from videodoc.core.utils.cuda import CudaProbeError
        raise CudaProbeError("boom")

    monkeypatch.setattr(doctor_service_module, "probe_cublas_loadable", raising)
    monkeypatch.setenv("VIDEODOC_HOME", str(tmp_path))
    monkeypatch.setenv("VIDEODOC_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "WARN" in result.stdout
