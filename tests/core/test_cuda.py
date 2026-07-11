import sys
import types

import pytest

from videodoc.core.utils.cuda import CudaProbeError, get_cuda_device_count, probe_cublas_loadable


def test_get_cuda_device_count_success(monkeypatch):
    fake_module = types.SimpleNamespace(get_cuda_device_count=lambda: 2)
    monkeypatch.setitem(sys.modules, "ctranslate2", fake_module)
    assert get_cuda_device_count() == 2


def test_get_cuda_device_count_missing_package_raises(monkeypatch):
    monkeypatch.setitem(sys.modules, "ctranslate2", None)
    with pytest.raises(CudaProbeError):
        get_cuda_device_count()


def test_get_cuda_device_count_call_failure_raises(monkeypatch):
    def failing():
        raise RuntimeError("driver not initialized")

    fake_module = types.SimpleNamespace(get_cuda_device_count=failing)
    monkeypatch.setitem(sys.modules, "ctranslate2", fake_module)
    with pytest.raises(CudaProbeError):
        get_cuda_device_count()


def test_probe_cublas_loadable_success(monkeypatch):
    import videodoc.core.utils.cuda as cuda_module

    monkeypatch.setattr(cuda_module.ctypes, "CDLL", lambda name, **kwargs: object())
    probe_cublas_loadable("cublas64_12.dll")  # must not raise


def test_probe_cublas_loadable_raises_on_oserror(monkeypatch):
    import videodoc.core.utils.cuda as cuda_module

    def failing(name, **kwargs):
        raise OSError("The specified module could not be found.")

    monkeypatch.setattr(cuda_module.ctypes, "CDLL", failing)
    with pytest.raises(CudaProbeError):
        probe_cublas_loadable("cublas64_12.dll")


def test_probe_cublas_loadable_passes_winmode_zero(monkeypatch):
    """Regression test: found empirically that ctypes.CDLL's default
    Python 3.8+ Windows behavior does NOT search PATH at all (a deliberate
    anti-DLL-hijacking hardening) -- without winmode=0 explicitly restoring
    the legacy PATH-inclusive search, this probe reports a false
    'not loadable' even when the exact library is genuinely on PATH and
    the real faster-whisper code path would succeed."""
    import videodoc.core.utils.cuda as cuda_module

    captured = {}

    def fake_cdll(name, **kwargs):
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(cuda_module.ctypes, "CDLL", fake_cdll)
    probe_cublas_loadable("cublas64_12.dll")
    assert captured["kwargs"] == {"winmode": 0}
