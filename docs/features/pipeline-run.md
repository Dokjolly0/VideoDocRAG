# Pipeline one-shot (`videodoc run`)

`videodoc run <project>` implements the one-command pipeline promised in README §10.

The command is intentionally an orchestrator, not a second implementation of the pipeline. `PipelineService` calls the existing services in order:

`scan` -> `ingest` -> `sync-codebase` -> `extract-audio` -> `transcribe` -> `frames` -> `ocr` -> `code` -> `chunk` -> `embed` -> `index` -> `outline` -> `generate` -> `review` -> `export` -> `index-docs`.

It does not open `chat`, because that command is interactive when no message is provided. Instead, `run` prepares the raw vector index, generated docs, export output, and documentation index so `ask` or `chat` can be used immediately afterwards.

The final export defaults to `mkdocs`, matching the explicit full-flow example in README §10. Users can override it with `--format`; `--top-k` is passed through to Markdown section generation.

Structural failures from any step stop the pipeline and return exit code 1 through the CLI. Per-video or per-file errors that the underlying services already treat as recoverable are kept as warnings in the step summary, allowing later steps to decide whether there is still enough material to continue.

Verified by:

```bash
python -m pytest tests/core/test_pipeline_service.py tests/cli/test_cli_run_command.py
```
