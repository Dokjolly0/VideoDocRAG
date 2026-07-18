from __future__ import annotations

import ast
import hashlib
import json
import re
import textwrap
from dataclasses import dataclass
from typing import Literal

import yaml

ContentType = Literal[
    "plain_text",
    "terminal_command",
    "source_code",
    "configuration",
    "error_message",
    "file_path",
    "ui_label",
]

ValidationStatus = Literal["valid", "invalid", "not_applicable"]

CODE_REVIEW_CONFIDENCE_THRESHOLD = 0.80

_SHELL_COMMANDS = {
    "apt",
    "brew",
    "cargo",
    "cd",
    "cmake",
    "conda",
    "copy",
    "cp",
    "curl",
    "docker",
    "dotnet",
    "ffmpeg",
    "git",
    "go",
    "kubectl",
    "make",
    "mkdir",
    "mv",
    "node",
    "npm",
    "npx",
    "pip",
    "pipenv",
    "pnpm",
    "poetry",
    "pytest",
    "python",
    "python3",
    "rm",
    "uv",
    "wget",
    "winget",
    "yarn",
}

_PROMPT_RE = re.compile(r"^\s*(?:[$#>]\s+|PS\s+[^>]+>\s+|[A-Za-z]:\\[^>]*>\s*)")
_FILE_PATH_RE = re.compile(
    r"(?ix)"
    r"(?:"
    r"(?:[A-Za-z]:\\|/|\./|\../)[^\s:]+"
    r"|"
    r"[\w.-]+(?:/|\\)[\w./\\-]+"
    r"|"
    r"[\w.-]+\.(?:py|js|jsx|ts|tsx|json|ya?ml|toml|md|html|css|sql|env|ini|cfg|dockerfile)"
    r")"
)
_KEY_VALUE_RE = re.compile(r"^\s*[-\w.\"']+\s*:\s*.+$")
_PYTHON_HINT_RE = re.compile(r"(?m)^\s*(def|class|from|import|if __name__|async def)\b")
_JS_HINT_RE = re.compile(r"\b(const|let|var|function|import|export|require|console\.log|=>|interface|type)\b")
_HTML_HINT_RE = re.compile(r"<\s*/?\s*[a-zA-Z][\w:-]*(?:\s+[^>]*)?>")
_CSS_HINT_RE = re.compile(r"[.#]?[A-Za-z][\w-]*\s*\{[^{}]*:[^{};]+;?[^{}]*\}", re.DOTALL)
_SQL_HINT_RE = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE\s+TABLE|ALTER\s+TABLE|FROM|WHERE)\b", re.IGNORECASE)
_DOCKER_HINT_RE = re.compile(r"(?m)^\s*(FROM|RUN|COPY|ADD|CMD|ENTRYPOINT|WORKDIR|ENV|EXPOSE)\b")
_ERROR_HINT_RE = re.compile(
    r"\b(traceback|exception|error|failed|failure|not found|stack trace|module not found|cannot|errno)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CodeAnalysis:
    content_type: ContentType
    language: str
    code: str
    normalized_code: str
    normalized_hash: str
    verified: bool
    validation_status: ValidationStatus
    validation_error: str | None
    review_reasons: tuple[str, ...]


def normalize_code_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = textwrap.dedent(text).strip()
    lines = [line.rstrip() for line in text.split("\n")]
    compacted: list[str] = []
    previous_blank = False
    for line in lines:
        blank = not line.strip()
        if blank and previous_blank:
            continue
        compacted.append(line)
        previous_blank = blank
    return "\n".join(compacted).strip()


def normalized_hash(text: str) -> str:
    normalized = normalize_code_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def is_code_like(content_type: ContentType) -> bool:
    return content_type not in {"plain_text", "ui_label"}


def analyze_ocr_text(
    text: str,
    *,
    ocr_confidence: float | None = None,
    strict_mode: bool = True,
    mark_uncertain_code: bool = True,
) -> CodeAnalysis | None:
    normalized = normalize_code_text(text)
    if not normalized:
        return None

    content_type, language, code = _classify_and_language(normalized)
    code = _strip_shell_prompts(code) if content_type == "terminal_command" else code
    normalized = normalize_code_text(code)
    digest = normalized_hash(normalized)
    validation_status, validation_error, parser_verified = _validate(normalized, language, content_type)
    rule_verified = content_type in {"terminal_command", "file_path", "error_message"}
    verified = parser_verified or rule_verified

    review_reasons: list[str] = []
    if is_code_like(content_type):
        if mark_uncertain_code and ocr_confidence is not None and ocr_confidence < CODE_REVIEW_CONFIDENCE_THRESHOLD:
            review_reasons.append(
                f"OCR confidence {ocr_confidence:.2f} is below the code review threshold "
                f"{CODE_REVIEW_CONFIDENCE_THRESHOLD:.2f}."
            )
        if validation_status == "invalid":
            review_reasons.append(f"Validation failed: {validation_error}")
        if strict_mode and not verified:
            review_reasons.append("Not verified by a parser or simple deterministic rule.")

    return CodeAnalysis(
        content_type=content_type,
        language=language,
        code=normalized,
        normalized_code=normalized,
        normalized_hash=digest,
        verified=verified,
        validation_status=validation_status,
        validation_error=validation_error,
        review_reasons=tuple(review_reasons),
    )


def _classify_and_language(text: str) -> tuple[ContentType, str, str]:
    stripped_prompt = _strip_shell_prompts(text)
    if _looks_like_terminal_command(text, stripped_prompt):
        return "terminal_command", "bash", stripped_prompt

    if _looks_like_json(text):
        return "configuration", "json", text
    if _HTML_HINT_RE.search(text):
        return "source_code", "html", text
    if _DOCKER_HINT_RE.search(text):
        return "configuration", "dockerfile", text
    if _CSS_HINT_RE.search(text):
        return "source_code", "css", text
    if _SQL_HINT_RE.search(text):
        return "source_code", "sql", text
    if _looks_like_python(text):
        return "source_code", "python", text
    if _looks_like_javascript(text):
        language = "typescript" if re.search(r"\b(interface|type)\s+\w+|:\s*\w+\s*[=;,)]", text) else "javascript"
        return "source_code", language, text
    if _looks_like_yaml(text):
        return "configuration", "yaml", text
    if _ERROR_HINT_RE.search(text):
        return "error_message", "other", text
    if _looks_like_file_path(text):
        return "file_path", "other", text
    if _looks_like_ui_label(text):
        return "ui_label", "other", text
    return "plain_text", "other", text


def _strip_shell_prompts(text: str) -> str:
    return "\n".join(_PROMPT_RE.sub("", line).rstrip() for line in text.split("\n")).strip()


def _looks_like_terminal_command(original: str, stripped_prompt: str) -> bool:
    if stripped_prompt != original.strip() and stripped_prompt:
        return True
    lines = [line.strip() for line in stripped_prompt.split("\n") if line.strip()]
    if not lines:
        return False
    command_like = 0
    for line in lines:
        token = re.split(r"\s+", line, maxsplit=1)[0].lower()
        if token in _SHELL_COMMANDS or line.startswith(("./", "../")):
            command_like += 1
    return command_like == len(lines) and command_like > 0


def _looks_like_json(text: str) -> bool:
    stripped = text.strip()
    return (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]"))


def _looks_like_yaml(text: str) -> bool:
    lines = [line for line in text.split("\n") if line.strip()]
    if len(lines) < 2:
        return False
    key_values = sum(1 for line in lines if _KEY_VALUE_RE.match(line))
    return key_values >= 2 or (key_values >= 1 and any(line.lstrip().startswith("- ") for line in lines))


def _looks_like_python(text: str) -> bool:
    if _PYTHON_HINT_RE.search(text):
        return True
    try:
        ast.parse(text)
    except SyntaxError:
        return False
    return "\n" in text and any(token in text for token in ("=", "(", ")", "."))


def _looks_like_javascript(text: str) -> bool:
    return bool(_JS_HINT_RE.search(text) or re.search(r"[{};]\s*$", text, re.MULTILINE))


def _looks_like_file_path(text: str) -> bool:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return bool(lines) and all(_FILE_PATH_RE.fullmatch(line) for line in lines)


def _looks_like_ui_label(text: str) -> bool:
    words = text.split()
    if len(words) > 5 or "\n" in text:
        return False
    return not any(ch in text for ch in "{}[]();=$`")


def _validate(text: str, language: str, content_type: ContentType) -> tuple[ValidationStatus, str | None, bool]:
    if language == "json":
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            return "invalid", str(exc), False
        return "valid", None, True
    if language == "yaml":
        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            return "invalid", str(exc), False
        return ("valid", None, True) if isinstance(loaded, (dict, list)) else ("invalid", "YAML is scalar-only.", False)
    if language == "python":
        try:
            ast.parse(text)
        except SyntaxError as exc:
            return "invalid", str(exc), False
        return "valid", None, True
    if content_type in {"terminal_command", "file_path", "error_message"}:
        return "not_applicable", None, True
    return "not_applicable", None, False
