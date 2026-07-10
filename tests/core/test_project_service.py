from pathlib import Path

import pytest

import videodoc.core.services.project_service as project_service_module
from videodoc.core.config import ProjectConfig
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
    # The registry key is always the slug, never the raw display name.
    assert result.name == "demo-course"
    assert registry.resolve("demo-course") == result.project_dir
    assert registry.resolve("Demo Course") is None


def test_init_registers_by_slug_not_display_name(tmp_path):
    """Regression test: 'init' and 'link' must agree on the canonical
    registry key (the slug), otherwise the same project ends up reachable
    under different identifiers depending on how it was created."""
    registry = ProjectRegistry(tmp_path / "registry.json")
    result = ProjectService.init("Corso Software X", path=tmp_path / "corso", registry=registry)
    assert result.name == "corso-software-x"

    other_registry = ProjectRegistry(tmp_path / "other-registry.json")
    linked = ProjectService.link(result.project_dir, registry=other_registry)
    assert linked.name == result.name == "corso-software-x"


def test_init_on_path_with_different_existing_project_raises(tmp_path):
    """Regression test: re-running 'init' with a different name on a path
    that already holds someone else's project must fail loudly instead of
    silently aliasing that project under the new name."""
    registry = ProjectRegistry(tmp_path / "registry.json")
    shared_dir = tmp_path / "shared"
    ProjectService.init("Original Project", path=shared_dir, registry=registry)

    with pytest.raises(RegistryConflictError):
        ProjectService.init("Different Project", path=shared_dir, registry=registry)

    # The original project's config.yaml must be untouched, and no alias
    # for 'different-project' should have been registered.
    assert registry.resolve("different-project") is None
    assert registry.resolve("original-project") == shared_dir.resolve()


def test_init_with_explicit_path_uses_it_directly(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    target = tmp_path / "somewhere-else"
    result = ProjectService.init("demo", path=target, registry=registry)
    assert result.project_dir == target.resolve()


def test_init_with_videos_option_sets_external_path_on_new_project(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    external = tmp_path / "external-videos"
    result = ProjectService.init("demo", path=tmp_path / "demo", videos=str(external), registry=registry)

    config = ProjectConfig.load(result.config_path)
    assert config.paths.videos == str(external)
    assert result.ignored_source_overrides == ()


def test_init_rerun_ignores_videos_option_and_flags_it(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    project_dir = tmp_path / "demo"
    ProjectService.init("demo", path=project_dir, registry=registry)

    before = ProjectConfig.load(project_dir / "config.yaml")

    result = ProjectService.init("demo", path=project_dir, videos=str(tmp_path / "external"), registry=registry)

    after = ProjectConfig.load(project_dir / "config.yaml")
    assert after == before
    assert result.ignored_source_overrides == ("videos",)


def test_init_rerun_with_multiple_ignored_overrides(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    project_dir = tmp_path / "demo"
    ProjectService.init("demo", path=project_dir, registry=registry)

    result = ProjectService.init(
        "demo", path=project_dir, registry=registry,
        videos=str(tmp_path / "v"), attachments=str(tmp_path / "a"), codebase=str(tmp_path / "c"),
    )
    assert set(result.ignored_source_overrides) == {"videos", "attachments", "codebase"}


def test_init_invalid_videos_option_raises_invalid_config_error(tmp_path):
    # "../outside" (parent-traversal) is invalid on every supported OS,
    # unlike a Windows-specific ambiguous form like "C:foo" which POSIX
    # accepts as a harmless relative filename -- see core/utils/paths.py.
    registry = ProjectRegistry(tmp_path / "registry.json")
    with pytest.raises(InvalidConfigError):
        ProjectService.init("demo", path=tmp_path / "demo", videos="../outside", registry=registry)


def test_init_invalid_videos_option_creates_nothing_on_disk(tmp_path):
    """Regression test: config validation must happen before any folder or
    file is created, so a bad --videos/--attachments/--codebase never leaves
    partial project state behind."""
    registry = ProjectRegistry(tmp_path / "registry.json")
    target = tmp_path / "demo"
    with pytest.raises(InvalidConfigError):
        ProjectService.init("demo", path=target, videos="../outside", registry=registry)
    assert not target.exists()
    assert registry.resolve("demo") is None


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
    assert linked.canonical_slug == "demo"
    assert other_registry.resolve("demo") == result.project_dir


def test_link_with_explicit_alias_is_slugified_and_flagged(tmp_path):
    """--name is a deliberate local alias, distinct from the project's own
    canonical slug -- but it must still be normalized to a slug like every
    other registry key, and the divergence must be visible via canonical_slug."""
    registry = ProjectRegistry(tmp_path / "registry.json")
    result = ProjectService.init("Corso Software X", path=tmp_path / "corso", registry=registry)

    other_registry = ProjectRegistry(tmp_path / "other-registry.json")
    linked = ProjectService.link(result.project_dir, name="Alias Locale!!", registry=other_registry)

    assert linked.name == "alias-locale"
    assert linked.canonical_slug == "corso-software-x"
    assert other_registry.resolve("alias-locale") == result.project_dir
    # link() never rewrites the project's own config.yaml.
    assert linked.canonical_slug != linked.name


def test_link_with_invalid_alias_raises_domain_error(tmp_path):
    registry = ProjectRegistry(tmp_path / "registry.json")
    result = ProjectService.init("demo", path=tmp_path / "demo", registry=registry)

    with pytest.raises(InvalidProjectNameError):
        ProjectService.link(result.project_dir, name="!!!", registry=ProjectRegistry(tmp_path / "reg2.json"))


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
