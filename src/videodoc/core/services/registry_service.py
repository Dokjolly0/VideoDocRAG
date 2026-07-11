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
        self._last_load_was_corrupted = False

    @property
    def last_load_was_corrupted(self) -> bool:
        """True iff the most recent _load() call found a corrupted registry
        file and quarantined it (see _quarantine_corrupted_file), starting
        from an empty registry instead. Exists so callers like doctor's
        registry health check can report this without reimplementing
        registry.json parsing themselves."""
        return self._last_load_was_corrupted

    @property
    def registry_path(self) -> Path:
        """The actual registry.json path this instance reads/writes (either
        the explicit path passed to __init__, or default_path())."""
        return self._registry_path

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
        self._last_load_was_corrupted = False
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
        self._last_load_was_corrupted = True
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

    def _extract_path(self, name: str, raw: dict) -> Path | None:
        """Best-effort 'path' extraction for a single entry. Returns None
        (and logs) instead of raising, so one malformed entry never crashes
        commands that iterate the whole registry (list/resolve)."""
        path_raw = raw.get("path") if isinstance(raw, dict) else None
        if not isinstance(path_raw, str) or not path_raw:
            logger.warning("Registry entry '%s' has a missing or invalid 'path'; ignoring it.", name)
            return None
        return Path(path_raw)

    def _extract_created_at(self, name: str, raw: dict) -> datetime:
        """Best-effort 'created_at' extraction; falls back to now() instead
        of raising, since a bad timestamp shouldn't block using the entry."""
        created_raw = raw.get("created_at") if isinstance(raw, dict) else None
        try:
            return datetime.fromisoformat(created_raw)
        except (TypeError, ValueError):
            logger.warning(
                "Registry entry '%s' has a missing or invalid 'created_at'; using the current time instead.",
                name,
            )
            return datetime.now(timezone.utc)

    def register(self, name: str, path: Path) -> ProjectEntry:
        resolved = path.resolve()
        data = self._load()
        existing_raw = data["projects"].get(name)
        if existing_raw is not None:
            existing_path = self._extract_path(name, existing_raw)
            if existing_path is not None:
                existing_path = existing_path.resolve()
                if existing_path == resolved:
                    return ProjectEntry(name, existing_path, self._extract_created_at(name, existing_raw))
                raise RegistryConflictError(
                    f"Project '{name}' is already registered at {existing_path}, "
                    f"which differs from the requested path {resolved}. "
                    f"Use a different name, or 'videodoc unlink {name}' first."
                )
            # existing_raw is malformed (unusable 'path'): treat it as absent
            # and let this call heal the entry with a fresh, valid one.
        created_at = datetime.now(timezone.utc)
        data["projects"][name] = {"path": resolved.as_posix(), "created_at": created_at.isoformat()}
        self._save(data)
        return ProjectEntry(name, resolved, created_at)

    def unlink(self, name: str) -> ProjectEntry:
        data = self._load()
        raw = data["projects"].pop(name, None)
        if raw is None:
            raise ProjectNotFoundError(f"No project named '{name}' is registered.")
        self._save(data)
        # Removal above always succeeds regardless of whether raw is
        # well-formed (popping a dict key needs no parsing) -- unlink must
        # never be the thing that fails to clean up a malformed entry.
        path = self._extract_path(name, raw) or Path(str(raw.get("path")) if isinstance(raw, dict) else "<unknown>")
        return ProjectEntry(name, path, self._extract_created_at(name, raw))

    def resolve(self, name: str) -> Path | None:
        raw = self._load()["projects"].get(name)
        if raw is None:
            return None
        return self._extract_path(name, raw)

    def list_all(self) -> list[ProjectEntry]:
        data = self._load()["projects"]
        entries = []
        for n, raw in data.items():
            path = self._extract_path(n, raw)
            if path is None:
                continue
            entries.append(ProjectEntry(n, path, self._extract_created_at(n, raw)))
        return sorted(entries, key=lambda e: e.name)
