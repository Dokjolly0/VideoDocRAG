from videodoc.core.models.document_section import (
    GeneratedSectionCodeBlock,
    GeneratedSectionManifest,
    GeneratedSectionSource,
)


def test_generated_section_manifest_roundtrip(tmp_path):
    manifest = GeneratedSectionManifest(
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
                text_hash="abc",
            )
        ],
        code_blocks=[
            GeneratedSectionCodeBlock(
                id="demo_code_0001",
                video_id="demo",
                chunk_id="demo_chunk_0001",
                timestamp_seconds=20.0,
                language="yaml",
                confidence=0.94,
                verified=True,
            )
        ],
    )
    path = tmp_path / "manifest.json"

    manifest.save(path)
    loaded = GeneratedSectionManifest.load(path)

    assert loaded == manifest
