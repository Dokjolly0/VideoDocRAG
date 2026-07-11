from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from videodoc.core.errors import InvalidFrameManifestError


class FrameManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    timestamp_seconds: float
    image_path: str  # project-relative posix, mirrors FrameRow.image_path
    perceptual_hash: str | None = None


class FrameManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_id: str
    frames: list[FrameManifestEntry]

    @classmethod
    def load(cls, path: Path) -> "FrameManifest":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise InvalidFrameManifestError(f"Cannot read frame manifest at {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise InvalidFrameManifestError(f"Invalid JSON in {path}: {exc}") from exc
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise InvalidFrameManifestError(f"Invalid frame manifest in {path}:\n{exc}") from exc

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False)

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")
