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
    # The effective selection settings used to produce this manifest --
    # FrameExtractionService compares these against the *current* run's
    # settings before taking the skip/self-heal path: without this, a
    # rerun with different --interval-seconds/--scene-detection/
    # --keyword-boost would silently keep the stale frames from whatever
    # settings were used originally, since "frames.json already exists"
    # alone used to be the only skip condition. Optional (default None) so
    # a manifest written before this field existed still parses instead of
    # raising InvalidFrameManifestError -- FrameExtractionService treats
    # None the same as "settings unknown" -> always re-extract, which for
    # any manifest predating this field is the correct, safe behavior.
    interval_seconds: int | None = None
    scene_detection: bool | None = None
    keyword_boost: bool | None = None

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
