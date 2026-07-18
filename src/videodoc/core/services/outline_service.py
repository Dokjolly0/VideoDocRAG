from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import (
    DatabaseError,
    InvalidSourceManifestError,
    NoVideosFoundError,
    OutlineSourceUnavailableError,
)
from videodoc.core.models.source_manifest import SourceManifest
from videodoc.core.storage.database import (
    ChunkRow,
    CodeBlockRow,
    VideoRow,
    ensure_schema,
    list_chunks,
    list_code_blocks,
    list_videos,
)

_SECTION_TITLES = (
    "Introduzione",
    "Installazione",
    "Configurazione ambiente",
    "Creazione del primo progetto",
    "Funzionalita principali",
    "Debug e troubleshooting",
    "Deployment",
    "Appendici",
)
_SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Introduzione": ("introduzione", "panoramica", "overview", "obiettivo", "contesto", "architettura"),
    "Installazione": ("install", "setup", "dipenden", "requisit", "venv", "pip", "npm", "package"),
    "Configurazione ambiente": ("config", "database", "env", "variabil", "yaml", "settings", "porta", "token"),
    "Creazione del primo progetto": ("progetto", "init", "crea", "nuovo", "primo", "workspace"),
    "Funzionalita principali": ("funzion", "feature", "comando", "workflow", "uso", "dashboard", "servizio"),
    "Debug e troubleshooting": ("debug", "errore", "error", "warning", "exception", "problema", "fix", "troubleshoot"),
    "Deployment": ("deploy", "release", "produzione", "docker", "build", "server", "hosting", "cloud"),
    "Appendici": ("appendice", "riferiment", "allegat", "codice", "codebase", "extra"),
}
_MAX_SOURCE_BULLETS = 5
_MAX_CODE_BULLETS = 4
_MAX_ATTACHMENT_BULLETS = 8
_MAX_CODEBASE_BULLETS = 8


@dataclass(frozen=True)
class OutlineResult:
    generated: bool
    skipped: bool
    outline_path: Path
    sections: int
    warnings: tuple[str, ...] = ()


@dataclass
class _SectionDraft:
    title: str
    chunks: list[tuple[VideoRow, ChunkRow]] = field(default_factory=list)
    code_blocks: list[tuple[VideoRow | None, CodeBlockRow]] = field(default_factory=list)


class OutlineService:
    def __init__(self, project_dir: Path, config: ProjectConfig) -> None:
        self.project_dir = project_dir
        self.config = config
        self.outline_path = self.project_dir / config.paths.output / "outline.md"

    def run(self, *, force: bool = False) -> OutlineResult:
        if self.outline_path.is_file() and not force:
            return OutlineResult(
                generated=False,
                skipped=True,
                outline_path=self.outline_path,
                sections=_count_existing_sections(self.outline_path),
            )

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

        warnings: list[str] = []
        chunks_by_video = {video.id: list_chunks(db_path, video.id) for video in videos}
        if not any(chunks_by_video.values()):
            raise OutlineSourceUnavailableError("No chunks found -- run 'videodoc chunk' first.")

        code_by_video = {video.id: list_code_blocks(db_path, video.id) for video in videos}
        sources = _load_source_manifest(self.project_dir, warnings)
        sections = _draft_sections(videos, chunks_by_video, code_by_video)
        markdown = _render_outline(self.config.project.name, sections, sources)

        self.outline_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.outline_path.parent / f"{self.outline_path.name}.tmp"
        try:
            tmp_path.write_text(markdown, encoding="utf-8")
            tmp_path.replace(self.outline_path)
        except OSError as exc:
            tmp_path.unlink(missing_ok=True)
            raise DatabaseError(f"Cannot write documentation outline at {self.outline_path}: {exc}") from exc

        return OutlineResult(
            generated=True,
            skipped=False,
            outline_path=self.outline_path,
            sections=len(sections),
            warnings=tuple(warnings),
        )


def _draft_sections(
    videos: list[VideoRow],
    chunks_by_video: dict[str, list[ChunkRow]],
    code_by_video: dict[str, list[CodeBlockRow]],
) -> list[_SectionDraft]:
    sections = [_SectionDraft(title) for title in _SECTION_TITLES]
    by_title = {section.title: section for section in sections}
    video_by_id = {video.id: video for video in videos}
    chunk_to_section: dict[tuple[str, str], _SectionDraft] = {}

    for video in videos:
        for chunk in chunks_by_video.get(video.id, []):
            section = by_title[_best_section_title(chunk)]
            section.chunks.append((video, chunk))
            chunk_to_section[(video.id, chunk.id)] = section

    appendices = by_title["Appendici"]
    for video_id, blocks in code_by_video.items():
        video = video_by_id.get(video_id)
        video_chunks = chunks_by_video.get(video_id, [])
        for block in blocks:
            section = _section_for_code_block(block, video_chunks, chunk_to_section) or appendices
            section.code_blocks.append((video, block))

    return sections


def _best_section_title(chunk: ChunkRow) -> str:
    haystack = " ".join(
        part for part in [chunk.topic or "", chunk.summary or "", chunk.transcript or "", chunk.ocr_text or ""] if part
    ).lower()
    best_title = "Funzionalita principali"
    best_score = 0
    for title, keywords in _SECTION_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in haystack)
        if score > best_score:
            best_title = title
            best_score = score
    return best_title


def _section_for_code_block(
    block: CodeBlockRow,
    chunks: list[ChunkRow],
    chunk_to_section: dict[tuple[str, str], _SectionDraft],
) -> _SectionDraft | None:
    if block.chunk_id:
        direct = chunk_to_section.get((block.video_id, block.chunk_id))
        if direct is not None:
            return direct
    if block.timestamp_seconds is None:
        return None
    for chunk in chunks:
        if chunk.start_seconds <= block.timestamp_seconds <= chunk.end_seconds:
            return chunk_to_section.get((block.video_id, chunk.id))
    return None


def _render_outline(project_name: str, sections: list[_SectionDraft], sources: SourceManifest | None) -> str:
    lines = [
        f"# Documentazione {project_name}",
        "",
        "> Outline generato automaticamente da VideoDocRAG. Modificabile manualmente prima di `videodoc generate`.",
        "",
    ]
    for index, section in enumerate(sections, start=1):
        lines.extend(_render_section(index, section))

    appendices = sections[-1]
    extra_lines = _render_external_sources(sources)
    if extra_lines:
        if lines[-1] != "":
            lines.append("")
        lines.extend(extra_lines)
        if appendices.title != "Appendici":
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_section(index: int, section: _SectionDraft) -> list[str]:
    lines = [f"## {index}. {section.title}", ""]
    lines.append(f"Obiettivo: {_section_goal(section.title)}")
    lines.append("")
    lines.append("Fonti candidate:")
    if section.chunks:
        for video, chunk in section.chunks[:_MAX_SOURCE_BULLETS]:
            lines.append(f"- {_chunk_source(video, chunk)}")
    else:
        lines.append("- Da completare manualmente.")
    if len(section.chunks) > _MAX_SOURCE_BULLETS:
        lines.append(f"- Altri {len(section.chunks) - _MAX_SOURCE_BULLETS} chunk collegati.")

    if section.code_blocks:
        lines.append("")
        lines.append("Codice rilevante:")
        for video, block in section.code_blocks[:_MAX_CODE_BULLETS]:
            lines.append(f"- {_code_source(video, block)}")
        if len(section.code_blocks) > _MAX_CODE_BULLETS:
            lines.append(f"- Altri {len(section.code_blocks) - _MAX_CODE_BULLETS} blocchi codice collegati.")
    lines.append("")
    return lines


def _render_external_sources(sources: SourceManifest | None) -> list[str]:
    if sources is None:
        return []

    lines: list[str] = []
    if sources.attachments:
        lines.append("Materiali allegati:")
        for path in sources.attachments[:_MAX_ATTACHMENT_BULLETS]:
            lines.append(f"- {Path(path).name}")
        if len(sources.attachments) > _MAX_ATTACHMENT_BULLETS:
            lines.append(f"- Altri {len(sources.attachments) - _MAX_ATTACHMENT_BULLETS} allegati.")

    if sources.codebase.present and sources.codebase.files:
        if lines:
            lines.append("")
        lines.append("Codebase rilevata:")
        for path in sources.codebase.files[:_MAX_CODEBASE_BULLETS]:
            lines.append(f"- {Path(path).as_posix()}")
        if len(sources.codebase.files) > _MAX_CODEBASE_BULLETS:
            lines.append(f"- Altri {len(sources.codebase.files) - _MAX_CODEBASE_BULLETS} file.")
    return lines


def _section_goal(title: str) -> str:
    return {
        "Introduzione": "presentare contesto, scopo e prerequisiti del materiale.",
        "Installazione": "raccogliere passaggi di setup, dipendenze e preparazione iniziale.",
        "Configurazione ambiente": "descrivere configurazioni, variabili, file e servizi necessari.",
        "Creazione del primo progetto": "ordinare i passaggi iniziali per creare e avviare il primo progetto.",
        "Funzionalita principali": "spiegare i workflow e le funzioni operative piu ricorrenti.",
        "Debug e troubleshooting": "raccogliere errori, diagnosi, verifiche e possibili correzioni.",
        "Deployment": "documentare build, rilascio e aspetti di esecuzione in produzione.",
        "Appendici": "conservare riferimenti, allegati, codebase e materiale di supporto.",
    }[title]


def _chunk_source(video: VideoRow, chunk: ChunkRow) -> str:
    topic = chunk.topic or "Senza topic"
    summary = _excerpt(chunk.summary or chunk.transcript or chunk.ocr_text or "", max_chars=180)
    suffix = f": {summary}" if summary else ""
    return f"{_video_label(video)} {_time_range(chunk.start_seconds, chunk.end_seconds)} - {topic}{suffix}"


def _code_source(video: VideoRow | None, block: CodeBlockRow) -> str:
    video_name = _video_label(video) if video is not None else block.video_id
    language = block.language or "text"
    timestamp = f" {_format_seconds(block.timestamp_seconds)}" if block.timestamp_seconds is not None else ""
    confidence = f", confidence={block.confidence:.2f}" if block.confidence is not None else ""
    verified = ", verified" if block.verified else ""
    snippet = _excerpt(block.code, max_chars=120)
    return f"{video_name}{timestamp} - {language}{confidence}{verified}: {snippet}"


def _video_label(video: VideoRow) -> str:
    return video.title or video.filename


def _load_source_manifest(project_dir: Path, warnings: list[str]) -> SourceManifest | None:
    path = project_dir / "sources.yaml"
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        warnings.append(f"sources.yaml could not be read, attachments/codebase omitted: {exc}")
        return None
    if not raw.strip() or raw.strip() == "# Populated by 'videodoc scan'":
        return None
    try:
        return SourceManifest.load(path)
    except InvalidSourceManifestError as exc:
        warnings.append(f"sources.yaml could not be parsed, attachments/codebase omitted: {exc}")
        return None


def _count_existing_sections(path: Path) -> int:
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("## "))
    except OSError:
        return 0


def _time_range(start_seconds: float, end_seconds: float) -> str:
    return f"{_format_seconds(start_seconds)}-{_format_seconds(end_seconds)}"


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
