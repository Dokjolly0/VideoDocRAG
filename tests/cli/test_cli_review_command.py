from typer.testing import CliRunner

from videodoc.cli.app import app
from videodoc.core.config import ProjectConfig
from videodoc.core.models.document_section import GeneratedSectionManifest, GeneratedSectionSource
from videodoc.core.models.vector_index import VectorIndex, VectorIndexRecord
from videodoc.core.utils.embedding import embed_text_hashing, text_hash

runner = CliRunner()


def _init_project(tmp_path, name="demo"):
    custom = tmp_path / name
    result = runner.invoke(app, ["init", name, "--path", str(custom)])
    assert result.exit_code == 0
    return custom


def _seed_reviewable_section(project_dir):
    config = ProjectConfig.load(project_dir / "config.yaml")
    source_text = "Introduciamo il progetto e la configurazione iniziale."
    index_path = project_dir / config.paths.indexes / "vector_index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    VectorIndex(
        backend="local-json",
        configured_vector_db="qdrant",
        distance="cosine",
        dimensions=32,
        inputs=[],
        records=[
            VectorIndexRecord(
                id="demo_chunk_0001_combined",
                vector=embed_text_hashing(source_text, dimensions=32),
                payload={"video_id": "demo", "video_name": "Demo.mp4", "chunk_id": "demo_chunk_0001", "text": source_text},
            )
        ],
    ).save(index_path)
    docs = project_dir / "docs"
    sources = docs / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    (docs / "01-introduzione.md").write_text(
        "# Introduzione\n\n"
        "## Obiettivo\n\nPresentare il progetto.\n\n"
        "## Fonti utilizzate\n\n- [1] `Demo.mp4` 00:00:00-00:01:00 - Introduzione\n\n"
        "## Spiegazione dettagliata\n\n- Introduciamo il progetto e la configurazione iniziale. [1]\n\n"
        "## Procedura passo-passo\n\n1. Introduciamo il progetto e la configurazione iniziale. [1]\n\n"
        "## Codice esaminato\n\nNessun blocco codice collegato alle fonti recuperate.\n\n"
        "## Spiegazione del codice\n\nNessun codice da spiegare in questa sezione.\n\n"
        "## Risultato atteso\n\nLe fonti recuperate non isolano un risultato atteso separato; verificare questa voce in revisione.\n\n"
        "## Errori comuni\n\nNessun errore specifico recuperato nelle fonti usate.\n\n"
        "## Riferimenti\n\n- [1] chunk `demo_chunk_0001`, record `demo_chunk_0001_combined`, `Demo.mp4` 00:00:00-00:01:00 - Introduzione\n",
        encoding="utf-8",
    )
    GeneratedSectionManifest(
        section_index=1,
        section_title="Introduzione",
        section_slug="introduzione",
        output_path="docs/01-introduzione.md",
        sources=[
            GeneratedSectionSource(
                rank=1,
                record_id="demo_chunk_0001_combined",
                video_id="demo",
                video_name="Demo.mp4",
                chunk_id="demo_chunk_0001",
                start_seconds=0.0,
                end_seconds=60.0,
                score=0.9,
                topic="Introduzione",
                source_type="transcript",
                embedding_type="combined",
                text_hash=text_hash(source_text),
            )
        ],
        code_blocks=[],
    ).save(sources / "01-introduzione.sources.json")


def test_review_success_prints_summary_and_writes_report(tmp_path):
    custom = _init_project(tmp_path)
    _seed_reviewable_section(custom)

    result = runner.invoke(app, ["review", "demo"])

    assert result.exit_code == 0
    assert "Sections" in result.stdout
    assert "Issues" in result.stdout
    assert (custom / "docs" / "review_report.md").is_file()
    assert (custom / "docs" / "review_report.json").is_file()


def test_review_missing_generated_sections_fails_with_hint(tmp_path):
    _init_project(tmp_path)

    result = runner.invoke(app, ["review", "demo"])

    assert result.exit_code == 1
    assert "videodoc generate" in result.output
