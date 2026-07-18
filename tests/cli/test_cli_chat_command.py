from typer.testing import CliRunner

from videodoc.cli.app import app
from videodoc.core.config import ProjectConfig
from videodoc.core.models.vector_index import VectorIndex, VectorIndexRecord
from videodoc.core.utils.embedding import embed_text_hashing

runner = CliRunner()


def _init_project(tmp_path, name="demo"):
    custom = tmp_path / name
    result = runner.invoke(app, ["init", name, "--path", str(custom)])
    assert result.exit_code == 0
    return custom


def _seed_raw_index(project_dir):
    config = ProjectConfig.load(project_dir / "config.yaml")
    text = "La configurazione usa PostgreSQL nel file config.yaml."
    path = project_dir / config.paths.indexes / "vector_index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    VectorIndex(
        backend="local-json",
        configured_vector_db="qdrant",
        distance="cosine",
        dimensions=32,
        inputs=[],
        records=[
            VectorIndexRecord(
                id="demo_chunk_0001_combined",
                vector=embed_text_hashing(text, dimensions=32),
                payload={
                    "video_id": "demo",
                    "video_name": "Demo.mp4",
                    "chunk_id": "demo_chunk_0001",
                    "source_type": "transcript",
                    "start_seconds": 0.0,
                    "end_seconds": 60.0,
                    "text": text,
                },
            )
        ],
    ).save(path)


def test_chat_message_saves_session_and_prints_sources(tmp_path):
    custom = _init_project(tmp_path)
    _seed_raw_index(custom)

    result = runner.invoke(app, ["chat", "demo", "--message", "PostgreSQL config.yaml", "--source", "raw"])

    assert result.exit_code == 0
    assert "Session:" in result.stdout
    assert "PostgreSQL" in result.stdout
    assert list((custom / "sessions").glob("chat_*.json"))


def test_chat_invalid_time_filter_fails(tmp_path):
    custom = _init_project(tmp_path)
    _seed_raw_index(custom)

    result = runner.invoke(app, ["chat", "demo", "--message", "x", "--from", "bad"])

    assert result.exit_code == 1
    assert "Invalid timecode" in result.output
