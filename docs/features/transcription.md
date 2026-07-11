# Audio transcription (`videodoc transcribe`)

## Summary
`videodoc transcribe <project>` is README §17's "Fase 4 — Trascrizione audio": for every video that already has extracted audio (`videodoc extract-audio`), transcribes it with `faster-whisper` into timestamped segments, saves them to `workdir/<id>/transcript/<id>.json` and the project's `project.db` (`transcript_segments` table), and updates that video's `metadata.json`. It is idempotent: if a transcript already exists, the Whisper engine is never invoked for that video.

## Performance model
The command now resolves runtime settings explicitly instead of relying on faster-whisper defaults:

- `transcription.device: auto` uses CUDA when `cuda_is_usable()` confirms both a CUDA device and loadable cuBLAS; otherwise it uses CPU.
- `transcription.compute_type: auto` resolves to `int8_float16` on CUDA and `int8` on CPU. On 8 GB laptop GPUs this leaves enough headroom for batched inference while keeping accuracy close to `float16`. Users who want maximum precision can force `float16`.
- `transcription.mode: auto` resolves to `batched` on CUDA and `standard` on CPU. Batched mode wraps the loaded `WhisperModel` in `faster_whisper.BatchedInferencePipeline` once per run.
- CUDA batched mode defaults to one video worker and `batch_size: 8`. That avoids running two huge videos at once while still feeding the GPU multiple chunks per inference call.
- `word_timestamps` defaults to `false` because the project does not persist word-level timestamps; computing them adds substantial alignment work for data that would be discarded.
- `beam_size` and `best_of` default to `1` for greedy decoding, which is much faster than the faster-whisper default beam size of 5.
- `vad_filter: true` and `chunk_length_seconds: 30` let faster-whisper skip non-speech and batch voiced chunks.

The key optimization is for a single very long video: per-video parallelism cannot help when there is only one active file, but batched chunk inference can keep the GPU busier.

## What was implemented
- `core/utils/transcription.py` keeps `load_whisper_model(...)`, adds `build_batched_pipeline(model)`, and extends `transcribe_audio(...)` with explicit runtime options: `mode`, `batch_size`, `beam_size`, `best_of`, `vad_filter`, `chunk_length_seconds`, and `condition_on_previous_text`.
- `core/utils/hardware.py` centralizes runtime resolution for device, compute type, transcription mode, video workers, CPU threads, and batched GPU batch size.
- `core/services/transcription_service.py::TranscriptionService.run()` loads the model once, optionally wraps it in the batched pipeline once, then transcribes fresh videos while keeping JSON/SQLite commits ordered and idempotent.
- Existing transcripts still self-heal the DB: the engine is skipped, but `transcript_segments` is rewritten from the on-disk JSON.
- `videodoc transcribe` exposes runtime overrides: `--workers`, `--device`, `--compute-type`, `--mode`, `--batch-size`, `--beam-size`, and `--word-timestamps/--no-word-timestamps`.

## Main files
- `src/videodoc/core/utils/transcription.py` — model load, batched pipeline wrapper, transcription call parsing.
- `src/videodoc/core/utils/hardware.py` — runtime/default resolution.
- `src/videodoc/core/services/transcription_service.py` — orchestration, skip path, JSON/DB writes.
- `src/videodoc/cli/commands/transcribe.py` — CLI command and runtime overrides.

## Design decisions
- Transcript JSON/DB rows still store segment-level `start_seconds`/`end_seconds`, not per-word timestamps. In batched text-only mode, these timestamps come from VAD/chunk boundaries and restored speech timestamps rather than word alignment.
- CUDA `auto` now prefers `int8_float16` instead of raw `float16` because the target workload includes very long videos and common 8 GB laptop GPUs. This is a practical speed/memory default, not a hard requirement.
- Batched mode defaults to one video worker on CUDA. If several small videos are available and VRAM permits it, users can override `--workers`, but for 74-hour workshop folders the safer high-throughput path is one video at a time with a larger internal batch.
- No automatic cleanup of a stale transcript after the source video is reingested with different content — same principle already applied to audio: delete the file manually to force re-transcription.

## CLI

```bash
videodoc transcribe corso-software-x
# Project: corso-software-x
# +-----------------+
# | Transcribed | 8 |
# | Skipped     | 0 |
# +-----------------+

videodoc transcribe corso-software-x --device cuda --mode batched --compute-type int8_float16 --batch-size 8 --beam-size 1 --workers 1 --no-word-timestamps
```

## Tests
- Unit: `tests/core/test_transcription_utils.py`, `tests/core/test_hardware.py`, `tests/core/test_transcript.py`, `tests/core/test_database.py`.
- Service: `tests/core/test_transcription_service.py`, including the CUDA auto/batched runtime path and existing skip/self-heal behavior.
- CLI: `tests/cli/test_cli_transcribe_command.py`, including runtime flag propagation.
