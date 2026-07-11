from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from videodoc.core.errors import InvalidOCRManifestError


class OCRManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame_id: str
    # "" (not None) means OCR ran on this frame and found either no text or
    # text below config.ocr.min_confidence -- confidence is still the real
    # measured score, never discarded, so "ran but low-confidence noise" stays
    # distinguishable from "OCR never ran on this frame" (frames.ocr_text
    # stays NULL in the DB for the latter, e.g. a per-frame failure).
    ocr_text: str
    confidence: float
    # The frame's own timestamp_seconds/perceptual_hash *at the time this
    # entry's OCR ran* -- not just its id. Frame ids are assigned densely by
    # position (demo_frame_0001, demo_frame_0002, ...), so a 'videodoc
    # frames' re-run with different settings (e.g. a different
    # --interval-seconds) can produce a completely different set of
    # timestamps/images while still landing on the exact same *count* of
    # frames, and therefore the exact same set of ids. Comparing only the
    # frame-id set (as an earlier version of this idempotency check did)
    # would then treat genuinely different frame content as unchanged and
    # silently reapply this entry's stale OCR text to a brand-new image.
    # Optional/None so a manifest written before these fields existed still
    # parses -- OCRService treats a None-vs-real mismatch the same as any
    # other signature mismatch, i.e. "re-OCR to be safe", never as a match.
    timestamp_seconds: float | None = None
    perceptual_hash: str | None = None


class OCRManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_id: str
    entries: list[OCRManifestEntry]
    # Effective settings used to produce this manifest -- OCRService compares
    # these against the *current* run's settings, plus each entry's own
    # timestamp_seconds/perceptual_hash against the corresponding live frame
    # row's (see OCRManifestEntry), before taking the skip/self-heal path,
    # exactly like FrameManifest's own interval_seconds/scene_detection/
    # keyword_boost comparison. Optional (default None) so a manifest written
    # before these fields existed still parses instead of raising
    # InvalidOCRManifestError -- OCRService treats None the same as "settings
    # unknown" -> always re-OCR, the safe default for any manifest predating
    # this field.
    engine: str | None = None
    languages: list[str] | None = None
    min_confidence: float | None = None

    @classmethod
    def load(cls, path: Path) -> "OCRManifest":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise InvalidOCRManifestError(f"Cannot read OCR manifest at {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise InvalidOCRManifestError(f"Invalid JSON in {path}: {exc}") from exc
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise InvalidOCRManifestError(f"Invalid OCR manifest in {path}:\n{exc}") from exc

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False)

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")
