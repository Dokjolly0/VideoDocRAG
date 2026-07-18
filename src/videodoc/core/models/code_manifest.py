from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from videodoc.core.errors import InvalidCodeManifestError


class CodeInputFrameSignature(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame_id: str
    timestamp_seconds: float
    perceptual_hash: str | None = None
    ocr_text_hash: str | None = None
    ocr_confidence: float | None = None


class CodeSourceFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame_id: str
    timestamp_seconds: float
    ocr_confidence: float | None = None


class CodeValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    error: str | None = None


class CodeManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    content_type: str
    language: str
    code: str
    normalized_hash: str
    timestamp_seconds: float
    end_timestamp_seconds: float | None = None
    source: str = "ocr"
    confidence: float | None = None
    verified: bool = False
    validation: CodeValidation
    source_frames: list[CodeSourceFrame]
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)


class CodeManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_id: str
    entries: list[CodeManifestEntry]
    input_frames: list[CodeInputFrameSignature]
    extract_from_ocr: bool | None = None
    strict_mode: bool | None = None
    mark_uncertain_code: bool | None = None

    @classmethod
    def load(cls, path: Path) -> "CodeManifest":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise InvalidCodeManifestError(f"Cannot read code manifest at {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise InvalidCodeManifestError(f"Invalid JSON in {path}: {exc}") from exc
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise InvalidCodeManifestError(f"Invalid code manifest in {path}:\n{exc}") from exc

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False)

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")
