from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.models.source_manifest import CodebaseManifest, ExclusionsManifest, SourceManifest
from videodoc.core.storage import filesystem
from videodoc.core.utils.paths import is_external_source_path


@dataclass(frozen=True)
class SourcePathReport:
    configured: str  # raw value from config.yaml
    resolved_path: Path  # always absolute/resolved
    is_external: bool
    exists: bool  # True if resolved_path exists on disk at all, file or directory
    is_directory: bool  # True only if it exists AND is a directory -- the actually usable case


@dataclass(frozen=True)
class ScanResult:
    manifest: SourceManifest
    manifest_path: Path
    videos_report: SourcePathReport
    attachments_report: SourcePathReport
    codebase_report: SourcePathReport


class SourceScanService:
    def __init__(self, project_dir: Path, config: ProjectConfig) -> None:
        self.project_dir = project_dir
        self.config = config

    def run(self) -> ScanResult:
        scan_cfg, paths_cfg = self.config.scan, self.config.paths

        videos_report = self._resolve_report(paths_cfg.videos)
        attachments_report = self._resolve_report(paths_cfg.attachments)
        codebase_report = self._resolve_report(paths_cfg.codebase)

        # The gate is is_directory, not exists: a path that exists but is a
        # file (not a directory) can't be walked, so it's treated as "0
        # files", not as an error and not as if it were actually missing.
        scan_errors: list[str] = []

        videos_errors: list[str] = []
        videos = (
            filesystem.scan_videos(videos_report.resolved_path, scan_cfg, videos_errors)
            if videos_report.is_directory else []
        )
        scan_errors.extend(f"videos: {e}" for e in videos_errors)

        attachments_errors: list[str] = []
        attachments = (
            filesystem.scan_attachments(attachments_report.resolved_path, scan_cfg, attachments_errors)
            if attachments_report.is_directory else []
        )
        scan_errors.extend(f"attachments: {e}" for e in attachments_errors)

        # codebase_is_present() and scan_codebase() share one errors list so
        # a permission problem surfaced by either (root itself unreadable,
        # or a subdirectory encountered mid-walk) ends up in the same
        # "codebase: ..." prefixed group.
        codebase_errors: list[str] = []
        codebase_present = (
            filesystem.codebase_is_present(codebase_report.resolved_path, codebase_errors)
            if codebase_report.is_directory else False
        )
        codebase_files = (
            filesystem.scan_codebase(codebase_report.resolved_path, scan_cfg, codebase_errors)
            if codebase_present else []
        )
        scan_errors.extend(f"codebase: {e}" for e in codebase_errors)

        dir_excludes, file_excludes = filesystem.split_excludes(filesystem.resolve_excludes(scan_cfg))

        manifest = SourceManifest(
            scanned_at=datetime.now(timezone.utc),
            videos=[v.as_posix() for v in videos],
            attachments=[a.as_posix() for a in attachments],
            codebase=CodebaseManifest(present=codebase_present, files=[f.as_posix() for f in codebase_files]),
            exclusions=ExclusionsManifest(directories=sorted(dir_excludes), file_patterns=sorted(file_excludes)),
            scan_errors=scan_errors,
        )
        manifest_path = self.project_dir / "sources.yaml"
        manifest.save(manifest_path)  # always regenerated in full, never merged

        return ScanResult(
            manifest=manifest, manifest_path=manifest_path,
            videos_report=videos_report, attachments_report=attachments_report, codebase_report=codebase_report,
        )

    def _resolve_report(self, configured: str) -> SourcePathReport:
        # is_external_source_path (core/utils/paths.py), not a bare
        # Path(configured).is_absolute(): the same helper the config
        # validator and resolve_source_path() use, so "is this external"
        # can never disagree between validation, resolution, and reporting.
        is_external = is_external_source_path(configured)
        try:
            resolved = filesystem.resolve_source_path(self.project_dir, configured)
            exists = resolved.exists()
            is_directory = resolved.is_dir()
        except OSError:
            # e.g. a disconnected drive on Windows -> never a crash: 0 files found
            resolved = Path(configured)
            exists = False
            is_directory = False
        return SourcePathReport(
            configured=configured, resolved_path=resolved, is_external=is_external,
            exists=exists, is_directory=is_directory,
        )
