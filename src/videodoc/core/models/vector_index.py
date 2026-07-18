from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from videodoc.core.errors import InvalidVectorIndexError


class VectorIndexInputSignature(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_id: str
    backend: str
    provider: str
    model: str
    dimensions: int
    records_hash: str


class VectorIndexRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    vector: list[float]
    payload: dict[str, Any] = Field(default_factory=dict)


class VectorIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")
    backend: str
    configured_vector_db: str
    distance: str
    dimensions: int
    inputs: list[VectorIndexInputSignature]
    records: list[VectorIndexRecord]

    @classmethod
    def load(cls, path: Path) -> "VectorIndex":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise InvalidVectorIndexError(f"Cannot read vector index at {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise InvalidVectorIndexError(f"Invalid JSON in {path}: {exc}") from exc
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise InvalidVectorIndexError(f"Invalid vector index in {path}:\n{exc}") from exc

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False)

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")
