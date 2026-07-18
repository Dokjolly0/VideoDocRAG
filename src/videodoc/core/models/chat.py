from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from videodoc.core.errors import InvalidDocumentationSectionManifestError

ChatMode = Literal["docs", "raw", "hybrid"]


class ChatSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rank: int
    source_type: str
    score: float
    text: str
    record_id: str
    video_id: str | None = None
    video_name: str | None = None
    chunk_id: str | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None
    doc_path: str | None = None
    section_title: str | None = None
    topic: str | None = None


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str
    sources: list[ChatSource] = Field(default_factory=list)
    created_at: str


class ChatSessionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str | None = None
    default_source: ChatMode = "docs"
    created_at: str
    updated_at: str
    messages: list[ChatMessage] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "ChatSessionSnapshot":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise InvalidDocumentationSectionManifestError(f"Cannot read chat session at {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise InvalidDocumentationSectionManifestError(f"Invalid JSON in {path}: {exc}") from exc
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise InvalidDocumentationSectionManifestError(f"Invalid chat session in {path}:\n{exc}") from exc

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False)

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")
