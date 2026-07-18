from __future__ import annotations

import html
import shutil
from dataclasses import dataclass
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DatabaseError, DocumentationExportFormatError, DocumentationExportUnavailableError

SUPPORTED_EXPORT_FORMATS = ("markdown", "mkdocs", "docusaurus", "github-pages", "pdf", "html")


@dataclass(frozen=True)
class ExportResult:
    format: str
    output_path: Path
    files: tuple[Path, ...]


class DocumentationExportService:
    def __init__(self, project_dir: Path, config: ProjectConfig) -> None:
        self.project_dir = project_dir
        self.config = config
        self.docs_dir = self.project_dir / config.paths.output
        self.exports_dir = self.project_dir / "exports"

    def run(self, export_format: str = "markdown") -> ExportResult:
        normalized = export_format.lower()
        if normalized not in SUPPORTED_EXPORT_FORMATS:
            raise DocumentationExportFormatError(
                f"Export format '{export_format}' is not supported -- choose one of: "
                f"{', '.join(SUPPORTED_EXPORT_FORMATS)}."
            )

        docs = _collect_docs(self.docs_dir)
        if not docs.sections:
            raise DocumentationExportUnavailableError(
                f"No generated Markdown sections found in {self.docs_dir} -- run 'videodoc generate' first."
            )

        if normalized == "markdown":
            return self._export_markdown(docs)
        if normalized == "mkdocs":
            return self._export_mkdocs(docs)
        if normalized == "docusaurus":
            return self._export_docusaurus(docs)
        if normalized == "github-pages":
            return self._export_html_site(docs, normalized, github_pages=True)
        if normalized == "html":
            return self._export_html_site(docs, normalized, github_pages=False)
        return self._export_pdf(docs)

    def _export_markdown(self, docs: "_Docs") -> ExportResult:
        target = self.exports_dir / "markdown"
        files: list[Path] = []
        for path in docs.markdown_files:
            relative = path.relative_to(self.docs_dir)
            destination = target / relative
            _copy_file(path, destination)
            files.append(destination)
        return ExportResult("markdown", target, tuple(files))

    def _export_mkdocs(self, docs: "_Docs") -> ExportResult:
        target = self.exports_dir / "mkdocs"
        docs_target = target / "docs"
        files: list[Path] = []
        index_path = docs_target / "index.md"
        _write_text(index_path, _markdown_index(self.config.project.name, docs.sections))
        files.append(index_path)
        for path in docs.sections:
            destination = docs_target / path.name
            _copy_file(path, destination)
            files.append(destination)
        config_path = target / "mkdocs.yml"
        _write_text(config_path, _mkdocs_yml(self.config.project.name, docs.sections))
        files.append(config_path)
        return ExportResult("mkdocs", target, tuple(files))

    def _export_docusaurus(self, docs: "_Docs") -> ExportResult:
        target = self.exports_dir / "docusaurus"
        docs_target = target / "docs"
        files: list[Path] = []
        intro_path = docs_target / "intro.md"
        _write_text(intro_path, _markdown_index(self.config.project.name, docs.sections))
        files.append(intro_path)
        for path in docs.sections:
            destination = docs_target / path.name
            _copy_file(path, destination)
            files.append(destination)
        sidebars = target / "sidebars.js"
        _write_text(sidebars, _docusaurus_sidebars(docs.sections))
        files.append(sidebars)
        config_path = target / "docusaurus.config.js"
        _write_text(config_path, _docusaurus_config(self.config.project.name))
        files.append(config_path)
        return ExportResult("docusaurus", target, tuple(files))

    def _export_html_site(self, docs: "_Docs", export_format: str, *, github_pages: bool) -> ExportResult:
        target = self.exports_dir / export_format
        files: list[Path] = []
        index_path = target / "index.html"
        _write_text(index_path, _html_index(self.config.project.name, docs.sections))
        files.append(index_path)
        for path in docs.sections:
            destination = target / f"{path.stem}.html"
            _write_text(destination, _html_page(_title_from_markdown(path), path.read_text(encoding="utf-8")))
            files.append(destination)
        if github_pages:
            nojekyll = target / ".nojekyll"
            _write_text(nojekyll, "")
            files.append(nojekyll)
        return ExportResult(export_format, target, tuple(files))

    def _export_pdf(self, docs: "_Docs") -> ExportResult:
        target = self.exports_dir / "pdf"
        pdf_path = target / "documentation.pdf"
        content = "\n\n".join(path.read_text(encoding="utf-8") for path in docs.sections)
        _write_bytes(pdf_path, _simple_pdf_bytes(self.config.project.name, content))
        return ExportResult("pdf", target, (pdf_path,))


@dataclass(frozen=True)
class _Docs:
    sections: tuple[Path, ...]
    markdown_files: tuple[Path, ...]


def _collect_docs(docs_dir: Path) -> _Docs:
    if not docs_dir.is_dir():
        return _Docs((), ())
    sections = tuple(sorted(docs_dir.glob("[0-9][0-9]-*.md")))
    extras = [
        docs_dir / name for name in ("outline.md", "review_report.md")
        if (docs_dir / name).is_file()
    ]
    markdown_files = tuple([*extras, *sections])
    return _Docs(sections=sections, markdown_files=markdown_files)


def _copy_file(source: Path, destination: Path) -> None:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    except OSError as exc:
        raise DatabaseError(f"Cannot export {source} to {destination}: {exc}") from exc


def _write_text(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise DatabaseError(f"Cannot write export file {path}: {exc}") from exc


def _write_bytes(path: Path, data: bytes) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError as exc:
        raise DatabaseError(f"Cannot write export file {path}: {exc}") from exc


def _markdown_index(project_name: str, sections: tuple[Path, ...]) -> str:
    lines = [f"# {project_name}", "", "## Sezioni", ""]
    for section in sections:
        lines.append(f"- [{_title_from_markdown(section)}]({section.name})")
    return "\n".join(lines).rstrip() + "\n"


def _mkdocs_yml(project_name: str, sections: tuple[Path, ...]) -> str:
    lines = [
        f"site_name: {project_name}",
        "site_description: Documentazione generata dai workshop video",
        "theme:",
        "  name: material",
        "nav:",
        "  - Home: index.md",
    ]
    for section in sections:
        lines.append(f"  - {_title_from_markdown(section)}: {section.name}")
    return "\n".join(lines) + "\n"


def _docusaurus_sidebars(sections: tuple[Path, ...]) -> str:
    docs = ["intro", *(section.stem for section in sections)]
    quoted = ", ".join(f"'{item}'" for item in docs)
    return f"module.exports = {{ tutorialSidebar: [{quoted}] }};\n"


def _docusaurus_config(project_name: str) -> str:
    escaped = project_name.replace("\\", "\\\\").replace("'", "\\'")
    return (
        "module.exports = {\n"
        f"  title: '{escaped}',\n"
        "  tagline: 'Documentazione generata dai workshop video',\n"
        "  url: 'https://example.com',\n"
        "  baseUrl: '/',\n"
        "  onBrokenLinks: 'throw',\n"
        "  onBrokenMarkdownLinks: 'warn',\n"
        "  presets: [['classic', { docs: { sidebarPath: require.resolve('./sidebars.js') } }]],\n"
        "};\n"
    )


def _html_index(project_name: str, sections: tuple[Path, ...]) -> str:
    items = "\n".join(
        f'<li><a href="{html.escape(section.stem)}.html">{html.escape(_title_from_markdown(section))}</a></li>'
        for section in sections
    )
    return _html_shell(project_name, f"<h1>{html.escape(project_name)}</h1>\n<ul>\n{items}\n</ul>")


def _html_page(title: str, markdown: str) -> str:
    return _html_shell(title, _markdown_to_html(markdown))


def _html_shell(title: str, body: str) -> str:
    safe_title = html.escape(title)
    return (
        "<!doctype html>\n"
        "<html lang=\"it\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"  <title>{safe_title}</title>\n"
        "  <style>body{font-family:system-ui,sans-serif;max-width:920px;margin:40px auto;padding:0 20px;line-height:1.55}"
        "pre{background:#f4f4f4;padding:12px;overflow:auto}code{font-family:ui-monospace,Consolas,monospace}</style>\n"
        "</head>\n"
        f"<body>\n{body}\n</body>\n"
        "</html>\n"
    )


def _markdown_to_html(markdown: str) -> str:
    lines: list[str] = []
    in_code = False
    code_lines: list[str] = []
    in_list = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            if in_code:
                lines.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
                code_lines = []
                in_code = False
            else:
                if in_list:
                    lines.append("</ul>")
                    in_list = False
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not line.strip():
            if in_list:
                lines.append("</ul>")
                in_list = False
            continue
        if line.startswith("#"):
            if in_list:
                lines.append("</ul>")
                in_list = False
            level = min(len(line) - len(line.lstrip("#")), 6)
            text = line[level:].strip()
            lines.append(f"<h{level}>{html.escape(text)}</h{level}>")
        elif line.startswith("- "):
            if not in_list:
                lines.append("<ul>")
                in_list = True
            lines.append(f"<li>{html.escape(line[2:])}</li>")
        else:
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<p>{html.escape(line)}</p>")
    if in_code:
        lines.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
    if in_list:
        lines.append("</ul>")
    return "\n".join(lines)


def _title_from_markdown(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        pass
    return path.stem


def _simple_pdf_bytes(project_name: str, markdown: str) -> bytes:
    lines = [project_name, "", *markdown.splitlines()]
    wrapped = _wrap_pdf_lines(lines)
    pages = [wrapped[index:index + 54] for index in range(0, len(wrapped), 54)] or [[""]]

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids_ids = [4 + index * 2 for index in range(len(pages))]
    kids = " ".join(f"{obj_id} 0 R" for obj_id in kids_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, page_lines in enumerate(pages):
        page_obj_id = 4 + index * 2
        content_obj_id = page_obj_id + 1
        stream = _pdf_content_stream(page_lines)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj_id} 0 R >>".encode("ascii")
        )
        objects.append(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")

    content = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj_id, obj in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{obj_id} 0 obj\n".encode("ascii"))
        content.extend(obj)
        content.extend(b"\nendobj\n")
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    content.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(content)


def _wrap_pdf_lines(lines: list[str]) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        clean = " ".join(line.replace("\t", "    ").split())
        if not clean:
            wrapped.append("")
            continue
        while len(clean) > 88:
            wrapped.append(clean[:88])
            clean = clean[88:]
        wrapped.append(clean)
    return wrapped


def _pdf_content_stream(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 10 Tf", "50 760 Td", "14 TL"]
    for line in lines:
        commands.append(f"({_pdf_escape(line)}) Tj")
        commands.append("T*")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1", errors="replace")


def _pdf_escape(text: str) -> str:
    encoded = text.encode("latin-1", errors="replace").decode("latin-1")
    return encoded.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
