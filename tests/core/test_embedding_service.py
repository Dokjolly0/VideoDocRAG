import pytest

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DatabaseError, EmbeddingEngineNotSupportedError, NoVideosFoundError
from videodoc.core.models.chunk_manifest import ChunkCodeBlock, ChunkManifest, ChunkManifestEntry
from videodoc.core.models.embedding_manifest import EmbeddingManifest
from videodoc.core.services.embedding_service import EmbeddingService
from videodoc.core.storage.database import VideoRow, ensure_schema, upsert_video
from videodoc.core.storage.filesystem import ensure_video_workdir


def _config(**embedding_overrides):
    config = ProjectConfig.default(name="Demo", slug="demo")
    if embedding_overrides:
        config = config.model_copy(update={"embedding": config.embedding.model_copy(update=embedding_overrides)})
    return config


def _seed_video(project_dir, config, video_id="demo", filename="Demo.mp4", duration_seconds=120.0):
    db_path = project_dir / config.paths.database
    ensure_schema(db_path)
    video_path = project_dir / "videos" / filename
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"fake video")
    upsert_video(
        db_path,
        VideoRow(
            id=video_id,
            filename=filename,
            title=None,
            duration_seconds=duration_seconds,
            file_hash="hash123",
            path=video_path.resolve().as_posix(),
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )
    video_dir = project_dir / config.paths.workdir / video_id
    ensure_video_workdir(video_dir)
    return video_dir


def _chunk_manifest(video_id="demo", video_name="Demo.mp4", *, text="Introduciamo il progetto."):
    return ChunkManifest(
        video_id=video_id,
        video_name=video_name,
        chunks=[
            ChunkManifestEntry(
                id=f"{video_id}_chunk_0001",
                source_type="transcript_ocr_code",
                start_seconds=0.0,
                end_seconds=60.0,
                topic="Introduzione",
                summary="Si introduce il progetto.",
                transcript=text,
                ocr_text="npm run dev",
                code_blocks=[
                    ChunkCodeBlock(
                        id=f"{video_id}_code_0001",
                        language="bash",
                        code="npm run dev",
                        timestamp_seconds=20.0,
                        confidence=0.9,
                        verified=True,
                    )
                ],
                video_name=video_name,
                metadata={"source_type": "transcript_ocr_code", "contains_code": True},
            )
        ],
        min_duration_seconds=90,
        max_duration_seconds=480,
        include_nearby_frames=True,
    )


def _save_chunk_manifest(project_dir, config, manifest):
    path = project_dir / config.paths.workdir / manifest.video_id / "chunks" / f"{manifest.video_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest.save(path)
    return path


def test_no_project_db_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    with pytest.raises(NoVideosFoundError):
        EmbeddingService(project_dir, _config()).run()


def test_empty_project_db_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    ensure_schema(project_dir / "project.db")
    with pytest.raises(NoVideosFoundError):
        EmbeddingService(project_dir, _config()).run()


def test_project_db_as_directory_raises_database_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    (project_dir / "project.db").mkdir()
    with pytest.raises(DatabaseError):
        EmbeddingService(project_dir, _config()).run()


def test_unsupported_provider_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config(provider="openai")
    _seed_video(project_dir, config)
    with pytest.raises(EmbeddingEngineNotSupportedError):
        EmbeddingService(project_dir, config).run()


def test_video_without_chunks_is_skipped(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)

    result = EmbeddingService(project_dir, config).run()

    assert result.skipped == ("demo",)
    assert result.processed == ()
    assert result.errors == ()


def test_fresh_embedding_writes_manifest_with_all_embedding_types(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _save_chunk_manifest(project_dir, config, _chunk_manifest())

    result = EmbeddingService(project_dir, config).run()

    assert result.processed == ("demo",)
    assert result.errors == ()

    manifest = EmbeddingManifest.load(project_dir / "indexes" / "embeddings" / "demo.json")
    assert manifest.backend == "feature-hashing"
    assert manifest.provider == "local"
    assert manifest.model == "bge-m3"
    assert {record.embedding_type for record in manifest.records} == {"transcript", "ocr", "code", "summary", "combined"}
    assert all(record.dimensions == 256 for record in manifest.records)
    assert all(len(record.vector) == 256 for record in manifest.records)
    combined = next(record for record in manifest.records if record.embedding_type == "combined")
    assert combined.metadata["contains_code"] is True
    assert combined.metadata["language"] == "bash"


def test_rerun_with_matching_manifest_is_skipped(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _save_chunk_manifest(project_dir, config, _chunk_manifest())

    EmbeddingService(project_dir, config).run()
    result = EmbeddingService(project_dir, config).run()

    assert result.skipped == ("demo",)
    assert result.processed == ()


def test_chunk_change_triggers_reembedding(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _save_chunk_manifest(project_dir, config, _chunk_manifest(text="Prima versione"))

    EmbeddingService(project_dir, config).run()
    _save_chunk_manifest(project_dir, config, _chunk_manifest(text="Versione aggiornata"))
    result = EmbeddingService(project_dir, config).run()

    assert result.processed == ("demo",)
    manifest = EmbeddingManifest.load(project_dir / "indexes" / "embeddings" / "demo.json")
    assert any("Versione aggiornata" in record.text for record in manifest.records)


def test_corrupt_chunk_manifest_reports_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    video_dir = _seed_video(project_dir, config)
    chunks_path = video_dir / "chunks" / "demo.json"
    chunks_path.write_text("{not valid json", encoding="utf-8")

    result = EmbeddingService(project_dir, config).run()

    assert result.processed == ()
    assert result.skipped == ()
    assert len(result.errors) == 1
    assert "chunk manifest could not be read" in result.errors[0]


def test_corrupt_embedding_manifest_reports_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _save_chunk_manifest(project_dir, config, _chunk_manifest())
    manifest_path = project_dir / "indexes" / "embeddings" / "demo.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("{not valid json", encoding="utf-8")

    result = EmbeddingService(project_dir, config).run()

    assert result.processed == ()
    assert result.skipped == ()
    assert len(result.errors) == 1
    assert "embeddings already exist" in result.errors[0]


def test_empty_chunk_manifest_clears_stale_embeddings(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    manifest = _chunk_manifest()
    _save_chunk_manifest(project_dir, config, manifest)

    EmbeddingService(project_dir, config).run()
    manifest = manifest.model_copy(update={"chunks": []})
    _save_chunk_manifest(project_dir, config, manifest)

    result = EmbeddingService(project_dir, config).run()

    assert result.processed == ("demo",)
    updated = EmbeddingManifest.load(project_dir / "indexes" / "embeddings" / "demo.json")
    assert updated.records == []
    assert updated.chunk_inputs == []
