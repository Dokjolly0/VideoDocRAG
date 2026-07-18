# Status e ispezione timestamp

Implementazione README §12.2, §12.3 e §35.4.

## Comandi

- `videodoc status <project>` carica il progetto e chiama `PipelineStatusService`.
- `videodoc inspect <project> --timestamp HH:MM:SS [--video NAME]` carica il progetto, converte il timecode con lo stesso parser usato da `ask`/`chat`, e chiama `TimestampInspectionService`.

## Status

`PipelineStatusService` è volutamente non distruttivo: se `project.db` non esiste, il comando mostra una pipeline non avviata e non crea il file SQLite. Se `project.db` esiste, legge le tabelle tramite le helper resilienti già usate dal resto del core.

Lo status combina:

- `sources.yaml` per sapere se lo scan fonti è stato eseguito;
- `project.db` per video, segmenti transcript, frame, blocchi codice, chunk e chat salvate;
- manifest/file in `workdir/<video_id>/...` per audio, transcript, frame, OCR, codice e chunk;
- `indexes/embeddings/<video_id>.json`, `indexes/vector_index.json` e `indexes/documentation_index.json` per embedding e indici;
- `docs/`, `docs/sources/`, `docs/review_report.*` ed `exports/` per documentazione, revisione ed export.

Gli indici vengono caricati con `VectorIndex.load()`: un file presente ma corrotto è riportato come warning e non come indice valido.

## Inspect

`TimestampInspectionService` usa `project.db` come fonte strutturata principale:

- segmento transcript che contiene il timestamp, oppure il più vicino;
- frame più vicino, con OCR/confidenza e flag `contains_code`;
- fino a tre blocchi codice temporizzati più vicini;
- chunk che contiene il timestamp, oppure il più vicino;
- manifest `docs/sources/*.sources.json` che citano lo stesso video e un range temporale che contiene il timestamp.

Se il progetto ha più video, `--video` è obbligatorio per evitare un contesto ambiguo. Il selettore video accetta id (`workshop_01`), filename (`workshop_01.mp4`) o stem (`workshop_01`).

## Verifica

Copertura aggiunta:

- `tests/core/test_status_service.py`;
- `tests/core/test_inspection_service.py`;
- `tests/cli/test_cli_status_command.py`;
- `tests/cli/test_cli_inspect_command.py`.
