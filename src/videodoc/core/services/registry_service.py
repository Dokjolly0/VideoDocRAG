from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import platformdirs

from videodoc.core.errors import ProjectNotFoundError, RegistryConflictError

logger = logging.getLogger("videodoc.registry")

REGISTRY_VERSION = 1
REGISTRY_FILENAME = "registry.json"
DATA_DIR_ENV_VAR = "VIDEODOC_DATA_DIR"  # full data-dir override, used by tests


@dataclass(frozen=True)
class ProjectEntry:
    name: str
    path: Path
    created_at: datetime


class ProjectRegistry:
    def __init__(self, registry_path: Path | None = None) -> None:
        self._registry_path = registry_path or self.default_path()

    @staticmethod
    def default_path() -> Path:
        """VIDEODOC_DATA_DIR takes absolute priority (used by tests so the
        real user data-dir is never touched). Otherwise
        platformdirs.user_data_dir('videodoc', appauthor=False)/registry.json.
        Always computed on demand (never cached at module scope), so tests
        can change the env var/monkeypatch between cases."""
        override = os.environ.get(DATA_DIR_ENV_VAR)
        base = Path(override) if override else Path(
            platformdirs.user_data_dir("videodoc", appauthor=False)
        )
        return base / REGISTRY_FILENAME

    def _load(self) -> dict:
        if not self._registry_path.exists():
            return {"version": REGISTRY_VERSION, "projects": {}}
        try:
            data = json.loads(self._registry_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("projects"), dict):
                raise ValueError("missing or invalid 'projects' key")
            return data
        except (json.JSONDecodeError, ValueError) as exc:
            self._quarantine_corrupted_file(exc)
            return {"version": REGISTRY_VERSION, "projects": {}}

    def _quarantine_corrupted_file(self, exc: Exception) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup = self._registry_path.with_name(f"{self._registry_path.name}.corrupted-{ts}")
        try:
            self._registry_path.replace(backup)
        except OSError:
            pass
        logger.warning(
            "Registry file %s is corrupted (%s); backed up to %s, starting from an empty registry.",
            self._registry_path, exc, backup,
        )

    def _save(self, data: dict) -> None:
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._registry_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(self._registry_path)  # atomic write

    def register(self, name: str, path: Path) -> ProjectEntry:
        resolved = path.resolve()
        data = self._load()
        existing = data["projects"].get(name)
        if existing is not None:
            existing_path = Path(existing["path"]).resolve()
            if existing_path == resolved:
                return ProjectEntry(name, existing_path, datetime.fromisoformat(existing["created_at"]))
            raise RegistryConflictError(
                f"Project '{name}' is already registered at {existing_path}, "
                f"which differs from the requested path {resolved}. "
                f"Use a different name, or 'videodoc unlink {name}' first."
            )
        created_at = datetime.now(timezone.utc)
        data["projects"][name] = {"path": resolved.as_posix(), "created_at": created_at.isoformat()}
        self._save(data)
        return ProjectEntry(name, resolved, created_at)

    def unlink(self, name: str) -> ProjectEntry:
        data = self._load()
        entry = data["projects"].pop(name, None)
        if entry is None:
            raise ProjectNotFoundError(f"No project named '{name}' is registered.")
        self._save(data)
        return ProjectEntry(name, Path(entry["path"]), datetime.fromisoformat(entry["created_at"]))

    def resolve(self, name: str) -> Path | None:
        entry = self._load()["projects"].get(name)
        return Path(entry["path"]) if entry else None

    def list_all(self) -> list[ProjectEntry]:
        data = self._load()["projects"]
        return sorted(
            (
                ProjectEntry(n, Path(v["path"]), datetime.fromisoformat(v["created_at"]))
                for n, v in data.items()
            ),
            key=lambda e: e.name,
        )
