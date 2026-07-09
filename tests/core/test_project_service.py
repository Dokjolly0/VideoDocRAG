from pathlib import Path

import pytest

import videodoc.core.services.project_service as project_service_module
from videodoc.core.errors import (
    InvalidConfigError,
    InvalidProjectNameError,
    ProjectNotFoundError,
    RegistryConflictError,
)
from videodoc.core.services.project_service import ProjectService, default_projects_home
from videodoc.core.services.registry_service import ProjectRegistry
from videodoc.core.utils.slug import slugify


def test_slugify_basic():
    assert slugify("Corso Software X") == "corso-software-x"


def test_slugify_accents_and_symbols():
    assert slugify("Città è già pronta!!") == "citta-e-gia-pronta"


def test_slugify_empty_result_raises():
    with pytest.raises(ValueError):
        slugify("!!!")


def test_default_projects_home_respects_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEODOC_HOME", str(tmp_path / "custom-home"))
    assert default_projects_home() == tmp_path / "custom-home"


def test_default_projects_home_falls_back_to_user_home(tmp_path, monkeypatch):
    monkeypatch.delenv("VIDEODOC_HOME", raising=False)
    monkeypatch.setattr(project_service_module.Path, "home", classmethod(lambda cls: tmp_path))
    assert default_projects_home() == tmp_path / "VideoDocRAG" / "projects"


def test_init_creates_expected_structure(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    result = ProjectService.init("Demo Course", path=tmp_path / "demo-course", registry=registry)

    assert result.created is True
    for sub in ("videos", "attachments", "codebase", "workdir", "indexes", "sessions", "docs"):
        assert (result.project_dir / sub).is_dir()
    assert (result.project_dir / "sources.yaml").is_file()
    assert result.config_path.is_file()
    assert not (result.project_dir / "project.db").exists()
    assert registry.resolve("Demo Course") == result.project_dir


def test_init_with_explicit_path_uses_it_directly(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    target = tmp_path / "somewhere-else"
    result = ProjectService.init("demo", path=target, registry=registry)
    assert result.project_dir == target.resolve()


def test_init_is_idempotent_and_keeps_existing_config(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    project_dir = tmp_path / "demo"
    first = ProjectService.init("demo", path=project_dir, registry=registry)
    assert first.created is True

    # Manually tweak config.yaml to prove a second init doesn't overwrite it.
    text = first.config_path.read_text(encoding="utf-8")
    text = text.replace("language: it", "language: en")
    first.config_path.write_text(text, encoding="utf-8")

    second = ProjectService.init("demo", path=project_dir, registry=registry)
    assert second.created is False
    assert "language: en" in second.config_path.read_text(encoding="utf-8")


def test_init_conflict_on_different_path_does_not_touch_filesystem(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    ProjectService.init("demo", path=tmp_path / "path-a", registry=registry)

    other_path = tmp_path / "path-b"
    with pytest.raises(RegistryConflictError):
        ProjectService.init("demo", path=other_path, registry=registry)
    assert not other_path.exists()


def test_init_invalid_name_raises_domain_error(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    with pytest.raises(InvalidProjectNameError):
        ProjectService.init("!!!", registry=registry)


def test_load_by_path_does_not_require_registry(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    result = ProjectService.init("demo", path=tmp_path / "demo", registry=registry)

    empty_registry = ProjectRegistry(tmp_path / "another-registry.json")
    service = ProjectService.load(str(result.project_dir), registry=empty_registry)
    assert service.project_dir == result.project_dir


def test_load_by_registered_name(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    result = ProjectService.init("demo", path=tmp_path / "demo", registry=registry)

    service = ProjectService.load("demo", registry=registry)
    assert service.project_dir == result.project_dir


def test_load_unknown_reference_raises(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    with pytest.raises(ProjectNotFoundError):
        ProjectService.load("does-not-exist", registry=registry)


def test_load_registered_but_deleted_project_raises(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    result = ProjectService.init("demo", path=tmp_path / "demo", registry=registry)
    result.config_path.unlink()

    with pytest.raises(ProjectNotFoundError):
        ProjectService.load("demo", registry=registry)


def test_link_registers_existing_project_with_its_slug(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    result = ProjectService.init("demo", path=tmp_path / "demo", registry=registry)

    other_registry = ProjectRegistry(tmp_path / "other-registry.json")
    linked = ProjectService.link(result.project_dir, registry=other_registry)
    assert linked.name == "demo"
    assert other_registry.resolve("demo") == result.project_dir


def test_link_without_config_raises(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    empty_dir = tmp_path / "not-a-project"
    empty_dir.mkdir()
    with pytest.raises(InvalidConfigError):
        ProjectService.link(empty_dir, registry=registry)


def test_link_conflict_raises(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    ProjectService.init("demo", path=tmp_path / "demo-a", registry=registry)
    other = ProjectService.init("other", path=tmp_path / "demo-b", registry=ProjectRegistry(tmp_path / "reg2.json"))

    with pytest.raises(RegistryConflictError):
        ProjectService.link(other.project_dir, name="demo", registry=registry)
