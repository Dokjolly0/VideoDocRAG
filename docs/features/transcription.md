# Audio transcription (`videodoc transcribe`)

## Summary
`videodoc transcribe <project>` is README §17's "Fase 4 — Trascrizione audio": for every video that already has extracted audio (`videodoc extract-audio`), transcribes it with `faster-whisper` into timestamped segments, saves them to `workdir/<id>/transcript/<id>.json` and the project's `project.db` (`transcript_segments` table), and updates that video's `metadata.json`. It is idempotent: if a transcript already exists, the Whisper engine is never invoked for that video.

## Performance model
The command resolves runtime settings explicitly instead of relying on faster-whisper defaults:

- `transcription.device: auto` uses CUDA when `cuda_is_usable()` confirms both a CUDA device and loadable cuBLAS; otherwise it uses CPU.
- On CUDA, `probe_gpu()` reads NVML via `nvidia-ml-py` and falls back to `nvidia-smi`. The planner uses dedicated framebuffer VRAM only (`memory.total` / `memory.free`); Windows shared GPU memory is deliberately ignored because it is system RAM and is too slow/unpredictable for CTranslate2 batch sizing.
- `transcription.compute_type: auto` chooses `float16` only when the GPU is tensor-core capable and has enough dedicated VRAM free; older pre-Tensor-Core devices use `int8`; common 8 GB laptop GPUs use `int8_float16` for the best speed/memory balance.
- `transcription.mode: auto` resolves to `batched` on CUDA and `standard` on CPU. Batched mode wraps the loaded `WhisperModel` in `faster_whisper.BatchedInferencePipeline` once per run.
- CUDA batched mode defaults to one video worker. `transcription.batch_size: auto` is computed from dedicated free VRAM with a safety margin and clamped to a practical range; if GPU details are unavailable, it falls back to the conservative legacy value `8`.
- CUDA OOMs are handled before the long parallel phase: model-load OOM can downgrade compute type, the first fresh video is used as a serial pre-flight that can halve batch size and reload if needed, and later per-video OOMs retry once with half the batch.
- `word_timestamps` defaults to `false` because the project does not persist word-level timestamps; computing them adds substantial alignment work for data that would be discarded.
- `beam_size` and `best_of` default to `1` for greedy decoding, which is much faster than the faster-whisper default beam size of 5.
- `vad_filter: true` and `chunk_length_seconds: 30` let faster-whisper skip non-speech and batch voiced chunks.

The key optimization is for a single very long video: per-video parallelism cannot help when there is only one active file, but batched chunk inference can keep the GPU busier.

## What was implemented
- `core/utils/transcription.py` keeps `load_whisper_model(...)`, adds `build_batched_pipeline(model)`, and extends `transcribe_audio(...)` with explicit runtime options: `mode`, `batch_size`, `beam_size`, `best_of`, `vad_filter`, `chunk_length_seconds`, and `condition_on_previous_text`.
- `core/utils/gpu.py` probes dedicated VRAM through NVML/`nvidia-smi` and detects CUDA OOM errors without making GPU diagnostics fatal.
- `core/utils/hardware.py` centralizes runtime resolution for device, compute type, transcription mode, video workers, CPU threads, and GPU-aware batched batch size.
- `core/services/transcription_service.py::TranscriptionService.run()` loads the model once, optionally wraps it in the batched pipeline once, then transcribes fresh videos while keeping JSON/SQLite commits ordered and idempotent.
- Existing transcripts still self-heal the DB: the engine is skipped, but `transcript_segments` is rewritten from the on-disk JSON.
- `videodoc transcribe` exposes runtime overrides: `--workers`, `--device`, `--compute-type`, `--mode`, `--batch-size`, `--beam-size`, and `--word-timestamps/--no-word-timestamps`.

## Main files
- `src/videodoc/core/utils/transcription.py` — model load, batched pipeline wrapper, transcription call parsing.
- `src/videodoc/core/utils/gpu.py` — NVML/`nvidia-smi` GPU probe and CUDA OOM detection.
- `src/videodoc/core/utils/hardware.py` — runtime/default resolution and CUDA auto planner.
- `src/videodoc/core/services/transcription_service.py` — orchestration, skip path, JSON/DB writes, and CUDA OOM retry policy.
- `src/videodoc/cli/commands/transcribe.py` — CLI command and runtime overrides.

## Design decisions
- Transcript JSON/DB rows still store segment-level `start_seconds`/`end_seconds`, not per-word timestamps. In batched text-only mode, these timestamps come from VAD/chunk boundaries and restored speech timestamps rather than word alignment.
- CUDA `auto` plans from dedicated free VRAM only. Shared GPU memory reported by Windows is intentionally not counted: using it would encourage PCIe/system-RAM paging instead of real GPU throughput.
- `int8_float16` is the normal 8 GB laptop-GPU choice, while `float16` is reserved for devices with enough dedicated VRAM headroom. This is a practical speed/memory default, not a hard requirement.
- Batched mode defaults to one video worker on CUDA. If several small videos are available and VRAM permits it, users can override `--workers`, but for 74-hour workshop folders the safer high-throughput path is one video at a time with a dynamically larger internal batch.
- No automatic cleanup of a stale transcript after the source video is reingested with different content — same principle already applied to audio: delete the file manually to force re-transcription.

## CLI

```bash
videodoc transcribe corso-software-x
# Project: corso-software-x
# +-----------------+
# | Transcribed | 8 |
# | Skipped     | 0 |
# +-----------------+

videodoc transcribe corso-software-x --device cuda --mode batched --beam-size 1 --workers 1 --no-word-timestamps
```

## Tests
- Unit: `tests/core/test_gpu.py`, `tests/core/test_hardware.py`, `tests/core/test_transcription_utils.py`, `tests/core/test_transcript.py`, `tests/core/test_database.py`.
- Service: `tests/core/test_transcription_service.py`, including CUDA auto planning, load/pre-flight/fan-out OOM retries, and existing skip/self-heal behavior.
- CLI: `tests/cli/test_cli_transcribe_command.py`, including runtime flag propagation.
