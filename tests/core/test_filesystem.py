from videodoc.core.storage.filesystem import PROJECT_SUBDIRS, ensure_project_structure, ensure_sources_yaml


def test_ensure_project_structure_creates_all_subdirs(tmp_path):
    project_dir = tmp_path / "demo"
    ensure_project_structure(project_dir)
    for sub in PROJECT_SUBDIRS:
        assert (project_dir / sub).is_dir()


def test_ensure_project_structure_is_idempotent_and_preserves_content(tmp_path):
    project_dir = tmp_path / "demo"
    ensure_project_structure(project_dir)
    marker = project_dir / "videos" / "keep-me.mp4"
    marker.write_text("fake video", encoding="utf-8")

    ensure_project_structure(project_dir)
    assert marker.read_text(encoding="utf-8") == "fake video"


def test_ensure_sources_yaml_creates_placeholder_once(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    path = ensure_sources_yaml(project_dir)
    assert path.exists()
    assert "scan" in path.read_text(encoding="utf-8")


def test_ensure_sources_yaml_does_not_overwrite_existing(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    path = project_dir / "sources.yaml"
    path.write_text("custom: content\n", encoding="utf-8")

    ensure_sources_yaml(project_dir)
    assert path.read_text(encoding="utf-8") == "custom: content\n"
