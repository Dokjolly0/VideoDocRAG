from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import (
    InvalidConfigError,
    InvalidProjectNameError,
    ProjectNotFoundError,
    RegistryConflictError,
)
from videodoc.core.services.registry_service import ProjectRegistry
from videodoc.core.storage import filesystem
from videodoc.core.utils.slug import slugify

HOME_ENV_VAR = "VIDEODOC_HOME"


def default_projects_home() -> Path:
    override = os.environ.get(HOME_ENV_VAR)
    if override:
        return Path(override)
    return Path.home() / "VideoDocRAG" / "projects"


def _safe_slugify(name: str) -> str:
    try:
        return slugify(name)
    except ValueError as exc:
        raise InvalidProjectNameError(str(exc)) from exc


@dataclass(frozen=True)
class ProjectInitResult:
    name: str
    project_dir: Path
    config_path: Path
    created: bool  # False if config.yaml already existed (idempotent rerun)


class ProjectService:
    def __init__(self, project_dir: Path, config: ProjectConfig) -> None:
        self.project_dir = project_dir
        self.config = config

    @classmethod
    def init(
        cls,
        name: str,
        *,
        path: Path | None = None,
        registry: ProjectRegistry | None = None,
        language: str = "it",
    ) -> ProjectInitResult:
        slug = _safe_slugify(name)
        target_dir = (path if path is not None else default_projects_home() / slug).resolve()
        registry = registry or ProjectRegistry()

        # 1. Check for conflicts BEFORE touching the filesystem (fail-fast).
        existing = registry.resolve(name)
        if existing is not None and existing.resolve() != target_dir:
            raise RegistryConflictError(
                f"Project '{name}' is already registered at {existing}, "
                f"which differs from the requested path {target_dir}."
            )

        # 2. Folder structure (idempotent).
        filesystem.ensure_project_structure(target_dir)
        filesystem.ensure_sources_yaml(target_dir)

        # 3. config.yaml: create only if missing, otherwise validate the existing one.
        config_path = target_dir / "config.yaml"
        if config_path.exists():
            config = ProjectConfig.load(config_path)  # raises InvalidConfigError if corrupted
            created = False
        else:
            config = ProjectConfig.default(name=name, slug=slug, language=language)
            config.save(config_path)
            created = True

        # 4. Registration (idempotent by construction of ProjectRegistry.register).
        registry.register(name, target_dir)
        return ProjectInitResult(name=name, project_dir=target_dir, config_path=config_path, created=created)

    @classmethod
    def load(cls, reference: str, *, registry: ProjectRegistry | None = None) -> "ProjectService":
        # (a) an existing path with a valid config.yaml -> use it directly, even if unregistered
        candidate = Path(reference)
        config_path = candidate / "config.yaml"
        if candidate.exists() and config_path.is_file():
            return cls(candidate.resolve(), ProjectConfig.load(config_path))

        # (b) a name in the registry
        registry = registry or ProjectRegistry()
        resolved = registry.resolve(reference)
        if resolved is not None:
            resolved_config = resolved / "config.yaml"
            if not resolved_config.is_file():
                raise ProjectNotFoundError(
                    f"Project '{reference}' is registered at {resolved}, but no config.yaml was found there."
                )
            return cls(resolved, ProjectConfig.load(resolved_config))

        # (c) clear error
        raise ProjectNotFoundError(
            f"Project '{reference}' was not found as a path or as a registered name. "
            f"Run 'videodoc list' to see registered projects."
        )

    @classmethod
    def link(
        cls, path: Path, *, name: str | None = None, registry: ProjectRegistry | None = None
    ) -> ProjectInitResult:
        resolved = path.resolve()
        config_path = resolved / "config.yaml"
        if not config_path.is_file():
            raise InvalidConfigError(f"No config.yaml found at {resolved}; not a valid VideoDocRAG project.")
        config = ProjectConfig.load(config_path)
        reg_name = name or config.project.slug
        registry = registry or ProjectRegistry()
        registry.register(reg_name, resolved)
        return ProjectInitResult(name=reg_name, project_dir=resolved, config_path=config_path, created=False)
