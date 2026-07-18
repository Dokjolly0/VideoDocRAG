from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from videodoc.core.errors import InvalidDocumentationSectionManifestError

IssueSeverity = Literal["error", "warning", "info"]


class ReviewIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    severity: IssueSeverity
    check: str
    section_path: str
    message: str


class ReviewedCodeBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    section_path: str
    classification: Literal["verified", "high_confidence", "ocr_extracted", "reconstructed", "needs_review"]
    confidence: float | None = None
    verified: bool = False


class ReviewedSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    source_manifest_path: str | None = None
    issue_count: int = 0


class DocumentationReviewReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sections: list[ReviewedSection]
    issues: list[ReviewIssue]
    code_blocks: list[ReviewedCodeBlock]

    @classmethod
    def load(cls, path: Path) -> "DocumentationReviewReport":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise InvalidDocumentationSectionManifestError(f"Cannot read review report at {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise InvalidDocumentationSectionManifestError(f"Invalid JSON in {path}: {exc}") from exc
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise InvalidDocumentationSectionManifestError(f"Invalid review report in {path}:\n{exc}") from exc

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False)

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")
