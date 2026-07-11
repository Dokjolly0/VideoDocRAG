import sys

import pytest
import yaml

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import InvalidConfigError

FULL_CONFIG_YAML = """
project:
  name: "Corso Software X"
  slug: "corso-software-x"
  language: "it"
  timezone: "Europe/Rome"

paths:
  videos: "videos"
  attachments: "attachments"
  codebase: "codebase"
  workdir: "workdir"
  indexes: "indexes"
  output: "docs"
  database: "project.db"

llm:
  provider: "ollama"
  model: "qwen2.5-coder:14b"
  context_window: 32768
  temperature: 0.1
  top_p: 0.9

embedding:
  provider: "local"
  model: "bge-m3"
  batch_size: 32

transcription:
  engine: "faster-whisper"
  model: "large-v3"
  language: "it"
  word_timestamps: true

frames:
  interval_seconds: 8
  scene_detection: true
  keyword_boost: true
  workers: "auto"

ocr:
  engine: "rapidocr"
  languages:
    - "it"
    - "en"
  min_confidence: 0.65
  workers: "auto"

chunking:
  min_duration_seconds: 90
  max_duration_seconds: 480
  split_on_topic_change: true
  include_nearby_frames: true

retrieval:
  vector_db: "qdrant"
  top_k: 12
  rerank: true
  hybrid_search: true

code:
  extract_from_ocr: true
  extract_from_attachments: true
  extract_from_codebase: true
  strict_mode: true
  mark_uncertain_code: true

scan:
  default_excludes: true
  add_excludes:
    - "tmp/"
    - "logs/"
  remove_excludes: []
  max_file_size_mb: 5
  follow_symlinks: false
  allowed_code_extensions:
    - ".py"
    - ".js"
    - ".ts"
    - ".tsx"
    - ".jsx"
    - ".json"
    - ".yaml"
    - ".yml"
    - ".md"
  allowed_video_extensions:
    - ".mp4"
    - ".mkv"
    - ".mov"
    - ".avi"
    - ".webm"
    - ".m4v"
    - ".wmv"

documentation:
  format: "markdown"
  include_video_name: true
  include_timestamps: true
  include_code_explanation: true
  include_expected_result: true
  include_common_errors: true
  include_sources_section: true

chat:
  default_source: "docs"
  allow_raw_video_filter: true
  allow_multi_video_filter: true
  allow_time_range_filter: true
  save_sessions: true
  max_history_messages: 20
  default_top_k: 8

gui:
  enabled: false
  backend: "fastapi"
  frontend: "react"
  host: "127.0.0.1"
  port: 8000
"""


def test_default_config_roundtrip():
    config = ProjectConfig.default(name="Demo Course", slug="demo-course")
    reparsed = ProjectConfig.model_validate(yaml.safe_load(config.to_yaml()))
    assert reparsed == config


def test_load_full_readme_example(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(FULL_CONFIG_YAML, encoding="utf-8")
    config = ProjectConfig.load(path)
    assert config.llm.model == "qwen2.5-coder:14b"
    assert config.scan.allowed_code_extensions == [
        ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml", ".md",
    ]
    assert config.paths.database == "project.db"


def test_missing_required_field_raises(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("project:\n  slug: demo\n", encoding="utf-8")
    with pytest.raises(InvalidConfigError):
        ProjectConfig.load(path)


def test_unknown_key_raises(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "project:\n  name: Demo\n  slug: demo\nllm:\n  foo: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(InvalidConfigError):
        ProjectConfig.load(path)


def test_invalid_yaml_raises(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("project: [unclosed", encoding="utf-8")
    with pytest.raises(InvalidConfigError):
        ProjectConfig.load(path)


@pytest.mark.parametrize(
    "override",
    [
        "llm:\n  temperature: 5.0\n",
        "retrieval:\n  top_k: 0\n",
        "chunking:\n  min_duration_seconds: 500\n  max_duration_seconds: 100\n",
    ],
)
def test_range_and_cross_field_validation(tmp_path, override):
    path = tmp_path / "config.yaml"
    path.write_text(f"project:\n  name: Demo\n  slug: demo\n{override}", encoding="utf-8")
    with pytest.raises(InvalidConfigError):
        ProjectConfig.load(path)


def test_save_writes_reloadable_file(tmp_path):
    config = ProjectConfig.default(name="Demo", slug="demo")
    path = tmp_path / "config.yaml"
    config.save(path)
    reloaded = ProjectConfig.load(path)
    assert reloaded == config


def test_load_missing_file_raises_invalid_config_error(tmp_path):
    with pytest.raises(InvalidConfigError):
        ProjectConfig.load(tmp_path / "does-not-exist.yaml")


def test_default_scan_allowed_video_extensions():
    config = ProjectConfig.default(name="Demo", slug="demo")
    assert config.scan.allowed_video_extensions == [
        ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv",
    ]


def _write_config(tmp_path, field, value):
    # yaml.safe_dump (not manual f-string YAML) so backslash-heavy Windows
    # paths are escaped correctly regardless of YAML quoting rules -- single-
    # quoted YAML does NOT interpret backslash escapes the way Python's
    # repr() does, so building the YAML text by hand here would silently test
    # the wrong string.
    raw = {"project": {"name": "Demo", "slug": "demo"}, "paths": {field: value}}
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


@pytest.mark.parametrize("field", ["workdir", "indexes", "output", "database"])
def test_internal_paths_reject_leading_slash_cross_platform(tmp_path, field):
    # "/foo" is anchored -- and fully absolute -- under BOTH Windows and
    # POSIX path rules, so this specific case is rejected on every supported
    # OS with no skip needed (unlike the Windows-only forms below).
    path = _write_config(tmp_path, field, "/foo")
    with pytest.raises(InvalidConfigError):
        ProjectConfig.load(path)


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="drive-relative ('C:foo') and root-relative ('\\foo') forms are only ambiguous under Windows path "
    "rules -- ProjectConfig.load() validates using the host's native path semantics (core/utils/paths.py), so "
    "on POSIX these are just harmless relative filenames and are correctly accepted there, not rejected.",
)
@pytest.mark.parametrize("field", ["workdir", "indexes", "output", "database"])
@pytest.mark.parametrize("bad_value", ["C:\\abs\\path", "C:foo", "\\foo"])
def test_internal_paths_reject_windows_specific_anchored_forms(tmp_path, field, bad_value):
    path = _write_config(tmp_path, field, bad_value)
    with pytest.raises(InvalidConfigError):
        ProjectConfig.load(path)


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="drive-relative ('C:foo'), root-relative ('\\foo'), and even a leading '/' are only ambiguous "
    "forms under Windows path rules for these three fields -- on POSIX a leading '/' is unambiguously "
    "absolute (a valid external source), not an error, so this whole case is Windows-specific.",
)
@pytest.mark.parametrize("field", ["videos", "attachments", "codebase"])
@pytest.mark.parametrize("bad_value", ["C:foo", "\\foo", "/foo"])
def test_source_paths_reject_ambiguous_windows_forms(tmp_path, field, bad_value):
    path = _write_config(tmp_path, field, bad_value)
    with pytest.raises(InvalidConfigError):
        ProjectConfig.load(path)


@pytest.mark.parametrize("field", ["videos", "attachments", "codebase"])
def test_source_paths_accept_true_absolute(tmp_path, field):
    path = _write_config(tmp_path, field, "D:\\Corsi\\Workshop")
    config = ProjectConfig.load(path)
    assert getattr(config.paths, field) == "D:\\Corsi\\Workshop"


@pytest.mark.parametrize("field", ["videos", "attachments", "codebase"])
def test_source_paths_accept_clean_relative(tmp_path, field):
    path = _write_config(tmp_path, field, "custom")
    config = ProjectConfig.load(path)
    assert getattr(config.paths, field) == "custom"


@pytest.mark.parametrize("field", ["workdir", "indexes", "output", "database"])
@pytest.mark.parametrize("bad_value", ["../outside", "sub/../../outside"])
def test_internal_paths_reject_parent_traversal(tmp_path, field, bad_value):
    # A relative value with no anchor still escapes project_dir once joined
    # with it if it walks upward via '..' -- the anchor-only check isn't
    # enough to guarantee these fields stay physically inside the project.
    # Forward-slash forms only: this traversal detection is cross-platform
    # (the backslash form is tested separately below, Windows-only).
    path = _write_config(tmp_path, field, bad_value)
    with pytest.raises(InvalidConfigError):
        ProjectConfig.load(path)


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="backslash is not a path separator under POSIX rules -- '..\\\\outside' is a single literal "
    "filename there, not a traversal, so it is correctly accepted on POSIX, not rejected.",
)
@pytest.mark.parametrize("field", ["workdir", "indexes", "output", "database"])
def test_internal_paths_reject_windows_backslash_parent_traversal(tmp_path, field):
    path = _write_config(tmp_path, field, "..\\outside")
    with pytest.raises(InvalidConfigError):
        ProjectConfig.load(path)


@pytest.mark.parametrize("field", ["videos", "attachments", "codebase"])
@pytest.mark.parametrize("bad_value", ["../outside", "sub/../../outside"])
def test_source_paths_reject_relative_parent_traversal(tmp_path, field, bad_value):
    path = _write_config(tmp_path, field, bad_value)
    with pytest.raises(InvalidConfigError):
        ProjectConfig.load(path)


@pytest.mark.parametrize("field", ["videos", "attachments", "codebase"])
def test_source_paths_accept_parent_traversal_inside_true_absolute(tmp_path, field):
    # '..' inside an already-absolute path is fine: it's never joined with
    # project_dir (it's used directly), so it resolves unambiguously on its
    # own regardless of the '..' segment.
    path = _write_config(tmp_path, field, "D:\\Corsi\\..\\OtherCorsi\\Workshop")
    config = ProjectConfig.load(path)
    assert getattr(config.paths, field) == "D:\\Corsi\\..\\OtherCorsi\\Workshop"

def test_ocr_defaults():
    config = ProjectConfig.default(name="Demo", slug="demo")
    assert config.ocr.engine == "rapidocr"
    assert config.ocr.languages == ["it", "en"]
    assert config.ocr.min_confidence == 0.65
    assert config.ocr.workers == "auto"
    assert config.frames.workers == "auto"


def test_concurrency_and_transcription_runtime_defaults_roundtrip():
    config = ProjectConfig.default(name="Demo", slug="demo")
    assert config.ingest.workers == "auto"
    assert config.audio.workers == "auto"
    assert config.transcription.device == "auto"
    assert config.transcription.word_timestamps is False
    assert config.transcription.compute_type == "auto"
    assert config.transcription.mode == "auto"
    assert config.transcription.workers == "auto"
    assert config.transcription.cpu_threads == "auto"
    assert config.transcription.batch_size == "auto"
    assert config.transcription.beam_size == 1
    assert config.transcription.best_of == 1
    assert config.transcription.vad_filter is True
    assert config.transcription.chunk_length_seconds == 30
    assert config.transcription.condition_on_previous_text is False
    reparsed = ProjectConfig.model_validate(yaml.safe_load(config.to_yaml()))
    assert reparsed == config


def test_concurrency_and_transcription_runtime_fields_accept_positive_ints(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump({
            "project": {"name": "Demo", "slug": "demo"},
            "ingest": {"workers": 3},
            "audio": {"workers": 4},
            "transcription": {
                "device": "cuda",
                "compute_type": "float16",
                "mode": "batched",
                "workers": 2,
                "cpu_threads": 1,
                "batch_size": 8,
                "beam_size": 2,
                "best_of": 2,
                "vad_filter": False,
                "chunk_length_seconds": 45,
                "condition_on_previous_text": True,
            },
        }),
        encoding="utf-8",
    )
    config = ProjectConfig.load(path)
    assert config.ingest.workers == 3
    assert config.audio.workers == 4
    assert config.transcription.device == "cuda"
    assert config.transcription.compute_type == "float16"
    assert config.transcription.mode == "batched"
    assert config.transcription.workers == 2
    assert config.transcription.cpu_threads == 1
    assert config.transcription.batch_size == 8
    assert config.transcription.beam_size == 2
    assert config.transcription.best_of == 2
    assert config.transcription.vad_filter is False
    assert config.transcription.chunk_length_seconds == 45
    assert config.transcription.condition_on_previous_text is True


@pytest.mark.parametrize("section,field", [
    ("ingest", "workers"),
    ("audio", "workers"),
    ("transcription", "workers"),
    ("transcription", "cpu_threads"),
    ("transcription", "batch_size"),
    ("frames", "workers"),
    ("ocr", "workers"),
])
def test_concurrency_fields_reject_non_positive_ints(tmp_path, section, field):
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump({"project": {"name": "Demo", "slug": "demo"}, section: {field: 0}}),
        encoding="utf-8",
    )
    with pytest.raises(InvalidConfigError):
        ProjectConfig.load(path)
