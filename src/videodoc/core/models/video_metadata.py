from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from videodoc.core.errors import InvalidVideoMetadataError


class VideoMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_id: str
    video_name: str
    title: str | None = None
    duration_seconds: float
    language: str
    hash: str
    format: str
    width: int
    height: int
    codec: str
    # Project-relative posix paths (always inside workdir/, which
    # PathsSection's own validator guarantees stays physically inside the
    # project folder) -- deliberately NOT absolute, unlike project.db's
    # VideoRow.path (which mirrors sources.yaml's genuinely-external
    # duality). A project must stay a self-contained, movable/archivable
    # unit (README §8.1.1); an absolute path baked in here would silently
    # break the moment the project folder moves.
    audio_path: str
    transcript_path: str
    frames_path: str
    ocr_path: str
    chunks_path: str

    @classmethod
    def load(cls, path: Path) -> "VideoMetadata":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise InvalidVideoMetadataError(f"Cannot read video metadata at {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise InvalidVideoMetadataError(f"Invalid JSON in {path}: {exc}") from exc
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise InvalidVideoMetadataError(f"Invalid video metadata in {path}:\n{exc}") from exc

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False)

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")
