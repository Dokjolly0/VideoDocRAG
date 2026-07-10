from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from videodoc.core.errors import InvalidTranscriptError

# README describes three mutually inconsistent shapes for a transcript
# segment: §17's simplified illustration ({"start": 12.4, "end": 28.7,
# "text": ...}), §9.2's richer example (HH:MM:SS start_time/end_time
# strings plus confidence), and §31/§30.2's actual SQL schema
# (start_seconds/end_seconds REAL). This module -- and the transcript_segments
# table in core/storage/database.py -- resolve that inconsistency by treating
# the SQL schema as authoritative (project.db is README's own stated source
# of truth, §8.1.1): both the DB rows and this JSON file use start_seconds/
# end_seconds (float), never HH:MM:SS strings or the bare start/end shape.


class TranscriptSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    start_seconds: float
    end_seconds: float
    text: str
    confidence: float | None = None


class Transcript(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_id: str
    engine: str
    model: str
    language: str
    segments: list[TranscriptSegment]

    @classmethod
    def load(cls, path: Path) -> "Transcript":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise InvalidTranscriptError(f"Cannot read transcript at {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise InvalidTranscriptError(f"Invalid JSON in {path}: {exc}") from exc
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise InvalidTranscriptError(f"Invalid transcript in {path}:\n{exc}") from exc

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False)

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")
