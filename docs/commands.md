# Comandi CLI — riferimento

Elenco di **ogni comando `videodoc` implementato**, con sintassi, opzioni ed esempio di output atteso (verificato contro il codice sorgente attuale, non inventato). Questo file è un riferimento rapido e verificabile — per il *perché* delle scelte dietro ogni comando vedi `docs/features/*.md`; per una guida passo-passo all'installazione e all'uso vedi `RUN.md`.

**Nota di processo**: questo file va aggiornato ad ogni comando nuovo o modificato — stesso impegno di manutenzione già richiesto per `docs/CHANGELOG.md`. Aggiornarlo fa parte della checklist di fine-step, insieme a `docs/CHANGELOG.md` e a `docs/features/<feature>.md`.

---

## init

**Sintassi:** `videodoc init <name> [--path PATH] [--videos PATH] [--attachments PATH] [--codebase PATH]`
**Descrizione:** Crea (o, se già esistente, riconosce) un progetto — struttura di cartelle, `config.yaml`, registrazione nel registro locale sotto lo slug canonico del nome.
**Exit code:** 0 = sempre, sia alla prima creazione sia se il progetto esisteva già (nessun errore in quel caso, solo un avviso se sono stati passati `--videos`/`--attachments`/`--codebase` ignorati). 1 = nome non slugificabile, path in conflitto con un progetto diverso già esistente, o `--videos`/`--attachments`/`--codebase` non valido (es. path relativo con `..`).
**Esempio:**
```
$ videodoc init corso-software-x --videos "D:\Corsi\Workshop"
Project 'corso-software-x' initialized at C:\Users\utente\VideoDocRAG\projects\corso-software-x
Registered as 'corso-software-x' in the local project registry.

$ videodoc init corso-software-x --videos "D:\Altro"
Project 'corso-software-x' already initialized at C:\Users\utente\VideoDocRAG\projects\corso-software-x (config.yaml kept unchanged)
Warning: --videos ignored: config.yaml already exists and 'init' never overwrites it.
Registered as 'corso-software-x' in the local project registry.
```
**Vedi anche:** [features/project-initialization.md](features/project-initialization.md), [features/slugify.md](features/slugify.md), [features/external-source-paths.md](features/external-source-paths.md)

---

## list

**Sintassi:** `videodoc list`
**Descrizione:** Elenca tutti i progetti registrati nel registro locale, con path e data di registrazione.
**Exit code:** 0 = sempre (anche a registro vuoto).
**Esempio:**
```
$ videodoc list
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Name           ┃ Path                                               ┃ Created at                ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ corso-software-x │ C:\Users\utente\VideoDocRAG\projects\corso-software-x │ 2026-07-10T13:14:59+00:00 │
└────────────────┴────────────────────────────────────────────────────┴───────────────────────────┘

$ videodoc list
No registered projects. Use 'videodoc init <name>' or 'videodoc link <path>'.
```
**Vedi anche:** [features/project-registry.md](features/project-registry.md)

---

## link

**Sintassi:** `videodoc link <path> [--name ALIAS]`
**Descrizione:** Registra nel registro locale un progetto già esistente su disco (deve contenere `config.yaml`) senza ricrearlo. `--name` imposta un alias locale distinto dallo slug canonico del progetto.
**Exit code:** 0 = successo. 1 = path senza `config.yaml` valido, alias non slugificabile, o conflitto con un progetto diverso già registrato con lo stesso nome.
**Esempio:**
```
$ videodoc link D:\Corsi\corso-software-x
Linked 'corso-software-x' -> D:\Corsi\corso-software-x

$ videodoc link D:\Corsi\corso-software-x --name "Alias Locale!!"
Linked as alias 'alias-locale' -> D:\Corsi\corso-software-x (the project's own slug is 'corso-software-x')
```
**Vedi anche:** [features/project-registry.md](features/project-registry.md), [features/slugify.md](features/slugify.md)

---

## unlink

**Sintassi:** `videodoc unlink <name>`
**Descrizione:** Rimuove un progetto dal registro locale. **Non cancella mai i file del progetto** — agisce solo sul registro.
**Exit code:** 0 = successo. 1 = nome non registrato.
**Esempio:**
```
$ videodoc unlink corso-software-x
Unlinked 'corso-software-x' from the registry (files at D:\Corsi\corso-software-x were not deleted).
```
**Vedi anche:** [features/project-registry.md](features/project-registry.md)

---

## path

**Sintassi:** `videodoc path <name>`
**Descrizione:** Stampa il percorso assoluto del progetto (solo il path, senza formattazione — pensato per essere usato in script, es. `cd (videodoc path corso-software-x)`).
**Exit code:** 0 = successo. 1 = nome non registrato.
**Esempio:**
```
$ videodoc path corso-software-x
C:\Users\utente\VideoDocRAG\projects\corso-software-x
```
**Vedi anche:** [features/project-registry.md](features/project-registry.md)

---

## scan

**Sintassi:** `videodoc scan <project>`
**Descrizione:** Enumera le fonti di un progetto (`videos/`, `attachments/`, `codebase/`, interne o esterne), applica le esclusioni configurate, e (ri)scrive `sources.yaml` per intero.
**Exit code:** 0 = sempre, anche con zero video trovati o con una fonte esterna mancante/non valida (in quel caso solo un `Warning`, mai un errore). 1 = solo per progetto sconosciuto o `config.yaml` non valido.
**Esempio:**
```
$ videodoc scan corso-software-x
Project: corso-software-x
+----------------------------------+
| Videos      | 8 found            |
| Attachments | 3 found            |
| Codebase    | present (42 files) |
+----------------------------------+
Excluded directories: .git, node_modules, __pycache__, dist, build, ...
Excluded file patterns: .DS_Store
Sources manifest updated: sources.yaml
```
(La tabella usa caratteri box-drawing Unicode su un terminale che li supporta; l'esempio sopra mostra il fallback ASCII di Rich per terminali Windows legacy — entrambi renderizzano lo stesso contenuto.)
**Vedi anche:** [features/scan.md](features/scan.md), [features/external-source-paths.md](features/external-source-paths.md)

---

## ingest

**Sintassi:** `videodoc ingest <project> [--workers N] [--verify]`
**Descrizione:** Per ogni video in `videos/`, usa un fingerprint rapido (`size` + `mtime` + `inode`) per saltare i rerun invariati senza rileggerli, calcola l'hash SHA-256 quando il fingerprint cambia o con `--verify`, estrae durata/formato/risoluzione/codec via `ffprobe`, registra il video in `project.db` (SQLite) e crea `workdir/<id>/{audio,frames,transcript,ocr,chunks}/` + `metadata.json`.
**Exit code:** 0 = successo, anche con errori per-video (probe/hash falliti su un singolo file: stampati come `Warning`, il video viene saltato, gli altri continuano) o con un reingest (stampa un `Warning` sui possibili artefatti obsoleti, non cancellati). 1 = progetto sconosciuto, `config.yaml` non valido, **zero video trovati**, `ffprobe` non disponibile in `PATH`, o collisione di id tra due video diversi (stesso slug derivato da nomi file diversi).
**Prerequisito:** richiede `ffprobe` (parte di FFmpeg) in `PATH` — vedi `RUN.md` §1.
**Esempio:**
```
$ videodoc ingest corso-software-x
Project: corso-software-x
+----------------+
| Ingested   | 8 |
| Reingested | 0 |
| Skipped    | 0 |
+----------------+
Database updated: project.db

$ videodoc ingest corso-software-x
Project: corso-software-x
+----------------+
| Ingested   | 0 |
| Reingested | 1 |
| Skipped    | 7 |
+----------------+
Database updated: project.db
Warning: workshop-05: video content changed and was reingested -- workdir/workshop-05/{audio,frames,transcript,ocr,chunks} may still contain artifacts from the previous version (never deleted automatically); re-run the relevant pipeline phase(s) to refresh them.
```
**Vedi anche:** [features/ingest.md](features/ingest.md)

---

## extract-audio

**Sintassi:** `videodoc extract-audio <project>`
**Descrizione:** Per ogni video già registrato con `ingest`, estrae l'audio in WAV mono a 16kHz via FFmpeg in `workdir/<id>/audio/<id>.wav` e aggiorna `metadata.json` (`audio_path`). Idempotente per presenza del file: se il `.wav` esiste già, FFmpeg non viene invocato.
**Exit code:** 0 = successo, anche con errori per-video (estrazione fallita su un singolo file: stampati come `Warning`, il video viene saltato, gli altri continuano). 1 = progetto sconosciuto, `config.yaml` non valido, **nessun video ancora registrato** (`ingest` mai eseguito), `ffmpeg` non disponibile in `PATH`, o problema strutturale su `project.db`.
**Prerequisito:** richiede `ffmpeg` (parte di FFmpeg, distinto da `ffprobe` già richiesto da `ingest`) in `PATH` — vedi `RUN.md` §1.
**Esempio:**
```
$ videodoc extract-audio corso-software-x
Project: corso-software-x
+---------------+
| Extracted | 8 |
| Skipped   | 0 |
+---------------+

$ videodoc extract-audio corso-software-x
Project: corso-software-x
+---------------+
| Extracted | 0 |
| Skipped   | 8 |
+---------------+
```
**Vedi anche:** [features/audio-extraction.md](features/audio-extraction.md)

---

## transcribe

**Sintassi:** `videodoc transcribe <project> [--workers N] [--device auto|cpu|cuda] [--compute-type TYPE] [--mode auto|standard|batched] [--batch-size N] [--beam-size N] [--word-timestamps|--no-word-timestamps]`
**Descrizione:** Per ogni video con audio già estratto, trascrive con `faster-whisper` in `workdir/<id>/transcript/<id>.json` e nella tabella `transcript_segments` di `project.db`, aggiornando `metadata.json` (`transcript_path`). Idempotente per presenza del file: se il transcript esiste già, il motore non viene invocato (ma le righe DB vengono comunque riallineate dal JSON, per auto-ripararsi da un eventuale fallimento DB precedente).
**Exit code:** 0 = successo, anche con errori per-video (trascrizione fallita su un singolo file: stampati come `Warning`, il video viene saltato, gli altri continuano). 1 = progetto sconosciuto, `config.yaml` non valido, **nessun video ancora registrato** (`ingest` mai eseguito) o **nessun video con audio estratto** (`extract-audio` mai eseguito), engine non supportato (solo `faster-whisper` è implementato), modello non caricabile, o problema strutturale su `project.db`.
**Prerequisito:** `faster-whisper` è una dipendenza richiesta (installata automaticamente); al primo utilizzo reale scarica il modello configurato (default `large-v3`, diversi GB) da Hugging Face — vedi `RUN.md` §1. Su CUDA, i default runtime sono ottimizzati per throughput: `mode=batched`, `compute_type` e `batch_size` calcolati dalla VRAM dedicata libera, `beam_size=1`, `workers=1` e niente word timestamps.
**Esempio:**
```
$ videodoc transcribe corso-software-x --device cuda --mode batched --beam-size 1 --workers 1 --no-word-timestamps
Project: corso-software-x
+-----------------+
| Transcribed | 8 |
| Skipped     | 0 |
+-----------------+

$ videodoc transcribe corso-software-x --device cuda --mode batched --beam-size 1 --workers 1 --no-word-timestamps
Project: corso-software-x
+-----------------+
| Transcribed | 0 |
| Skipped     | 8 |
+-----------------+
```
**Vedi anche:** [features/transcription.md](features/transcription.md)

---

## frames

**Sintassi:** `videodoc frames <project> [--workers N] [--interval-seconds N] [--scene-detection|--no-scene-detection] [--keyword-boost|--no-keyword-boost] [--scene-threshold X] [--hwaccel auto|cuda|none]`
**Descrizione:** Per ogni video gia registrato con `ingest`, seleziona timestamp combinando intervallo fisso, cambi scena rilevati da FFmpeg (`select=gt(scene\,threshold)`) e segmenti della trascrizione con parole chiave come "codice"/"comando"/"terminale"/"errore" (README sezione 18.3). Estrae i frame via FFmpeg in `workdir/<id>/frames/frame_NNNN.jpg`, calcola un hash percettivo per scartare frame boosted quasi identici al precedente, e registra tutto in `workdir/<id>/frames/frames.json` e nella tabella `frames` di `project.db`, aggiornando `metadata.json` (`frames_path`). Idempotente per impostazioni semantiche (`interval_seconds`/`scene_detection`/`keyword_boost` e, se la scene detection e attiva, `scene_threshold`); `hwaccel` non influenza skip/ri-estrazione perche e solo un knob di performance.
**Exit code:** 0 = successo, anche con errori per-video (estrazione o scene detection fallita su un singolo file, o estrazione senza frame utilizzabili: stampati come `Warning`, il video viene saltato, gli altri continuano). 1 = progetto sconosciuto, `config.yaml` non valido, nessun video ancora registrato (`ingest` mai eseguito), `ffmpeg` non disponibile in `PATH` quando almeno un video richiede una nuova estrazione, o problema strutturale su `project.db`.
**Prerequisito:** richiede `ffmpeg` in `PATH` solo se almeno un video necessita di estrazione fresca. `--hwaccel auto` usa CUDA solo se FFmpeg e il probe GPU la rendono disponibile e se c'e uno slot GPU libero; `--hwaccel none` forza CPU; `--hwaccel cuda` tenta CUDA e ritenta una volta su CPU se la passata fallisce. Il keyword boost usa la trascrizione se `videodoc transcribe` e gia stato eseguito; altrimenti contribuisce zero frame extra senza generare errore.
**Esempio:**
```
$ videodoc frames corso-software-x
Project: corso-software-x
+---------------+
| Extracted | 8 |
| Skipped   | 0 |
+---------------+

$ videodoc frames corso-software-x
Project: corso-software-x
+---------------+
| Extracted | 0 |
| Skipped   | 8 |
+---------------+
```
**Vedi anche:** [features/frame-extraction.md](features/frame-extraction.md)

---

## ocr

**Sintassi:** `videodoc ocr <project> [--workers N] [--language LANG]... [--min-confidence N]`
**Descrizione:** Per ogni video con frame già estratti (`videodoc frames`), esegue l'OCR (motore RapidOCR) su ogni immagine frame, registra il testo riconosciuto e la relativa confidenza in `workdir/<id>/ocr/<id>.json` e nelle colonne `ocr_text`/`ocr_confidence` della tabella `frames` di `project.db`, aggiornando `metadata.json` (`ocr_path`). Non tocca mai `contains_code`/`perceptual_hash` (riservate rispettivamente alla fase §20, non ancora implementata, e alla fase frame). Idempotente per **due** condizioni indipendenti: le impostazioni effettive salvate in `ocr.json` (`engine`/`languages`/`min_confidence`) devono coincidere con quelle correnti, **e** l'insieme di frame-id correnti deve coincidere con quello registrato nel manifest — un video con frame senza `videodoc frames` mai eseguito viene saltato silenziosamente (non è un errore). Un testo riconosciuto con confidenza sotto `min_confidence` viene comunque registrato (testo vuoto, confidenza reale conservata), per distinguere "OCR eseguito ma rumore" da "OCR mai eseguito" (quest'ultimo resta `NULL`).
**Exit code:** 0 = successo, anche con errori per-frame/per-video (OCR fallito su una singola immagine: stampati come `Warning`, il frame viene saltato e ritentato al run successivo, gli altri continuano). 1 = progetto sconosciuto, `config.yaml` non valido, **nessun video ancora registrato** (`ingest` mai eseguito), il pacchetto `rapidocr` non disponibile quando almeno un video richiede un OCR fresco, o problema strutturale su `project.db`.
**Prerequisito:** richiede i pacchetti Python `rapidocr` e `onnxruntime` (installati automaticamente come dipendenze del progetto, nessun binario di sistema) — ma solo per i video che effettivamente necessitano di un nuovo OCR. Il modello di riconoscimento di default gestisce correttamente anche l'italiano su testo a schermo di qualità realistica (verificato); `--language` è al momento solo informativo (registrato per l'idempotenza, non seleziona un modello diverso).
**Esempio:**
```
$ videodoc ocr corso-software-x
Project: corso-software-x
+---------------+
| Processed | 8 |
| Skipped   | 0 |
+---------------+

$ videodoc ocr corso-software-x
Project: corso-software-x
+---------------+
| Processed | 0 |
| Skipped   | 8 |
+---------------+
```
**Vedi anche:** [features/ocr.md](features/ocr.md)

---

## doctor

**Sintassi:** `videodoc doctor`
**Descrizione:** Comando **machine-scoped** (nessun argomento progetto): verifica lo stato dell'ambiente — versione Python, FFmpeg (`ffprobe`+`ffmpeg`), `faster-whisper` importabile, GPU/CUDA (rilevamento device + caricabilità reale di `cublas`), salute del registro locale, scrivibilità della cartella progetti di default. Non modifica nulla, non scarica nulla, non richiede alcuna conferma.
**Exit code:** 0 = nessun `error` (i `warning`, come un problema CUDA rilevabile ma non bloccante, non influenzano l'exit code). 1 = almeno un check in stato `error`.
**Esempio:**
```
$ videodoc doctor
OK    Python version: 3.13.14 (>= 3.11 required)
OK    FFmpeg (ffprobe + ffmpeg): both found on PATH
OK    faster-whisper: importable
OK    GPU / CUDA: 1 CUDA device(s) detected, cublas64_12.dll loadable; NVIDIA GeForce RTX 4070 Laptop GPU, 8188 MiB dedicated total, 7301 MiB dedicated free, CC 8.9, driver 555.99 (via nvml); auto plan: compute_type=int8_float16, batch_size=19 (...)
OK    Project registry: 3 project(s) registered -- C:\Users\utente\AppData\Local\videodoc\registry.json (default location)
OK    Default projects folder: C:\Users\utente\VideoDocRAG\projects is writable (default location)
6 OK, 0 warning(s), 0 error(s).
```
(Le parole di stato `OK`/`WARN`/`ERROR` sono testo ASCII colorato, non simboli Unicode — verificato che simboli come ✓/⚠ causano un crash reale su alcune console Windows legacy.)
**Vedi anche:** [features/doctor-setup.md](features/doctor-setup.md)

---

## setup

**Sintassi:** `videodoc setup`
**Descrizione:** Comando **machine-scoped**: esegue gli stessi controlli di `doctor` e offre di correggere quanto non è `ok`. Le correzioni via pip (nel venv, reversibili — es. `nvidia-cublas-cu12`/`nvidia-cudnn-cu12`) vengono applicate **automaticamente senza conferma**. Le correzioni di sistema (FFmpeg via `winget`/`apt`/`brew`) chiedono **conferma esplicita** prima di essere eseguite. Le correzioni puramente manuali (es. il passaggio di `PATH` per le DLL CUDA su Windows) vengono solo stampate, mai eseguite.
**Exit code:** 0 = nessun check originariamente `error` resta irrisolto. 1 = almeno un check `error` non ha una correzione, la correzione è stata rifiutata, o il tentativo di correzione è fallito.
**Esempio:**
```
$ videodoc setup
OK    Python version: 3.13.14 (>= 3.11 required)
OK    FFmpeg (ffprobe + ffmpeg): both found on PATH
OK    faster-whisper: importable
WARN  GPU / CUDA: 1 CUDA device(s) detected but cublas64_12.dll could not be loaded: ...
  Applying fix for 'GPU / CUDA': <venv>\Scripts\python.exe -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
  Applied: Successfully installed nvidia-cublas-cu12-... nvidia-cudnn-cu12-...
  On Windows the pip packages alone are not enough -- also run this in your PowerShell session before 'videodoc transcribe' (see RUN.md): $env:PATH = "<venv>\Lib\site-packages\nvidia\cublas\bin;<venv>\Lib\site-packages\nvidia\cudnn\bin;$env:PATH"
OK    Project registry: 3 project(s) registered -- ...
OK    Default projects folder: ... is writable
Re-checking automatically-fixed items...
WARN  GPU / CUDA: 1 CUDA device(s) detected but cublas64_12.dll could not be loaded: ...
```
(In questo esempio il solo `pip install` non risolve ancora — resta il passaggio manuale del `PATH`, mai automatizzato da `setup`; vedi `RUN.md` §8.)
**Vedi anche:** [features/doctor-setup.md](features/doctor-setup.md)
