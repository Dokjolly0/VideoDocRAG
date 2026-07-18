from videodoc.core.config import ProjectConfig
from videodoc.core.models.codebase_manifest import CodebaseSyncManifest
from videodoc.core.models.vector_index import VectorIndex
from videodoc.core.services.chat_service import ChatAnswerService
from videodoc.core.services.codebase_sync_service import CodebaseSyncService


def _config():
    return ProjectConfig.default(name="Demo", slug="demo")


def test_sync_codebase_writes_manifest_and_index(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    codebase = project_dir / "codebase"
    (codebase / "src").mkdir(parents=True)
    (codebase / "src" / "app.py").write_text(
        "def create_app():\n"
        "    return 'ok'\n",
        encoding="utf-8",
    )
    (codebase / "node_modules" / "pkg").mkdir(parents=True)
    (codebase / "node_modules" / "pkg" / "index.js").write_text("ignored", encoding="utf-8")

    result = CodebaseSyncService(project_dir, config).run()

    assert result.synced is True
    assert result.files == 1
    assert result.snippets == 1
    manifest = CodebaseSyncManifest.load(project_dir / "indexes" / "codebase_manifest.json")
    assert manifest.files[0].path == "src/app.py"
    assert manifest.snippets[0].symbol_name == "create_app"
    assert manifest.snippets[0].metadata["link"] == "codebase/src/app.py#L1-L2"
    index = VectorIndex.load(project_dir / "indexes" / "codebase_index.json")
    assert index.records[0].payload["source_type"] == "codebase"
    assert index.records[0].payload["doc_path"] == "codebase/src/app.py#L1-L2"


def test_sync_codebase_is_idempotent_until_file_changes(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    path = project_dir / "codebase" / "app.py"
    path.parent.mkdir()
    path.write_text("def first():\n    return 1\n", encoding="utf-8")

    first = CodebaseSyncService(project_dir, config).run()
    second = CodebaseSyncService(project_dir, config).run()
    path.write_text("def first():\n    return 2\n", encoding="utf-8")
    third = CodebaseSyncService(project_dir, config).run()

    assert first.synced is True
    assert second.skipped is True
    assert third.modified == 1
    assert third.synced is True


def test_sync_codebase_records_removed_files(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    path = project_dir / "codebase" / "app.py"
    path.parent.mkdir()
    path.write_text("def first():\n    return 1\n", encoding="utf-8")
    CodebaseSyncService(project_dir, config).run()

    path.unlink()
    result = CodebaseSyncService(project_dir, config).run()

    assert result.removed == 1
    assert result.files == 0
    assert VectorIndex.load(project_dir / "indexes" / "codebase_index.json").records == []


def test_sync_codebase_without_codebase_is_noop(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()

    result = CodebaseSyncService(project_dir, _config()).run()

    assert result.skipped is True
    assert result.files == 0
    assert result.manifest_path.exists() is False


def test_chat_raw_mode_searches_synced_codebase(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    path = project_dir / "codebase" / "src" / "app.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "def create_app():\n"
        "    database_url = 'postgresql://localhost'\n"
        "    return database_url\n",
        encoding="utf-8",
    )
    CodebaseSyncService(project_dir, config).run()

    result = ChatAnswerService(project_dir, config).answer("create_app database_url", mode="raw")

    assert result.sources[0].source_type == "codebase"
    assert result.sources[0].doc_path == "codebase/src/app.py#L1-L3"
    assert "database_url" in result.answer
