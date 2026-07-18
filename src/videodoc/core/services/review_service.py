from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DatabaseError, DocumentationReviewUnavailableError, InvalidDocumentationSectionManifestError
from videodoc.core.models.document_review import DocumentationReviewReport, ReviewIssue, ReviewedCodeBlock, ReviewedSection
from videodoc.core.models.document_section import GeneratedSectionManifest
from videodoc.core.models.vector_index import VectorIndex

_REQUIRED_HEADINGS = (
    "Obiettivo",
    "Fonti utilizzate",
    "Spiegazione dettagliata",
    "Procedura passo-passo",
    "Codice esaminato",
    "Spiegazione del codice",
    "Risultato atteso",
    "Errori comuni",
    "Riferimenti",
)
_CITATION_RE = re.compile(r"\[(\d+)\]")
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9_./:@#-]+")
_NARRATIVE_HEADINGS = {"Spiegazione dettagliata", "Procedura passo-passo", "Errori comuni"}
_PLACEHOLDER_PREFIXES = (
    "Da completare",
    "Le fonti recuperate non contengono",
    "Nessun errore specifico",
    "Nessuna fonte",
)
_MIN_TOKEN_OVERLAP = 0.12


@dataclass(frozen=True)
class ReviewResult:
    report_path: Path
    json_path: Path
    sections: int
    issues: int
    errors: int
    warnings: int


class DocumentationReviewService:
    def __init__(self, project_dir: Path, config: ProjectConfig) -> None:
        self.project_dir = project_dir
        self.config = config
        self.output_dir = self.project_dir / config.paths.output
        self.sources_dir = self.output_dir / "sources"
        self.report_path = self.output_dir / "review_report.md"
        self.json_path = self.output_dir / "review_report.json"
        self.index_path = self.project_dir / config.paths.indexes / "vector_index.json"

    def run(self) -> ReviewResult:
        section_paths = _generated_section_paths(self.output_dir)
        if not section_paths:
            raise DocumentationReviewUnavailableError(
                f"No generated Markdown sections found in {self.output_dir} -- run 'videodoc generate' first."
            )

        index_records = _load_index_records(self.index_path)
        reviewed_sections: list[ReviewedSection] = []
        issues: list[ReviewIssue] = []
        code_blocks: list[ReviewedCodeBlock] = []

        for section_path in section_paths:
            rel_section = section_path.relative_to(self.project_dir).as_posix()
            section_issues: list[ReviewIssue] = []
            manifest_path = self.sources_dir / f"{section_path.stem}.sources.json"
            manifest: GeneratedSectionManifest | None = None
            if not manifest_path.is_file():
                section_issues.append(_issue("error", "sources", rel_section, f"Missing source manifest {manifest_path}."))
            else:
                try:
                    manifest = GeneratedSectionManifest.load(manifest_path)
                except InvalidDocumentationSectionManifestError as exc:
                    section_issues.append(_issue("error", "sources", rel_section, str(exc)))

            try:
                markdown = section_path.read_text(encoding="utf-8")
            except OSError as exc:
                section_issues.append(_issue("error", "markdown", rel_section, f"Cannot read section: {exc}"))
                markdown = ""

            section_issues.extend(_review_markdown_structure(rel_section, markdown))
            if manifest is not None:
                section_issues.extend(_review_sources(rel_section, markdown, manifest, index_records))
                block_reviews, block_issues = _review_code_blocks(rel_section, markdown, manifest)
                code_blocks.extend(block_reviews)
                section_issues.extend(block_issues)

            issues.extend(section_issues)
            reviewed_sections.append(
                ReviewedSection(
                    path=rel_section,
                    source_manifest_path=manifest_path.relative_to(self.project_dir).as_posix() if manifest_path.is_file() else None,
                    issue_count=len(section_issues),
                )
            )

        report = DocumentationReviewReport(sections=reviewed_sections, issues=issues, code_blocks=code_blocks)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        _write_atomic(self.json_path, report.to_json() + "\n")
        _write_atomic(self.report_path, _render_report(report))
        return ReviewResult(
            report_path=self.report_path,
            json_path=self.json_path,
            sections=len(reviewed_sections),
            issues=len(issues),
            errors=sum(1 for issue in issues if issue.severity == "error"),
            warnings=sum(1 for issue in issues if issue.severity == "warning"),
        )


def _generated_section_paths(output_dir: Path) -> list[Path]:
    if not output_dir.is_dir():
        return []
    return sorted(
        path for path in output_dir.glob("[0-9][0-9]-*.md")
        if path.name not in {"review_report.md", "outline.md"}
    )


def _load_index_records(index_path: Path) -> dict[str, str]:
    if not index_path.is_file():
        return {}
    index = VectorIndex.load(index_path)
    return {record.id: str(record.payload.get("text", "")) for record in index.records}


def _review_markdown_structure(section_path: str, markdown: str) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    if markdown.count("```") % 2 != 0:
        issues.append(_issue("error", "markdown", section_path, "Unbalanced fenced code blocks."))
    h1_count = sum(1 for line in markdown.splitlines() if line.startswith("# "))
    if h1_count != 1:
        issues.append(_issue("error", "markdown", section_path, f"Expected exactly one H1, found {h1_count}."))

    sections = _h2_sections(markdown)
    for heading in _REQUIRED_HEADINGS:
        if heading not in sections:
            issues.append(_issue("warning", "markdown", section_path, f"Missing required heading '## {heading}'."))
        elif not _section_has_content(sections[heading]):
            issues.append(_issue("warning", "empty_section", section_path, f"Section '## {heading}' is empty."))

    duplicate_blocks = _duplicate_code_blocks(markdown)
    for block in duplicate_blocks:
        issues.append(_issue("warning", "duplicate_code", section_path, f"Duplicate code block detected: {block[:80]}"))
    return issues


def _review_sources(
    section_path: str,
    markdown: str,
    manifest: GeneratedSectionManifest,
    index_records: dict[str, str],
) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    if manifest.sources and not index_records:
        issues.append(_issue("warning", "sources", section_path, "Vector index unavailable; anti-hallucination overlap checks were limited."))

    cited_ranks = {int(match.group(1)) for match in _CITATION_RE.finditer(markdown)}
    valid_ranks = {source.rank for source in manifest.sources}
    for rank in sorted(cited_ranks - valid_ranks):
        issues.append(_issue("error", "sources", section_path, f"Citation [{rank}] has no matching source manifest entry."))

    for source in manifest.sources:
        if source.video_name and source.video_name not in markdown:
            issues.append(_issue("error", "video_reference", section_path, f"Missing video reference '{source.video_name}' for source [{source.rank}]."))
        expected_time = _time_range(source.start_seconds, source.end_seconds)
        if expected_time and expected_time not in markdown:
            issues.append(_issue("error", "timestamp", section_path, f"Missing timestamp {expected_time} for source [{source.rank}]."))

    issues.extend(_review_supported_claims(section_path, markdown, manifest, index_records))
    return issues


def _review_supported_claims(
    section_path: str,
    markdown: str,
    manifest: GeneratedSectionManifest,
    index_records: dict[str, str],
) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    source_by_rank = {source.rank: source for source in manifest.sources}
    for heading, line in _narrative_lines(markdown):
        citations = [int(match.group(1)) for match in _CITATION_RE.finditer(line)]
        if not citations:
            issues.append(_issue("warning", "anti_hallucination", section_path, f"Uncited claim under '{heading}': {line[:120]}"))
            continue
        if not index_records:
            continue
        line_tokens = _tokens(line)
        for rank in citations:
            source = source_by_rank.get(rank)
            if source is None:
                continue
            source_tokens = _tokens(index_records.get(source.record_id, ""))
            if source_tokens and line_tokens:
                overlap = len(line_tokens & source_tokens) / max(len(line_tokens), 1)
                if overlap < _MIN_TOKEN_OVERLAP:
                    issues.append(
                        _issue(
                            "warning",
                            "anti_hallucination",
                            section_path,
                            f"Low lexical overlap between claim and source [{rank}]: {line[:120]}",
                        )
                    )
    return issues


def _review_code_blocks(
    section_path: str,
    markdown: str,
    manifest: GeneratedSectionManifest,
) -> tuple[list[ReviewedCodeBlock], list[ReviewIssue]]:
    issues: list[ReviewIssue] = []
    reviews: list[ReviewedCodeBlock] = []
    fenced_blocks = _fenced_code_blocks(markdown)
    if manifest.code_blocks and len(fenced_blocks) < len(manifest.code_blocks):
        issues.append(
            _issue(
                "error",
                "code",
                section_path,
                f"Manifest lists {len(manifest.code_blocks)} code block(s), but Markdown contains {len(fenced_blocks)} fenced block(s).",
            )
        )

    for block in manifest.code_blocks:
        classification = _classify_code(block.verified, block.confidence)
        reviews.append(
            ReviewedCodeBlock(
                id=block.id,
                section_path=section_path,
                classification=classification,
                confidence=block.confidence,
                verified=block.verified,
            )
        )
        if classification == "needs_review":
            issues.append(_issue("warning", "code", section_path, f"Code block {block.id} requires review."))
    return reviews, issues


def _classify_code(verified: bool, confidence: float | None) -> str:
    if verified:
        return "verified"
    if confidence is not None and confidence >= 0.90:
        return "high_confidence"
    if confidence is not None and confidence >= 0.80:
        return "ocr_extracted"
    return "needs_review"


def _h2_sections(markdown: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in markdown.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections


def _section_has_content(lines: list[str]) -> bool:
    return any(line.strip() and not line.strip().startswith("<!--") for line in lines)


def _narrative_lines(markdown: str) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    current_heading: str | None = None
    in_code = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if stripped.startswith("## "):
            current_heading = stripped[3:]
            continue
        if current_heading not in _NARRATIVE_HEADINGS:
            continue
        if not stripped or stripped.startswith("#") or any(stripped.startswith(prefix) for prefix in _PLACEHOLDER_PREFIXES):
            continue
        normalized = stripped.lstrip("- ").lstrip("0123456789. ")
        if normalized:
            results.append((current_heading, normalized))
    return results


def _duplicate_code_blocks(markdown: str) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for block in _fenced_code_blocks(markdown):
        normalized = "\n".join(line.rstrip() for line in block.strip().splitlines()).strip()
        if not normalized:
            continue
        if normalized in seen:
            duplicates.append(normalized)
        seen.add(normalized)
    return duplicates


def _fenced_code_blocks(markdown: str) -> list[str]:
    blocks: list[str] = []
    in_code = False
    current: list[str] = []
    for line in markdown.splitlines():
        if line.strip().startswith("```"):
            if in_code:
                blocks.append("\n".join(current))
                current = []
            in_code = not in_code
            continue
        if in_code:
            current.append(line)
    return blocks


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(text) if len(token) > 2}


def _time_range(start_seconds: float | None, end_seconds: float | None) -> str:
    if start_seconds is None and end_seconds is None:
        return ""
    if end_seconds is None:
        return f"@{_format_seconds(start_seconds or 0.0)}"
    return f"{_format_seconds(start_seconds or 0.0)}-{_format_seconds(end_seconds)}"


def _format_seconds(value: float) -> str:
    total = max(0, int(round(value)))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _render_report(report: DocumentationReviewReport) -> str:
    lines = [
        "# Documentation Review Report",
        "",
        f"Sections reviewed: {len(report.sections)}",
        f"Issues found: {len(report.issues)}",
        "",
        "## Issues",
        "",
    ]
    if report.issues:
        for issue in report.issues:
            lines.append(f"- [{issue.severity}] `{issue.section_path}` — {issue.check}: {issue.message}")
    else:
        lines.append("- No issues found.")

    lines.extend(["", "## Code Classification", ""])
    if report.code_blocks:
        for block in report.code_blocks:
            confidence = f", confidence={block.confidence:.2f}" if block.confidence is not None else ""
            lines.append(f"- `{block.id}` in `{block.section_path}`: {block.classification}{confidence}")
    else:
        lines.append("- No code blocks reviewed.")

    lines.extend(["", "## Sections", ""])
    for section in report.sections:
        lines.append(f"- `{section.path}`: {section.issue_count} issue(s)")
    return "\n".join(lines).rstrip() + "\n"


def _issue(severity: str, check: str, section_path: str, message: str) -> ReviewIssue:
    return ReviewIssue(severity=severity, check=check, section_path=section_path, message=message)


def _write_atomic(path: Path, text: str) -> None:
    tmp_path = path.parent / f"{path.name}.tmp"
    try:
        tmp_path.write_text(text, encoding="utf-8")
        tmp_path.replace(path)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise DatabaseError(f"Cannot write documentation review report at {path}: {exc}") from exc
