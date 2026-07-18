from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from videodoc.core.errors import InvalidDocumentationSectionManifestError


class GeneratedSectionSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rank: int
    record_id: str
    video_id: str
    video_name: str
    chunk_id: str
    start_seconds: float | None
    end_seconds: float | None
    score: float
    topic: str | None
    source_type: str | None
    embedding_type: str
    text_hash: str


class GeneratedSectionCodeBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    video_id: str
    chunk_id: str | None
    timestamp_seconds: float | None
    language: str | None
    confidence: float | None
    verified: bool


class GeneratedSectionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section_index: int
    section_title: str
    section_slug: str
    output_path: str
    sources: list[GeneratedSectionSource]
    code_blocks: list[GeneratedSectionCodeBlock]

    @classmethod
    def load(cls, path: Path) -> "GeneratedSectionManifest":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise InvalidDocumentationSectionManifestError(f"Cannot read section manifest at {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise InvalidDocumentationSectionManifestError(f"Invalid JSON in {path}: {exc}") from exc
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise InvalidDocumentationSectionManifestError(f"Invalid section manifest in {path}:\n{exc}") from exc

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False)

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")
