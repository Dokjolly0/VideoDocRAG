from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator

from videodoc.core.errors import InvalidConfigError
from videodoc.core.utils.paths import has_ambiguous_anchor, has_any_anchor, has_parent_traversal, is_external_source_path


class ProjectSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    slug: str
    language: str = "it"
    timezone: str = "Europe/Rome"


class PathsSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    videos: str = "videos"
    attachments: str = "attachments"
    codebase: str = "codebase"
    workdir: str = "workdir"
    indexes: str = "indexes"
    output: str = "docs"
    database: str = "project.db"

    @field_validator("workdir", "indexes", "output", "database")
    @classmethod
    def _must_stay_inside_project(cls, v: str, info: ValidationInfo) -> str:
        # has_any_anchor (core/utils/paths.py), non un semplice
        # Path(v).is_absolute(): su Windows quest'ultimo da solo
        # rifiuterebbe "C:\foo" ma lascerebbe passare "C:foo" (drive-relative:
        # "cartella corrente sul drive C:") e "\foo" (root-relative: "radice del
        # drive corrente") -- forme che pathlib NON considera absolute ma che,
        # una volta unite a project_dir con l'operatore /, possono comunque
        # scavalcarlo silenziosamente (su POSIX questa ambiguità non esiste
        # affatto, e has_any_anchor si comporta semplicemente come
        # is_absolute() lì -- vedi core/utils/paths.py). has_any_anchor è la
        # stessa identica funzione usata dal validator di
        # videos/attachments/codebase sotto e da
        # resolve_source_path()/SourceScanService -- un'unica definizione
        # condivisa, non tre implementazioni indipendenti che potrebbero
        # divergere, e che si adatta automaticamente all'OS host (Windows,
        # Linux o macOS) tramite pathlib.
        if has_any_anchor(v):
            raise ValueError(
                f"paths.{info.field_name} must be a relative path (resolved against the "
                f"project folder) -- no drive letter, no leading slash, including ambiguous "
                f"forms specific to the host OS's path rules (e.g. Windows drive-relative "
                f"'C:foo' or root-relative '\\foo'), which pathlib does not always classify "
                f"as absolute but which can still escape the project folder when joined with "
                f"it. Absolute paths are only allowed for paths.videos, paths.attachments and "
                f"paths.codebase, which may point to external locations. "
                f"workdir/indexes/output/database must stay physically inside the project folder "
                f"to preserve per-project data isolation (README §8.1.1). Got: {v!r}"
            )
        # A path with no anchor can still escape project_dir once joined with
        # it if it contains '..' segments (e.g. "../outside" or
        # "sub/../../outside") -- rejecting only anchored forms above is not
        # enough to guarantee these four fields stay physically inside the
        # project, which is the whole point of restricting them to relative-only.
        if has_parent_traversal(v):
            raise ValueError(
                f"paths.{info.field_name} must not contain '..' path segments -- "
                f"a relative path like '../outside' can still escape the project "
                f"folder once resolved against it, defeating the same per-project "
                f"data isolation guarantee this field's relative-only restriction "
                f"exists to protect (README §8.1.1). Got: {v!r}"
            )
        return v

    @field_validator("videos", "attachments", "codebase")
    @classmethod
    def _no_ambiguous_windows_forms(cls, v: str, info: ValidationInfo) -> str:
        # Questi tre campi accettano SIA relativo pulito SIA assoluto vero (è
        # il punto della feature: fonti esterne referenziate, su Windows,
        # Linux o macOS -- vedi core/utils/paths.py). Le stesse forme ambigue
        # rifiutate sopra (su Windows: drive-relative "C:foo", root-relative
        # "\foo"/"/foo"; su POSIX questa categoria è strutturalmente vuota)
        # restano pericolose anche qui: non scavalcherebbero project_dir per
        # errore (non vengono mai unite quando "assolute" agli occhi di
        # pathlib), ma produrrebbero una resolve_source_path() il cui
        # comportamento dipende da stato mutabile del processo/dell'host --
        # fragile, non riproducibile, né chiaramente "relativo al progetto"
        # né chiaramente "percorso esterno esplicito". Si rifiutano solo le
        # forme ambigue: un percorso assoluto vero resta valido.
        #
        # has_ambiguous_anchor/is_external_source_path (core/utils/paths.py)
        # sono le stesse identiche funzioni usate da resolve_source_path() e
        # SourceScanService per risolvere/classificare questi path a runtime,
        # entrambe basate sulla semantica nativa dell'host (PurePath) -- così
        # "questo path è considerato esterno" non può mai disaccordare tra
        # validazione e risoluzione, su nessuno dei tre OS supportati.
        if has_ambiguous_anchor(v):
            raise ValueError(
                f"paths.{info.field_name} must be either a clean relative path (resolved "
                f"against the project folder) or a fully absolute path pointing to an "
                f"external source (e.g. 'D:\\Corsi\\Workshop' on Windows, '/mnt/videos' on "
                f"Linux/macOS). Ambiguous forms specific to the host OS's path rules (e.g. "
                f"Windows drive-relative 'C:foo' or root-relative '\\foo', '/foo') are "
                f"rejected: their resolution depends on mutable per-process/per-drive state, "
                f"not on paths.{info.field_name} alone. Got: {v!r}"
            )
        # Same reasoning as workdir/indexes/output/database: a *relative*
        # value with '..' segments can silently escape project_dir once
        # joined with it, which is neither "clean relative to the project"
        # nor "an explicit external reference" -- it's ambiguous in the same
        # way the anchored forms above are. A '..' inside a value that is
        # already fully absolute is fine: it never gets joined with
        # project_dir, so it resolves unambiguously on its own.
        if not is_external_source_path(v) and has_parent_traversal(v):
            raise ValueError(
                f"paths.{info.field_name} must not contain '..' path segments when "
                f"relative -- a relative path like '../outside' can silently escape "
                f"the project folder once resolved against it. To reference an "
                f"external source explicitly, use a fully absolute path (e.g. "
                f"'D:\\Corsi\\Workshop' on Windows, '/mnt/videos' on Linux/macOS) instead "
                f"of a relative one that walks upward. Got: {v!r}"
            )
        return v


class LLMSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = "ollama"
    model: str = "qwen2.5-coder:14b"
    context_window: int = Field(32768, gt=0)
    temperature: float = Field(0.1, ge=0.0, le=2.0)
    top_p: float = Field(0.9, ge=0.0, le=1.0)


class EmbeddingSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = "local"
    model: str = "bge-m3"
    batch_size: int = Field(32, gt=0)


class ConcurrencySection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workers: int | Literal["auto"] = "auto"

    @field_validator("workers")
    @classmethod
    def _workers_positive_or_auto(cls, v: int | Literal["auto"]) -> int | Literal["auto"]:
        if v == "auto":
            return v
        if v <= 0:
            raise ValueError("workers must be 'auto' or a positive integer")
        return v


class TranscriptionSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engine: str = "faster-whisper"
    model: str = "large-v3"
    language: str = "it"
    word_timestamps: bool = False
    device: Literal["auto", "cpu", "cuda"] = "auto"
    compute_type: str = "auto"
    mode: Literal["auto", "standard", "batched"] = "auto"
    workers: int | Literal["auto"] = "auto"
    cpu_threads: int | Literal["auto"] = "auto"
    batch_size: int | Literal["auto"] = "auto"
    beam_size: int = Field(1, gt=0)
    best_of: int = Field(1, gt=0)
    vad_filter: bool = True
    chunk_length_seconds: int = Field(30, gt=0)
    condition_on_previous_text: bool = False

    @field_validator("workers", "cpu_threads", "batch_size")
    @classmethod
    def _positive_or_auto(cls, v: int | Literal["auto"], info: ValidationInfo) -> int | Literal["auto"]:
        if v == "auto":
            return v
        if v <= 0:
            raise ValueError(f"{info.field_name} must be 'auto' or a positive integer")
        return v


class FramesSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interval_seconds: int = Field(8, gt=0)
    scene_detection: bool = True
    keyword_boost: bool = True


class OCRSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engine: str = "paddleocr"
    languages: list[str] = Field(default_factory=lambda: ["it", "en"])
    min_confidence: float = Field(0.65, ge=0.0, le=1.0)


class ChunkingSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_duration_seconds: int = Field(90, gt=0)
    max_duration_seconds: int = Field(480, gt=0)
    split_on_topic_change: bool = True
    include_nearby_frames: bool = True

    @field_validator("max_duration_seconds")
    @classmethod
    def _max_gte_min(cls, v: int, info: ValidationInfo) -> int:
        min_v = info.data.get("min_duration_seconds")
        if min_v is not None and v < min_v:
            raise ValueError("max_duration_seconds must be >= min_duration_seconds")
        return v


class RetrievalSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vector_db: str = "qdrant"
    top_k: int = Field(12, gt=0)
    rerank: bool = True
    hybrid_search: bool = True


class CodeSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extract_from_ocr: bool = True
    extract_from_attachments: bool = True
    extract_from_codebase: bool = True
    strict_mode: bool = True
    mark_uncertain_code: bool = True


class ScanSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_excludes: bool = True
    add_excludes: list[str] = Field(default_factory=list)
    remove_excludes: list[str] = Field(default_factory=list)
    max_file_size_mb: int = Field(5, gt=0)
    follow_symlinks: bool = False
    allowed_code_extensions: list[str] = Field(
        default_factory=lambda: [
            ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml", ".md",
        ]
    )
    allowed_video_extensions: list[str] = Field(
        default_factory=lambda: [".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv"]
    )


class DocumentationSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["markdown"] = "markdown"
    include_video_name: bool = True
    include_timestamps: bool = True
    include_code_explanation: bool = True
    include_expected_result: bool = True
    include_common_errors: bool = True
    include_sources_section: bool = True


class ChatSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_source: Literal["docs", "raw", "hybrid"] = "docs"
    allow_raw_video_filter: bool = True
    allow_multi_video_filter: bool = True
    allow_time_range_filter: bool = True
    save_sessions: bool = True
    max_history_messages: int = Field(20, gt=0)
    default_top_k: int = Field(8, gt=0)


class GUISection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    backend: str = "fastapi"
    frontend: str = "react"
    host: str = "127.0.0.1"
    port: int = Field(8000, gt=0, le=65535)


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project: ProjectSection
    paths: PathsSection = Field(default_factory=PathsSection)
    llm: LLMSection = Field(default_factory=LLMSection)
    embedding: EmbeddingSection = Field(default_factory=EmbeddingSection)
    ingest: ConcurrencySection = Field(default_factory=ConcurrencySection)
    audio: ConcurrencySection = Field(default_factory=ConcurrencySection)
    transcription: TranscriptionSection = Field(default_factory=TranscriptionSection)
    frames: FramesSection = Field(default_factory=FramesSection)
    ocr: OCRSection = Field(default_factory=OCRSection)
    chunking: ChunkingSection = Field(default_factory=ChunkingSection)
    retrieval: RetrievalSection = Field(default_factory=RetrievalSection)
    code: CodeSection = Field(default_factory=CodeSection)
    scan: ScanSection = Field(default_factory=ScanSection)
    documentation: DocumentationSection = Field(default_factory=DocumentationSection)
    chat: ChatSection = Field(default_factory=ChatSection)
    gui: GUISection = Field(default_factory=GUISection)

    @classmethod
    def default(
        cls, *, name: str, slug: str, language: str = "it",
        videos: str | None = None, attachments: str | None = None, codebase: str | None = None,
    ) -> "ProjectConfig":
        overrides = {
            k: v for k, v in {"videos": videos, "attachments": attachments, "codebase": codebase}.items()
            if v is not None
        }
        try:
            return cls(
                project=ProjectSection(name=name, slug=slug, language=language),
                paths=PathsSection(**overrides),
            )
        except ValidationError as exc:
            # Senza questo try/except, un ValidationError qui (es. da
            # videos="C:foo", rifiutato dal validator sopra) propagherebbe
            # grezzo fino alla CLI: init_command intercetta solo
            # InvalidConfigError/InvalidProjectNameError/RegistryConflictError.
            # default() diventa "safe" come load() -- stesso confine per
            # input controllato dall'utente.
            raise InvalidConfigError(f"Invalid project configuration:\n{exc}") from exc

    @classmethod
    def load(cls, path: Path) -> "ProjectConfig":
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except OSError as exc:
            # Copre anche il file mancante (FileNotFoundError è una
            # sottoclasse di OSError): "missing, malformed, or fails
            # validation" deve coprire tutti e tre i casi, non solo YAML
            # invalido. In pratica i chiamanti interni verificano sempre
            # config_path.is_file() prima di chiamare load(), ma l'API
            # stessa deve restare corretta indipendentemente da questo.
            raise InvalidConfigError(f"Cannot read config at {path}: {exc}") from exc
        except yaml.YAMLError as exc:
            raise InvalidConfigError(f"Invalid YAML in {path}: {exc}") from exc
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise InvalidConfigError(f"Invalid configuration in {path}:\n{exc}") from exc

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False, allow_unicode=True)

    def save(self, path: Path) -> None:
        path.write_text(self.to_yaml(), encoding="utf-8")
