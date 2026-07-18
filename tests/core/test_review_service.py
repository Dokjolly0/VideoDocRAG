import pytest

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DocumentationReviewUnavailableError
from videodoc.core.models.document_review import DocumentationReviewReport
from videodoc.core.models.document_section import (
    GeneratedSectionCodeBlock,
    GeneratedSectionManifest,
    GeneratedSectionSource,
)
from videodoc.core.models.vector_index import VectorIndex, VectorIndexRecord
from videodoc.core.services.review_service import DocumentationReviewService
from videodoc.core.utils.embedding import embed_text_hashing, text_hash


def _config():
    return ProjectConfig.default(name="Demo", slug="demo")


def _seed_index(project_dir, config, text=None):
    source_text = text or "La configurazione del database usa PostgreSQL nel file config.yaml."
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
                vector=embed_text_hashing(source_text, dimensions=32),
                payload={"video_id": "demo", "video_name": "Demo.mp4", "chunk_id": "demo_chunk_0001", "text": source_text},
            )
        ],
    ).save(path)
    return source_text


def _seed_section(project_dir, *, markdown=None, code_verified=True, code_confidence=0.94):
    docs = project_dir / "docs"
    sources = docs / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    section = docs / "01-configurazione.md"
    section.write_text(markdown or _valid_markdown(), encoding="utf-8")
    source_text = "La configurazione del database usa PostgreSQL nel file config.yaml."
    GeneratedSectionManifest(
        section_index=1,
        section_title="Configurazione",
        section_slug="configurazione",
        output_path="docs/01-configurazione.md",
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
                text_hash=text_hash(source_text),
            )
        ],
        code_blocks=[
            GeneratedSectionCodeBlock(
                id="demo_code_0001",
                video_id="demo",
                chunk_id="demo_chunk_0001",
                timestamp_seconds=20.0,
                language="yaml",
                confidence=code_confidence,
                verified=code_verified,
            )
        ],
    ).save(sources / "01-configurazione.sources.json")
    return section


def _valid_markdown():
    return """# Configurazione

## Obiettivo

Descrivere la configurazione.

## Fonti utilizzate

- [1] `Demo.mp4` 00:00:10-00:00:40 - Configurazione database

## Spiegazione dettagliata

- La configurazione del database usa PostgreSQL nel file config.yaml. [1]

## Procedura passo-passo

1. La configurazione del database usa PostgreSQL nel file config.yaml. [1]

## Codice esaminato

```yaml
database_url: postgresql://localhost
```

## Spiegazione del codice

- `demo_code_0001`: blocco yaml recuperato da `demo` 00:00:20, confidenza OCR 0.94.

## Risultato atteso

Le fonti recuperate non isolano un risultato atteso separato; verificare questa voce in revisione.

## Errori comuni

Nessun errore specifico recuperato nelle fonti usate.

## Riferimenti

- [1] chunk `demo_chunk_0001`, record `demo_chunk_0001_combined`, `Demo.mp4` 00:00:10-00:00:40 - Configurazione database
"""


def test_review_valid_generated_section_writes_reports(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_index(project_dir, config)
    _seed_section(project_dir)

    result = DocumentationReviewService(project_dir, config).run()

    assert result.sections == 1
    assert result.errors == 0
    assert (project_dir / "docs" / "review_report.md").is_file()
    report = DocumentationReviewReport.load(project_dir / "docs" / "review_report.json")
    assert report.sections[0].issue_count == 0
    assert report.code_blocks[0].classification == "verified"


def test_missing_source_manifest_is_reported_as_issue(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_index(project_dir, config)
    docs = project_dir / "docs"
    docs.mkdir()
    (docs / "01-configurazione.md").write_text(_valid_markdown(), encoding="utf-8")

    result = DocumentationReviewService(project_dir, config).run()

    assert result.errors == 1
    report = DocumentationReviewReport.load(project_dir / "docs" / "review_report.json")
    assert report.issues[0].check == "sources"


def test_uncited_claim_is_flagged(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_index(project_dir, config)
    markdown = _valid_markdown().replace(
        "- La configurazione del database usa PostgreSQL nel file config.yaml. [1]",
        "- Kubernetes viene configurato automaticamente senza ulteriori passaggi.",
    )
    _seed_section(project_dir, markdown=markdown)

    result = DocumentationReviewService(project_dir, config).run()

    assert result.warnings >= 1
    report = DocumentationReviewReport.load(project_dir / "docs" / "review_report.json")
    assert any(issue.check == "anti_hallucination" for issue in report.issues)


def test_low_confidence_code_is_marked_needs_review(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_index(project_dir, config)
    _seed_section(project_dir, code_verified=False, code_confidence=0.61)

    result = DocumentationReviewService(project_dir, config).run()

    assert result.warnings >= 1
    report = DocumentationReviewReport.load(project_dir / "docs" / "review_report.json")
    assert report.code_blocks[0].classification == "needs_review"


def test_no_generated_sections_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()

    with pytest.raises(DocumentationReviewUnavailableError, match="videodoc generate"):
        DocumentationReviewService(project_dir, _config()).run()
