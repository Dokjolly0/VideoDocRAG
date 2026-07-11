import json
import logging
from pathlib import Path

import pytest

import videodoc.core.services.registry_service as registry_module
from videodoc.core.errors import ProjectNotFoundError, RegistryConflictError
from videodoc.core.services.registry_service import ProjectRegistry


def test_default_path_respects_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEODOC_DATA_DIR", str(tmp_path / "custom"))
    assert ProjectRegistry.default_path() == tmp_path / "custom" / "registry.json"


def test_default_path_falls_back_to_platformdirs(tmp_path, monkeypatch):
    monkeypatch.delenv("VIDEODOC_DATA_DIR", raising=False)
    monkeypatch.setattr(
        registry_module.platformdirs, "user_data_dir", lambda *a, **k: str(tmp_path / "platformdirs-fallback")
    )
    assert ProjectRegistry.default_path() == tmp_path / "platformdirs-fallback" / "registry.json"


def test_empty_registry_does_not_create_file(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry = ProjectRegistry(registry_path)
    assert registry.list_all() == []
    assert not registry_path.exists()


def test_register_creates_file_and_is_visible_from_new_instance(tmp_path):
    registry_path = tmp_path / "registry.json"
    ProjectRegistry(registry_path).register("demo", tmp_path / "demo")
    assert registry_path.exists()
    entries = ProjectRegistry(registry_path).list_all()
    assert [e.name for e in entries] == ["demo"]


def test_register_is_idempotent_for_same_path(tmp_path):
    registry_path = tmp_path / "registry.json"
    project_dir = tmp_path / "demo"
    registry = ProjectRegistry(registry_path)
    registry.register("demo", project_dir)
    registry.register("demo", project_dir)
    assert len(registry.list_all()) == 1


def test_register_conflict_on_different_path(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry = ProjectRegistry(registry_path)
    registry.register("demo", tmp_path / "demo-a")
    with pytest.raises(RegistryConflictError):
        registry.register("demo", tmp_path / "demo-b")


def test_unlink_removes_entry(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry = ProjectRegistry(registry_path)
    registry.register("demo", tmp_path / "demo")
    registry.unlink("demo")
    assert registry.list_all() == []


def test_unlink_unknown_raises(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    with pytest.raises(ProjectNotFoundError):
        registry.unlink("nope")


def test_resolve_unknown_returns_none(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    assert registry.resolve("nope") is None


def test_corrupted_registry_is_quarantined(tmp_path, caplog):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text("not valid json", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        entries = ProjectRegistry(registry_path).list_all()
    assert entries == []
    corrupted = list(tmp_path.glob("registry.json.corrupted-*"))
    assert len(corrupted) == 1
    assert "corrupted" in caplog.text.lower()


def test_registry_missing_projects_key_is_quarantined(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"version": 1}), encoding="utf-8")
    assert ProjectRegistry(registry_path).list_all() == []
    assert list(tmp_path.glob("registry.json.corrupted-*"))


def test_registered_paths_are_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    registry_path = tmp_path / "registry.json"
    registry = ProjectRegistry(registry_path)
    registry.register("demo", Path("relative-dir"))
    resolved = registry.resolve("demo")
    assert resolved.is_absolute()


def _write_raw_registry(registry_path: Path, projects: dict) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps({"version": 1, "projects": projects}), encoding="utf-8")


def test_list_all_skips_malformed_entry_but_keeps_valid_ones(tmp_path, caplog):
    registry_path = tmp_path / "registry.json"
    _write_raw_registry(
        registry_path,
        {
            "good": {"path": str(tmp_path / "good"), "created_at": "2026-01-01T00:00:00+00:00"},
            "no-path": {"created_at": "2026-01-01T00:00:00+00:00"},
        },
    )
    with caplog.at_level(logging.WARNING):
        entries = ProjectRegistry(registry_path).list_all()
    assert [e.name for e in entries] == ["good"]
    assert "no-path" in caplog.text


def test_resolve_returns_none_for_entry_with_missing_path(tmp_path):
    registry_path = tmp_path / "registry.json"
    _write_raw_registry(registry_path, {"broken": {"created_at": "2026-01-01T00:00:00+00:00"}})
    assert ProjectRegistry(registry_path).resolve("broken") is None


def test_unlink_removes_malformed_entry_without_crashing(tmp_path):
    """A malformed entry must always be removable -- 'unlink' is the tool
    meant to clean it up, so it must never itself be blocked by bad data."""
    registry_path = tmp_path / "registry.json"
    _write_raw_registry(registry_path, {"broken": {"created_at": "not-a-real-timestamp"}})
    registry = ProjectRegistry(registry_path)

    entry = registry.unlink("broken")
    assert entry.name == "broken"
    assert registry.list_all() == []
    assert registry.resolve("broken") is None


def test_register_heals_a_malformed_existing_entry(tmp_path):
    registry_path = tmp_path / "registry.json"
    _write_raw_registry(registry_path, {"demo": {"created_at": "2026-01-01T00:00:00+00:00"}})
    registry = ProjectRegistry(registry_path)

    target = tmp_path / "demo"
    entry = registry.register("demo", target)
    assert entry.path == target.resolve()
    assert registry.resolve("demo") == target.resolve()


def test_last_load_was_corrupted_false_after_clean_load(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry = ProjectRegistry(registry_path)
    registry.list_all()
    assert registry.last_load_was_corrupted is False


def test_last_load_was_corrupted_true_immediately_after_quarantine(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text("not valid json", encoding="utf-8")
    registry = ProjectRegistry(registry_path)

    registry.list_all()
    assert registry.last_load_was_corrupted is True


def test_last_load_was_corrupted_resets_on_next_clean_load(tmp_path):
    """A registry that was corrupted (and quarantined into an empty state)
    must report last_load_was_corrupted as False again on a subsequent
    load of that now-healthy empty state -- the flag reflects the most
    recent load, not 'was ever corrupted'."""
    registry_path = tmp_path / "registry.json"
    registry_path.write_text("not valid json", encoding="utf-8")
    registry = ProjectRegistry(registry_path)

    registry.list_all()
    assert registry.last_load_was_corrupted is True

    registry.list_all()
    assert registry.last_load_was_corrupted is False


def test_registry_path_reflects_explicit_path(tmp_path):
    registry_path = tmp_path / "custom-registry.json"
    assert ProjectRegistry(registry_path).registry_path == registry_path


def test_registry_path_falls_back_to_default(monkeypatch, tmp_path):
    monkeypatch.setenv("VIDEODOC_DATA_DIR", str(tmp_path))
    assert ProjectRegistry().registry_path == tmp_path / "registry.json"
