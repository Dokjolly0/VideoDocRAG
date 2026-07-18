from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from videodoc.core.errors import InvalidChunkManifestError


class ChunkTranscriptSignature(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    start_seconds: float
    end_seconds: float
    text_hash: str
    confidence: float | None = None


class ChunkFrameSignature(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    timestamp_seconds: float
    perceptual_hash: str | None = None
    ocr_text_hash: str | None = None
    ocr_confidence: float | None = None
    contains_code: bool = False


class ChunkCodeSignature(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    timestamp_seconds: float | None = None
    language: str | None = None
    code_hash: str
    confidence: float | None = None
    verified: bool = False


class ChunkCodeBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    language: str | None = None
    code: str
    timestamp_seconds: float | None = None
    confidence: float | None = None
    verified: bool = False


class ChunkManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    source_type: str
    start_seconds: float
    end_seconds: float
    topic: str
    summary: str
    transcript: str = ""
    ocr_text: str = ""
    code_blocks: list[ChunkCodeBlock] = Field(default_factory=list)
    video_name: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_id: str
    video_name: str
    chunks: list[ChunkManifestEntry]
    transcript_inputs: list[ChunkTranscriptSignature] = Field(default_factory=list)
    frame_inputs: list[ChunkFrameSignature] = Field(default_factory=list)
    code_inputs: list[ChunkCodeSignature] = Field(default_factory=list)
    min_duration_seconds: int | None = None
    max_duration_seconds: int | None = None
    include_nearby_frames: bool | None = None

    @classmethod
    def load(cls, path: Path) -> "ChunkManifest":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise InvalidChunkManifestError(f"Cannot read chunk manifest at {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise InvalidChunkManifestError(f"Invalid JSON in {path}: {exc}") from exc
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise InvalidChunkManifestError(f"Invalid chunk manifest in {path}:\n{exc}") from exc

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False)

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")
