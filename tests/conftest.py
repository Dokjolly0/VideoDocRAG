import pytest


@pytest.fixture(autouse=True)
def isolated_videodoc_env(tmp_path, monkeypatch):
    """Applies to ALL tests: no test may ever touch the real user data-dir
    (e.g. %LOCALAPPDATA%\\videodoc) or the real default home (~/VideoDocRAG)."""
    monkeypatch.setenv("VIDEODOC_DATA_DIR", str(tmp_path / "appdata"))
    monkeypatch.setenv("VIDEODOC_HOME", str(tmp_path / "home" / "VideoDocRAG"))
    yield
