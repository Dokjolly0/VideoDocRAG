from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from videodoc.core.errors import InvalidCodebaseManifestError


class CodebaseFileEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    file_hash: str
    size_bytes: int
    snippet_count: int


class CodebaseSnippet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    project_id: str
    source_type: str = "codebase"
    file_path: str
    language: str | None = None
    start_line: int
    end_line: int
    symbol_name: str | None = None
    content: str
    file_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CodebaseSyncManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    codebase_root: str
    synced_at: str
    settings_hash: str
    files: list[CodebaseFileEntry]
    snippets: list[CodebaseSnippet]
    scan_errors: list[str] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "CodebaseSyncManifest":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise InvalidCodebaseManifestError(f"Cannot read codebase manifest at {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise InvalidCodebaseManifestError(f"Invalid JSON in {path}: {exc}") from exc
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise InvalidCodebaseManifestError(f"Invalid codebase manifest in {path}:\n{exc}") from exc

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False)

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")
