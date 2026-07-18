from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from videodoc.core.errors import InvalidEmbeddingManifestError


class EmbeddingChunkSignature(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    source_type: str
    start_seconds: float
    end_seconds: float
    topic_hash: str
    summary_hash: str
    transcript_hash: str
    ocr_hash: str
    code_hash: str
    metadata_hash: str


class EmbeddingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    chunk_id: str
    embedding_type: str
    text: str
    text_hash: str
    vector: list[float]
    dimensions: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmbeddingManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_id: str
    video_name: str
    backend: str
    provider: str
    model: str
    dimensions: int
    batch_size: int
    chunk_inputs: list[EmbeddingChunkSignature]
    records: list[EmbeddingRecord]

    @classmethod
    def load(cls, path: Path) -> "EmbeddingManifest":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise InvalidEmbeddingManifestError(f"Cannot read embedding manifest at {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise InvalidEmbeddingManifestError(f"Invalid JSON in {path}: {exc}") from exc
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise InvalidEmbeddingManifestError(f"Invalid embedding manifest in {path}:\n{exc}") from exc

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False)

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")
