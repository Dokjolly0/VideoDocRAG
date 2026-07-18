import pytest

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DatabaseError, NoVideosFoundError, VectorIndexNotSupportedError
from videodoc.core.models.embedding_manifest import EmbeddingChunkSignature, EmbeddingManifest, EmbeddingRecord
from videodoc.core.models.vector_index import VectorIndex
from videodoc.core.services.index_service import IndexService
from videodoc.core.storage.database import VideoRow, ensure_schema, upsert_video


def _config(**retrieval_overrides):
    config = ProjectConfig.default(name="Demo", slug="demo")
    if retrieval_overrides:
        config = config.model_copy(update={"retrieval": config.retrieval.model_copy(update=retrieval_overrides)})
    return config


def _seed_video(project_dir, config, video_id="demo", filename="Demo.mp4"):
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
            duration_seconds=120.0,
            file_hash="hash123",
            path=video_path.resolve().as_posix(),
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )


def _embedding_manifest(video_id="demo", video_name="Demo.mp4", *, text="Introduzione"):
    return EmbeddingManifest(
        video_id=video_id,
        video_name=video_name,
        backend="feature-hashing",
        provider="local",
        model="bge-m3",
        dimensions=2,
        batch_size=32,
        chunk_inputs=[
            EmbeddingChunkSignature(
                id=f"{video_id}_chunk_0001",
                source_type="transcript",
                start_seconds=0.0,
                end_seconds=60.0,
                topic_hash="topic",
                summary_hash="summary",
                transcript_hash="transcript",
                ocr_hash="ocr",
                code_hash="code",
                metadata_hash="metadata",
            )
        ],
        records=[
            EmbeddingRecord(
                id=f"{video_id}_chunk_0001_combined",
                chunk_id=f"{video_id}_chunk_0001",
                embedding_type="combined",
                text=text,
                text_hash=f"hash-{text}",
                vector=[1.0, 0.0],
                dimensions=2,
                metadata={
                    "source_type": "transcript",
                    "start_seconds": 0.0,
                    "end_seconds": 60.0,
                    "topic": "Introduzione",
                },
            )
        ],
    )


def _save_embedding_manifest(project_dir, config, manifest):
    path = project_dir / config.paths.indexes / "embeddings" / f"{manifest.video_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest.save(path)
    return path


def test_no_project_db_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    with pytest.raises(NoVideosFoundError):
        IndexService(project_dir, _config()).run()


def test_empty_project_db_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    ensure_schema(project_dir / "project.db")
    with pytest.raises(NoVideosFoundError):
        IndexService(project_dir, _config()).run()


def test_project_db_as_directory_raises_database_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    (project_dir / "project.db").mkdir()
    with pytest.raises(DatabaseError):
        IndexService(project_dir, _config()).run()


def test_unsupported_vector_db_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config(vector_db="pinecone")
    _seed_video(project_dir, config)
    with pytest.raises(VectorIndexNotSupportedError):
        IndexService(project_dir, config).run()


def test_no_embedding_manifests_is_skipped(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)

    result = IndexService(project_dir, config).run()

    assert result.skipped is True
    assert result.indexed is False
    assert result.records == 0


def test_fresh_index_writes_vector_index(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _save_embedding_manifest(project_dir, config, _embedding_manifest())

    result = IndexService(project_dir, config).run()

    assert result.indexed is True
    assert result.records == 1
    index = VectorIndex.load(project_dir / "indexes" / "vector_index.json")
    assert index.backend == "local-json"
    assert index.configured_vector_db == "qdrant"
    assert index.records[0].payload["project_id"] == "demo"
    assert index.records[0].payload["video_id"] == "demo"
    assert index.records[0].payload["text"] == "Introduzione"


def test_rerun_with_matching_inputs_is_skipped(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _save_embedding_manifest(project_dir, config, _embedding_manifest())

    IndexService(project_dir, config).run()
    result = IndexService(project_dir, config).run()

    assert result.skipped is True
    assert result.indexed is False
    assert result.records == 1


def test_embedding_change_triggers_reindex(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _save_embedding_manifest(project_dir, config, _embedding_manifest(text="Prima"))

    IndexService(project_dir, config).run()
    _save_embedding_manifest(project_dir, config, _embedding_manifest(text="Dopo"))
    result = IndexService(project_dir, config).run()

    assert result.indexed is True
    index = VectorIndex.load(project_dir / "indexes" / "vector_index.json")
    assert index.records[0].payload["text"] == "Dopo"


def test_corrupt_embedding_manifest_reports_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    path = project_dir / "indexes" / "embeddings" / "demo.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not valid json", encoding="utf-8")

    result = IndexService(project_dir, config).run()

    assert result.skipped is True
    assert len(result.errors) == 1
    assert "embedding manifest could not be read" in result.errors[0]


def test_corrupt_existing_index_is_rewritten_with_warning(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _save_embedding_manifest(project_dir, config, _embedding_manifest())
    index_path = project_dir / "indexes" / "vector_index.json"
    index_path.write_text("{not valid json", encoding="utf-8")

    result = IndexService(project_dir, config).run()

    assert result.indexed is True
    assert len(result.errors) == 1
    assert "vector index already exists" in result.errors[0]
    assert VectorIndex.load(index_path).records[0].payload["text"] == "Introduzione"
