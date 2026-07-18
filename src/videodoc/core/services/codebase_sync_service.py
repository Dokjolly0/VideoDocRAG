from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import InvalidCodebaseManifestError
from videodoc.core.models.codebase_manifest import CodebaseFileEntry, CodebaseSnippet, CodebaseSyncManifest
from videodoc.core.models.vector_index import VectorIndex, VectorIndexInputSignature, VectorIndexRecord
from videodoc.core.storage import filesystem
from videodoc.core.utils.embedding import HASHING_EMBEDDING_BACKEND, HASHING_EMBEDDING_DIMENSIONS, embed_text_hashing, text_hash
from videodoc.core.utils.hashing import hash_file
from videodoc.core.utils.slug import slugify
from videodoc.core.utils.vector_index import LOCAL_VECTOR_INDEX_BACKEND, VECTOR_INDEX_DISTANCE, stable_json_hash

_FALLBACK_CHUNK_LINES = 80
_LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
}


@dataclass(frozen=True)
class CodebaseSyncResult:
    synced: bool
    skipped: bool
    files: int
    snippets: int
    added: int
    modified: int
    removed: int
    errors: tuple[str, ...]
    manifest_path: Path
    index_path: Path


@dataclass(frozen=True)
class _ScannedFile:
    path: Path
    relative_path: str
    file_hash: str
    size_bytes: int
    text: str


class CodebaseSyncService:
    def __init__(self, project_dir: Path, config: ProjectConfig) -> None:
        self.project_dir = project_dir
        self.config = config
        self.indexes_dir = self.project_dir / config.paths.indexes
        self.manifest_path = self.indexes_dir / "codebase_manifest.json"
        self.index_path = self.indexes_dir / "codebase_index.json"

    def run(self) -> CodebaseSyncResult:
        errors: list[str] = []
        previous = self._load_previous(errors)
        root = self._resolve_codebase_root()
        present = filesystem.codebase_is_present(root, errors)
        file_paths = filesystem.scan_codebase(root, self.config.scan, errors) if present else []
        scanned_files = self._read_files(root, file_paths, errors)
        settings_hash = self._settings_hash()
        added, modified, removed = _change_counts(previous, scanned_files)

        if not present and previous is None:
            return CodebaseSyncResult(
                synced=False,
                skipped=True,
                files=0,
                snippets=0,
                added=0,
                modified=0,
                removed=0,
                errors=tuple(errors),
                manifest_path=self.manifest_path,
                index_path=self.index_path,
            )

        if (
            previous is not None
            and self.index_path.is_file()
            and previous.settings_hash == settings_hash
            and added == 0
            and modified == 0
            and removed == 0
            and not errors
        ):
            return CodebaseSyncResult(
                synced=False,
                skipped=True,
                files=len(previous.files),
                snippets=len(previous.snippets),
                added=0,
                modified=0,
                removed=0,
                errors=(),
                manifest_path=self.manifest_path,
                index_path=self.index_path,
            )

        manifest = self._build_manifest(root, scanned_files, settings_hash, errors)
        index = _build_index(manifest, self.config)
        self.indexes_dir.mkdir(parents=True, exist_ok=True)
        _save_manifest_atomic(manifest, self.manifest_path)
        _save_index_atomic(index, self.index_path)
        return CodebaseSyncResult(
            synced=True,
            skipped=False,
            files=len(manifest.files),
            snippets=len(manifest.snippets),
            added=added,
            modified=modified,
            removed=removed,
            errors=tuple(errors),
            manifest_path=self.manifest_path,
            index_path=self.index_path,
        )

    def _resolve_codebase_root(self) -> Path:
        return filesystem.resolve_source_path(self.project_dir, self.config.paths.codebase)

    def _load_previous(self, errors: list[str]) -> CodebaseSyncManifest | None:
        if not self.manifest_path.is_file():
            return None
        try:
            return CodebaseSyncManifest.load(self.manifest_path)
        except InvalidCodebaseManifestError as exc:
            errors.append(f"previous codebase manifest could not be read and will be rebuilt: {exc}")
            return None

    def _read_files(self, root: Path, paths: list[Path], errors: list[str]) -> list[_ScannedFile]:
        scanned: list[_ScannedFile] = []
        for path in paths:
            try:
                relative_path = path.relative_to(root).as_posix()
            except ValueError:
                relative_path = path.name
            try:
                file_hash = hash_file(path)
                size_bytes = path.stat().st_size
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                errors.append(f"{relative_path}: {exc}")
                continue
            scanned.append(_ScannedFile(path, relative_path, file_hash, size_bytes, text))
        return scanned

    def _settings_hash(self) -> str:
        scan = self.config.scan
        return stable_json_hash(
            {
                "default_excludes": scan.default_excludes,
                "add_excludes": sorted(scan.add_excludes),
                "remove_excludes": sorted(scan.remove_excludes),
                "max_file_size_mb": scan.max_file_size_mb,
                "follow_symlinks": scan.follow_symlinks,
                "allowed_code_extensions": sorted(scan.allowed_code_extensions),
                "embedding_provider": self.config.embedding.provider,
                "embedding_model": self.config.embedding.model,
                "dimensions": HASHING_EMBEDDING_DIMENSIONS,
            }
        )

    def _build_manifest(
        self,
        root: Path,
        scanned_files: list[_ScannedFile],
        settings_hash: str,
        errors: list[str],
    ) -> CodebaseSyncManifest:
        files: list[CodebaseFileEntry] = []
        snippets: list[CodebaseSnippet] = []
        for scanned_file in sorted(scanned_files, key=lambda item: item.relative_path):
            file_snippets = _snippets_for_file(scanned_file, self.config.project.slug)
            snippets.extend(file_snippets)
            files.append(
                CodebaseFileEntry(
                    path=scanned_file.relative_path,
                    file_hash=scanned_file.file_hash,
                    size_bytes=scanned_file.size_bytes,
                    snippet_count=len(file_snippets),
                )
            )
        return CodebaseSyncManifest(
            project_id=self.config.project.slug,
            codebase_root=root.as_posix(),
            synced_at=datetime.now(timezone.utc).isoformat(),
            settings_hash=settings_hash,
            files=files,
            snippets=snippets,
            scan_errors=errors,
        )


def _snippets_for_file(scanned_file: _ScannedFile, project_id: str) -> list[CodebaseSnippet]:
    lines = scanned_file.text.splitlines()
    if not lines:
        return []
    ranges = _python_symbol_ranges(scanned_file) if scanned_file.path.suffix.lower() == ".py" else []
    if not ranges:
        ranges = _line_chunks(lines)
    snippets = []
    language = _LANGUAGE_BY_SUFFIX.get(scanned_file.path.suffix.lower(), scanned_file.path.suffix.lower().lstrip(".") or None)
    for index, (start_line, end_line, symbol_name) in enumerate(ranges, start=1):
        content = "\n".join(lines[start_line - 1:end_line]).strip()
        if not content:
            continue
        link = f"codebase/{scanned_file.relative_path}#L{start_line}-L{end_line}"
        snippets.append(
            CodebaseSnippet(
                id=_snippet_id(scanned_file.relative_path, start_line, end_line, index),
                project_id=project_id,
                file_path=scanned_file.relative_path,
                language=language,
                start_line=start_line,
                end_line=end_line,
                symbol_name=symbol_name,
                content=content,
                file_hash=scanned_file.file_hash,
                metadata={"indexed_from": "codebase", "link": link},
            )
        )
    return snippets


def _python_symbol_ranges(scanned_file: _ScannedFile) -> list[tuple[int, int, str | None]]:
    try:
        tree = ast.parse(scanned_file.text)
    except SyntaxError:
        return []
    ranges = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            end_line = getattr(node, "end_lineno", None)
            if end_line is not None:
                ranges.append((node.lineno, end_line, node.name))
    return sorted(ranges)


def _line_chunks(lines: list[str]) -> list[tuple[int, int, str | None]]:
    chunks = []
    start = 1
    while start <= len(lines):
        end = min(len(lines), start + _FALLBACK_CHUNK_LINES - 1)
        if any(line.strip() for line in lines[start - 1:end]):
            chunks.append((start, end, None))
        start = end + 1
    return chunks


def _snippet_id(relative_path: str, start_line: int, end_line: int, index: int) -> str:
    try:
        base = slugify(relative_path)
    except ValueError:
        base = "file"
    digest = text_hash(f"{relative_path}:{start_line}:{end_line}")[:10]
    return f"codebase_{base}_{index:04d}_{digest}"


def _change_counts(previous: CodebaseSyncManifest | None, scanned_files: list[_ScannedFile]) -> tuple[int, int, int]:
    previous_hashes = {entry.path: entry.file_hash for entry in previous.files} if previous is not None else {}
    current_hashes = {entry.relative_path: entry.file_hash for entry in scanned_files}
    added = sum(1 for path in current_hashes if path not in previous_hashes)
    modified = sum(1 for path, file_hash in current_hashes.items() if path in previous_hashes and previous_hashes[path] != file_hash)
    removed = sum(1 for path in previous_hashes if path not in current_hashes)
    return added, modified, removed


def _build_index(manifest: CodebaseSyncManifest, config: ProjectConfig) -> VectorIndex:
    signatures = [
        {
            "id": snippet.id,
            "file_path": snippet.file_path,
            "file_hash": snippet.file_hash,
            "start_line": snippet.start_line,
            "end_line": snippet.end_line,
            "content_hash": text_hash(snippet.content),
        }
        for snippet in manifest.snippets
    ]
    records = [
        VectorIndexRecord(
            id=snippet.id,
            vector=embed_text_hashing(_index_text(snippet), dimensions=HASHING_EMBEDDING_DIMENSIONS),
            payload={
                "project_id": manifest.project_id,
                "source_type": "codebase",
                "chunk_id": snippet.id,
                "embedding_type": "codebase",
                "text": _index_text(snippet),
                "doc_path": str(snippet.metadata.get("link") or ""),
                "section_title": snippet.symbol_name or snippet.file_path,
                "file_path": snippet.file_path,
                "language": snippet.language,
                "start_line": snippet.start_line,
                "end_line": snippet.end_line,
                "symbol_name": snippet.symbol_name,
                "file_hash": snippet.file_hash,
            },
        )
        for snippet in manifest.snippets
    ]
    return VectorIndex(
        backend=LOCAL_VECTOR_INDEX_BACKEND,
        configured_vector_db="codebase",
        distance=VECTOR_INDEX_DISTANCE,
        dimensions=HASHING_EMBEDDING_DIMENSIONS,
        inputs=[
            VectorIndexInputSignature(
                video_id="codebase",
                backend=HASHING_EMBEDDING_BACKEND,
                provider=config.embedding.provider,
                model=config.embedding.model,
                dimensions=HASHING_EMBEDDING_DIMENSIONS,
                records_hash=stable_json_hash(signatures),
            )
        ],
        records=records,
    )


def _index_text(snippet: CodebaseSnippet) -> str:
    parts = [
        f"Codebase file: {snippet.file_path}",
        f"Lines: {snippet.start_line}-{snippet.end_line}",
        f"Language: {snippet.language or 'text'}",
    ]
    if snippet.symbol_name:
        parts.append(f"Symbol: {snippet.symbol_name}")
    parts.extend(["", snippet.content])
    return "\n".join(parts)


def _save_manifest_atomic(manifest: CodebaseSyncManifest, path: Path) -> None:
    tmp_path = path.parent / f"{path.name}.tmp"
    try:
        manifest.save(tmp_path)
        tmp_path.replace(path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


def _save_index_atomic(index: VectorIndex, path: Path) -> None:
    tmp_path = path.parent / f"{path.name}.tmp"
    try:
        index.save(tmp_path)
        tmp_path.replace(path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise
