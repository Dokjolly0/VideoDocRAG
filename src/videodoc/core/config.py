from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator

from videodoc.core.errors import InvalidConfigError


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


class TranscriptionSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engine: str = "faster-whisper"
    model: str = "large-v3"
    language: str = "it"
    word_timestamps: bool = True


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
    def default(cls, *, name: str, slug: str, language: str = "it") -> "ProjectConfig":
        return cls(project=ProjectSection(name=name, slug=slug, language=language))

    @classmethod
    def load(cls, path: Path) -> "ProjectConfig":
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
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
