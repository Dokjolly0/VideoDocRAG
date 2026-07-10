from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from videodoc.core.errors import InvalidSourceManifestError


class CodebaseManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    present: bool = False
    files: list[str] = Field(default_factory=list)


class ExclusionsManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    directories: list[str] = Field(default_factory=list)
    file_patterns: list[str] = Field(default_factory=list)


class SourceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scanned_at: datetime
    videos: list[str] = Field(default_factory=list)
    attachments: list[str] = Field(default_factory=list)
    codebase: CodebaseManifest = Field(default_factory=CodebaseManifest)
    exclusions: ExclusionsManifest = Field(default_factory=ExclusionsManifest)
    scan_errors: list[str] = Field(default_factory=list)
    # Problems encountered while walking a source (e.g. a subdirectory that
    # couldn't be scanned due to permissions). The scan itself never fails
    # because of these -- they're recorded here (and surfaced as CLI
    # warnings) so an incomplete result is never silently mistaken for a
    # complete one.

    @classmethod
    def load(cls, path: Path) -> "SourceManifest":
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except OSError as exc:
            # Covers a missing file too (FileNotFoundError is an OSError
            # subclass): "missing, malformed, or fails validation" must cover
            # all three cases, not just invalid YAML.
            raise InvalidSourceManifestError(f"Cannot read sources manifest at {path}: {exc}") from exc
        except yaml.YAMLError as exc:
            raise InvalidSourceManifestError(f"Invalid YAML in {path}: {exc}") from exc
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise InvalidSourceManifestError(f"Invalid sources manifest in {path}:\n{exc}") from exc

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False, allow_unicode=True)

    def save(self, path: Path) -> None:
        path.write_text(self.to_yaml(), encoding="utf-8")
