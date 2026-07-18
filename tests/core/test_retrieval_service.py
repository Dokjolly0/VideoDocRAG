import pytest

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import InvalidVectorIndexError, VectorIndexUnavailableError
from videodoc.core.models.vector_index import VectorIndex, VectorIndexRecord
from videodoc.core.services.retrieval_service import RetrievalService
from videodoc.core.utils.embedding import embed_text_hashing


def _config(**retrieval_overrides):
    config = ProjectConfig.default(name="Demo", slug="demo")
    if retrieval_overrides:
        config = config.model_copy(update={"retrieval": config.retrieval.model_copy(update=retrieval_overrides)})
    return config


def _record(record_id, text, *, dimensions=32, video_name="Demo.mp4", chunk_id=None, start=0.0, end=60.0):
    return VectorIndexRecord(
        id=record_id,
        vector=embed_text_hashing(text, dimensions=dimensions),
        payload={
            "project_id": "demo",
            "video_id": "demo",
            "video_name": video_name,
            "chunk_id": chunk_id or record_id.removesuffix("_combined"),
            "embedding_type": "combined",
            "source_type": "transcript",
            "start_seconds": start,
            "end_seconds": end,
            "topic": "Database",
            "text": text,
        },
    )


def _save_index(project_dir, config, records, *, dimensions=32, backend="local-json", distance="cosine"):
    path = project_dir / config.paths.indexes / "vector_index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    VectorIndex(
        backend=backend,
        configured_vector_db="qdrant",
        distance=distance,
        dimensions=dimensions,
        inputs=[],
        records=records,
    ).save(path)


def test_ask_retrieves_ranked_sources_and_builds_grounded_answer(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config(top_k=1)
    database_text = "La configurazione del database usa PostgreSQL e si imposta nel file config.yaml."
    _save_index(
        project_dir,
        config,
        [
            _record("demo_chunk_0001_combined", database_text),
            _record("demo_chunk_0002_combined", "La schermata principale mostra la dashboard utente.", start=70.0, end=120.0),
        ],
    )

    result = RetrievalService(project_dir, config).ask("Come si configura il database?")

    assert len(result.sources) == 1
    assert result.sources[0].chunk_id == "demo_chunk_0001"
    assert result.sources[0].video_name == "Demo.mp4"
    assert "PostgreSQL" in result.answer
    assert "[1]" in result.answer


def test_retrieve_deduplicates_multiple_embedding_records_for_same_chunk(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config(top_k=5)
    text = "Il comando npm run dev avvia il server locale."
    _save_index(
        project_dir,
        config,
        [
            _record("demo_chunk_0001_transcript", text, chunk_id="demo_chunk_0001"),
            _record("demo_chunk_0001_combined", text, chunk_id="demo_chunk_0001"),
        ],
    )

    sources = RetrievalService(project_dir, config).retrieve("npm run dev")

    assert len(sources) == 1
    assert sources[0].chunk_id == "demo_chunk_0001"


def test_missing_index_raises_actionable_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()

    with pytest.raises(VectorIndexUnavailableError, match="videodoc index"):
        RetrievalService(project_dir, _config()).ask("database")


def test_no_positive_sources_returns_no_source_answer(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _save_index(
        project_dir,
        config,
        [
            VectorIndexRecord(
                id="zero",
                vector=[0.0, 0.0],
                payload={"video_id": "demo", "chunk_id": "zero", "text": "Testo non indicizzato."},
            )
        ],
        dimensions=2,
    )

    result = RetrievalService(project_dir, config).ask("database")

    assert result.sources == ()
    assert "Non ho trovato" in result.answer


def test_incompatible_record_dimensions_raise_invalid_index(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _save_index(
        project_dir,
        config,
        [VectorIndexRecord(id="bad", vector=[1.0], payload={"video_id": "demo", "text": "database"})],
        dimensions=2,
    )

    with pytest.raises(InvalidVectorIndexError, match="incompatible"):
        RetrievalService(project_dir, config).retrieve("database")
