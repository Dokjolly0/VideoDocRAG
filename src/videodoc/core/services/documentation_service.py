from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DatabaseError, DocumentationOutlineUnavailableError, NoVideosFoundError
from videodoc.core.models.document_section import (
    GeneratedSectionCodeBlock,
    GeneratedSectionManifest,
    GeneratedSectionSource,
)
from videodoc.core.services.retrieval_service import RetrievalService, RetrievedSource
from videodoc.core.storage.database import CodeBlockRow, ensure_schema, list_code_blocks, list_videos
from videodoc.core.utils.embedding import text_hash
from videodoc.core.utils.slug import slugify

_HEADING_RE = re.compile(r"^##\s+(?:(?P<index>\d+)\.\s+)?(?P<title>.+?)\s*$")
_ERROR_WORDS = ("errore", "error", "warning", "exception", "traceback", "fallisce", "problema")
_MAX_SECTION_SOURCES = 6
_MAX_CODE_BLOCKS = 5


@dataclass(frozen=True)
class GeneratedSection:
    title: str
    output_path: Path
    source_manifest_path: Path
    sources: int
    code_blocks: int


@dataclass(frozen=True)
class DocumentationGenerationResult:
    generated: tuple[GeneratedSection, ...]
    skipped: tuple[Path, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _OutlineSection:
    index: int
    title: str
    body: str


class DocumentationService:
    def __init__(self, project_dir: Path, config: ProjectConfig) -> None:
        self.project_dir = project_dir
        self.config = config
        self.output_dir = self.project_dir / config.paths.output
        self.outline_path = self.output_dir / "outline.md"
        self.sources_dir = self.output_dir / "sources"

    def run(self, *, force: bool = False, top_k: int | None = None) -> DocumentationGenerationResult:
        outline_sections = self._load_outline()
        db_path = self.project_dir / self.config.paths.database
        if not db_path.exists():
            raise NoVideosFoundError(
                f"No videos registered in {db_path.name} -- run 'videodoc ingest' first."
            )
        if not db_path.is_file():
            raise DatabaseError(f"{db_path} exists but is not a file.")

        ensure_schema(db_path)
        videos = list_videos(db_path)
        if not videos:
            raise NoVideosFoundError(
                f"No videos registered in {db_path.name} -- run 'videodoc ingest' first."
            )

        retriever = RetrievalService(self.project_dir, self.config)
        generated: list[GeneratedSection] = []
        skipped: list[Path] = []
        warnings: list[str] = []

        for section in outline_sections:
            section_slug = _section_slug(section)
            output_path = self.output_dir / f"{section.index:02d}-{section_slug}.md"
            manifest_path = self.sources_dir / f"{section.index:02d}-{section_slug}.sources.json"
            if output_path.is_file() and not force:
                skipped.append(output_path)
                continue

            sources = retriever.retrieve(_section_query(section), top_k=top_k)[:_MAX_SECTION_SOURCES]
            if not sources:
                warnings.append(f"{section.title}: no indexed sources retrieved; generated a review placeholder.")
            code_blocks = _code_blocks_for_sources(db_path, sources)
            markdown = _render_section_markdown(section, sources, code_blocks)
            manifest = _section_manifest(section, section_slug, output_path, sources, code_blocks, self.project_dir)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            self.sources_dir.mkdir(parents=True, exist_ok=True)
            _write_atomic(output_path, markdown)
            _write_atomic(manifest_path, manifest.to_json() + "\n")
            generated.append(
                GeneratedSection(
                    title=section.title,
                    output_path=output_path,
                    source_manifest_path=manifest_path,
                    sources=len(sources),
                    code_blocks=len(code_blocks),
                )
            )

        return DocumentationGenerationResult(tuple(generated), tuple(skipped), tuple(warnings))

    def _load_outline(self) -> list[_OutlineSection]:
        if not self.outline_path.is_file():
            raise DocumentationOutlineUnavailableError(
                f"No documentation outline found at {self.outline_path} -- run 'videodoc outline' first."
            )
        try:
            text = self.outline_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DocumentationOutlineUnavailableError(f"Cannot read documentation outline at {self.outline_path}: {exc}") from exc
        sections = _parse_outline(text)
        if not sections:
            raise DocumentationOutlineUnavailableError(
                f"No sections found in {self.outline_path} -- run 'videodoc outline --force' or edit the outline."
            )
        return sections


def _parse_outline(text: str) -> list[_OutlineSection]:
    sections: list[_OutlineSection] = []
    current_index = 0
    current_title: str | None = None
    current_body: list[str] = []

    def flush() -> None:
        nonlocal current_index, current_title, current_body
        if current_title is None:
            return
        index = current_index or len(sections) + 1
        sections.append(_OutlineSection(index=index, title=current_title, body="\n".join(current_body).strip()))

    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            flush()
            current_title = match.group("title").strip()
            current_index = int(match.group("index")) if match.group("index") else 0
            current_body = []
        elif current_title is not None:
            current_body.append(line)
    flush()
    return sections


def _section_slug(section: _OutlineSection) -> str:
    try:
        return slugify(section.title)
    except ValueError:
        return f"section-{section.index:02d}"


def _section_query(section: _OutlineSection) -> str:
    return "\n".join(part for part in [section.title, section.body] if part.strip())


def _render_section_markdown(
    section: _OutlineSection,
    sources: tuple[RetrievedSource, ...],
    code_blocks: list[CodeBlockRow],
) -> str:
    lines = [
        f"# {section.title}",
        "",
        "## Obiettivo",
        "",
        _objective_from_outline(section),
        "",
        "## Fonti utilizzate",
        "",
    ]
    if sources:
        for source in sources:
            lines.append(f"- [{source.rank}] {_source_label(source)}")
    else:
        lines.append("- Nessuna fonte indicizzata recuperata per questa sezione.")

    lines.extend(["", "## Spiegazione dettagliata", ""])
    if sources:
        for source in sources:
            lines.append(f"- {_excerpt(source.text, max_chars=360)} [{source.rank}]")
    else:
        lines.append("Da completare dopo aver aggiunto fonti indicizzate pertinenti.")

    lines.extend(["", "## Procedura passo-passo", ""])
    procedure_steps = _procedure_steps(sources)
    if procedure_steps:
        for index, step in enumerate(procedure_steps, start=1):
            lines.append(f"{index}. {step}")
    else:
        lines.append("Le fonti recuperate non contengono una procedura esplicita da trasformare in passi.")

    lines.extend(["", "## Codice esaminato", ""])
    if code_blocks:
        for block in code_blocks:
            language = block.language or ""
            lines.append(f"Fonte codice: {block.video_id} {_optional_timestamp(block.timestamp_seconds)}".rstrip())
            if not block.verified or (block.confidence is not None and block.confidence < 0.80):
                lines.append("> Revisione richiesta: blocco codice da OCR non completamente verificato.")
            lines.append(f"```{language}")
            lines.append(block.code.rstrip())
            lines.append("```")
            lines.append("")
    else:
        lines.append("Nessun blocco codice collegato alle fonti recuperate.")

    lines.extend(["## Spiegazione del codice", ""])
    if code_blocks:
        for block in code_blocks:
            language = block.language or "testo"
            confidence = f", confidenza OCR {block.confidence:.2f}" if block.confidence is not None else ""
            lines.append(
                f"- `{block.id}`: blocco {language} recuperato da `{block.video_id}`"
                f"{_optional_timestamp(block.timestamp_seconds)}{confidence}."
            )
    else:
        lines.append("Nessun codice da spiegare in questa sezione.")

    lines.extend(["", "## Risultato atteso", ""])
    lines.append("Le fonti recuperate non isolano un risultato atteso separato; verificare questa voce in revisione.")

    lines.extend(["", "## Errori comuni", ""])
    errors = _error_sources(sources)
    if errors:
        for source in errors:
            lines.append(f"- {_excerpt(source.text, max_chars=220)} [{source.rank}]")
    else:
        lines.append("Nessun errore specifico recuperato nelle fonti usate.")

    lines.extend(["", "## Riferimenti", ""])
    if sources:
        for source in sources:
            lines.append(f"- [{source.rank}] chunk `{source.chunk_id}`, record `{source.record_id}`, {_source_label(source)}")
    else:
        lines.append("- Da completare.")

    return "\n".join(lines).rstrip() + "\n"


def _section_manifest(
    section: _OutlineSection,
    section_slug: str,
    output_path: Path,
    sources: tuple[RetrievedSource, ...],
    code_blocks: list[CodeBlockRow],
    project_dir: Path,
) -> GeneratedSectionManifest:
    rel_output = output_path.relative_to(project_dir).as_posix()
    return GeneratedSectionManifest(
        section_index=section.index,
        section_title=section.title,
        section_slug=section_slug,
        output_path=rel_output,
        sources=[
            GeneratedSectionSource(
                rank=source.rank,
                record_id=source.record_id,
                video_id=source.video_id,
                video_name=source.video_name,
                chunk_id=source.chunk_id,
                start_seconds=source.start_seconds,
                end_seconds=source.end_seconds,
                score=source.score,
                topic=source.topic,
                source_type=source.source_type,
                embedding_type=source.embedding_type,
                text_hash=text_hash(source.text),
            )
            for source in sources
        ],
        code_blocks=[
            GeneratedSectionCodeBlock(
                id=block.id,
                video_id=block.video_id,
                chunk_id=block.chunk_id,
                timestamp_seconds=block.timestamp_seconds,
                language=block.language,
                confidence=block.confidence,
                verified=block.verified,
            )
            for block in code_blocks
        ],
    )


def _code_blocks_for_sources(db_path: Path, sources: tuple[RetrievedSource, ...]) -> list[CodeBlockRow]:
    blocks: list[CodeBlockRow] = []
    seen: set[str] = set()
    by_video: dict[str, list[RetrievedSource]] = {}
    for source in sources:
        by_video.setdefault(source.video_id, []).append(source)

    for video_id, video_sources in by_video.items():
        for block in list_code_blocks(db_path, video_id):
            if block.id in seen:
                continue
            if _block_matches_sources(block, video_sources):
                blocks.append(block)
                seen.add(block.id)
            if len(blocks) >= _MAX_CODE_BLOCKS:
                return blocks
    return blocks


def _block_matches_sources(block: CodeBlockRow, sources: list[RetrievedSource]) -> bool:
    for source in sources:
        if block.chunk_id and block.chunk_id == source.chunk_id:
            return True
        if block.timestamp_seconds is None or source.start_seconds is None or source.end_seconds is None:
            continue
        if source.start_seconds <= block.timestamp_seconds <= source.end_seconds:
            return True
    return False


def _objective_from_outline(section: _OutlineSection) -> str:
    for line in section.body.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("obiettivo:"):
            objective = stripped.split(":", 1)[1].strip()
            if objective:
                return objective[0].upper() + objective[1:]
    return "Raccogliere e organizzare solo le informazioni supportate dalle fonti recuperate."


def _procedure_steps(sources: tuple[RetrievedSource, ...]) -> list[str]:
    steps = []
    for source in sources:
        excerpt = _excerpt(source.text, max_chars=240)
        if excerpt:
            steps.append(f"{excerpt} [{source.rank}]")
    return steps[:5]


def _error_sources(sources: tuple[RetrievedSource, ...]) -> list[RetrievedSource]:
    return [source for source in sources if any(word in source.text.lower() for word in _ERROR_WORDS)]


def _source_label(source: RetrievedSource) -> str:
    time_range = _time_range(source.start_seconds, source.end_seconds)
    topic = f" - {source.topic}" if source.topic else ""
    return f"`{source.video_name or source.video_id}` {time_range}{topic}"


def _time_range(start_seconds: float | None, end_seconds: float | None) -> str:
    if start_seconds is None and end_seconds is None:
        return ""
    if end_seconds is None:
        return f"@{_format_seconds(start_seconds or 0.0)}"
    return f"{_format_seconds(start_seconds or 0.0)}-{_format_seconds(end_seconds)}"


def _optional_timestamp(value: float | None) -> str:
    return f" {_format_seconds(value)}" if value is not None else ""


def _format_seconds(value: float) -> str:
    total = max(0, int(round(value)))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _excerpt(text: str, *, max_chars: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _write_atomic(path: Path, text: str) -> None:
    tmp_path = path.parent / f"{path.name}.tmp"
    try:
        tmp_path.write_text(text, encoding="utf-8")
        tmp_path.replace(path)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise DatabaseError(f"Cannot write generated documentation at {path}: {exc}") from exc
