from __future__ import annotations

from pathlib import Path

# Order matches the "expected output" tree in README §14 (project.db excluded:
# it is created later, during ingestion, once a schema is actually needed).
PROJECT_SUBDIRS = ("videos", "attachments", "codebase", "workdir", "indexes", "sessions", "docs")


def ensure_project_structure(project_dir: Path) -> None:
    """Create project_dir and all standard subfolders. Idempotent: never
    errors if folders already exist, never touches existing files."""
    project_dir.mkdir(parents=True, exist_ok=True)
    for sub in PROJECT_SUBDIRS:
        (project_dir / sub).mkdir(parents=True, exist_ok=True)


def ensure_sources_yaml(project_dir: Path) -> Path:
    """Create an empty placeholder sources.yaml only if it doesn't exist yet;
    never overwrites an existing file. The real schema for sources.yaml will
    be defined by the 'scan' step (README §15.1) — not anticipated here."""
    path = project_dir / "sources.yaml"
    if not path.exists():
        path.write_text("# Populated by 'videodoc scan'\n", encoding="utf-8")
    return path
