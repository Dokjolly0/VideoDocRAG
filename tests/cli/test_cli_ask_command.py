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


def _seed_index(project_dir):
    config = ProjectConfig.load(project_dir / "config.yaml")
    text = "La configurazione del database usa PostgreSQL e variabili nel file config.yaml."
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
                    "project_id": "demo",
                    "video_id": "demo",
                    "video_name": "Demo.mp4",
                    "chunk_id": "demo_chunk_0001",
                    "embedding_type": "combined",
                    "source_type": "transcript",
                    "start_seconds": 10.0,
                    "end_seconds": 40.0,
                    "topic": "Database",
                    "text": text,
                },
            )
        ],
    ).save(path)


def test_ask_success_prints_answer_and_sources(tmp_path):
    custom = _init_project(tmp_path)
    _seed_index(custom)

    result = runner.invoke(app, ["ask", "demo", "Come si configura il database?", "--top-k", "1"])

    assert result.exit_code == 0
    assert "Project: demo" in result.stdout
    assert "PostgreSQL" in result.stdout
    assert "Sources" in result.stdout
    assert "00:00:10-00:00:40" in result.stdout


def test_ask_unknown_project_fails():
    result = runner.invoke(app, ["ask", "does-not-exist", "Domanda?"])
    assert result.exit_code == 1


def test_ask_missing_index_fails_with_hint(tmp_path):
    _init_project(tmp_path)

    result = runner.invoke(app, ["ask", "demo", "Domanda?"])

    assert result.exit_code == 1
    assert "videodoc index" in result.output
