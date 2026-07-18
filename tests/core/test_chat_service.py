from videodoc.core.config import ProjectConfig
from videodoc.core.models.chat import ChatSessionSnapshot
from videodoc.core.models.document_section import GeneratedSectionManifest, GeneratedSectionSource
from videodoc.core.models.vector_index import VectorIndex, VectorIndexRecord
from videodoc.core.services.chat_service import ChatAnswerService, ChatFilters, DocumentationIndexService, parse_timecode
from videodoc.core.storage.database import ensure_schema, list_chat_messages
from videodoc.core.utils.embedding import embed_text_hashing, text_hash


def _config():
    return ProjectConfig.default(name="Demo", slug="demo")


def _seed_doc(project_dir):
    docs = project_dir / "docs"
    sources = docs / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    text = "# Configurazione database\n\nLa configurazione del database usa PostgreSQL nel file config.yaml."
    (docs / "01-configurazione-database.md").write_text(text, encoding="utf-8")
    GeneratedSectionManifest(
        section_index=1,
        section_title="Configurazione database",
        section_slug="configurazione-database",
        output_path="docs/01-configurazione-database.md",
        sources=[
            GeneratedSectionSource(
                rank=1,
                record_id="demo_chunk_0001_combined",
                video_id="demo",
                video_name="Demo.mp4",
                chunk_id="demo_chunk_0001",
                start_seconds=10.0,
                end_seconds=40.0,
                score=0.9,
                topic="Configurazione database",
                source_type="transcript",
                embedding_type="combined",
                text_hash=text_hash("La configurazione del database usa PostgreSQL."),
            )
        ],
        code_blocks=[],
    ).save(sources / "01-configurazione-database.sources.json")


def _seed_raw_index(project_dir, config):
    path = project_dir / config.paths.indexes / "vector_index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    good_text = "Nel video Demo configuriamo PostgreSQL nel file config.yaml."
    other_text = "Nel video Altro parliamo della dashboard."
    VectorIndex(
        backend="local-json",
        configured_vector_db="qdrant",
        distance="cosine",
        dimensions=32,
        inputs=[],
        records=[
            VectorIndexRecord(
                id="demo_chunk_0001_combined",
                vector=embed_text_hashing(good_text, dimensions=32),
                payload={
                    "video_id": "demo",
                    "video_name": "Demo.mp4",
                    "chunk_id": "demo_chunk_0001",
                    "source_type": "transcript",
                    "start_seconds": 10.0,
                    "end_seconds": 40.0,
                    "text": good_text,
                },
            ),
            VectorIndexRecord(
                id="altro_chunk_0001_combined",
                vector=embed_text_hashing(other_text, dimensions=32),
                payload={
                    "video_id": "altro",
                    "video_name": "Altro.mp4",
                    "chunk_id": "altro_chunk_0001",
                    "source_type": "transcript",
                    "start_seconds": 100.0,
                    "end_seconds": 140.0,
                    "text": other_text,
                },
            ),
        ],
    ).save(path)


def test_documentation_index_service_builds_generated_documentation_records(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_doc(project_dir)

    index = DocumentationIndexService(project_dir, config).build()

    assert len(index.records) == 1
    assert index.records[0].payload["source_type"] == "generated_documentation"
    assert index.records[0].payload["linked_video_names"] == ["Demo.mp4"]


def test_chat_docs_mode_answers_from_generated_docs(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_doc(project_dir)

    result = ChatAnswerService(project_dir, config).answer("Come si configura il database?", mode="docs")

    assert "PostgreSQL" in result.answer
    assert result.sources[0].source_type == "generated_documentation"
    assert result.sources[0].doc_path == "docs/01-configurazione-database.md"


def test_chat_raw_mode_applies_video_and_time_filters(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_raw_index(project_dir, config)

    result = ChatAnswerService(project_dir, config).answer(
        "PostgreSQL config.yaml",
        mode="raw",
        filters=ChatFilters(videos=("Demo.mp4",), start_seconds=0.0, end_seconds=50.0),
    )

    assert len(result.sources) == 1
    assert result.sources[0].video_name == "Demo.mp4"


def test_chat_turn_saves_session_to_db_and_json(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    ensure_schema(project_dir / config.paths.database)
    _seed_raw_index(project_dir, config)

    result = ChatAnswerService(project_dir, config).answer("PostgreSQL", mode="raw", save_session=True)

    assert result.session_id is not None
    assert len(list_chat_messages(project_dir / config.paths.database, result.session_id)) == 2
    snapshot = ChatSessionSnapshot.load(project_dir / "sessions" / f"{result.session_id}.json")
    assert snapshot.messages[0].role == "user"
    assert snapshot.messages[1].sources


def test_parse_timecode_accepts_hhmmss_and_mmss():
    assert parse_timecode("01:02:03") == 3723.0
    assert parse_timecode("02:03") == 123.0
