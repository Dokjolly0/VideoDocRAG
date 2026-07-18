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

## sync-codebase

**Sintassi:** `videodoc sync-codebase <project>`
**Descrizione:** Sincronizza la cartella `codebase/` del progetto (interna o esterna), rispettando le esclusioni configurate in `scan:`, calcola hash dei file, rileva file aggiunti/modificati/rimossi, estrae snippet citabili e scrive `indexes/codebase_manifest.json` + `indexes/codebase_index.json`. L'indice codebase è ricercabile da `ask`/`chat` con `--source raw` o `--source hybrid`.
**Exit code:** 0 = sincronizzazione completata, skip idempotente, o nessuna codebase presente. 1 = progetto sconosciuto, `config.yaml` non valido, o errore di scrittura degli artefatti.
**Esempio:**
```
$ videodoc sync-codebase corso-software-x
Project: corso-software-x
+--------------------------------------------------------------+
| Synced   | yes                                                |
| Skipped  | no                                                 |
| Files    | 42                                                 |
| Snippets | 96                                                 |
| Added    | 42                                                 |
| Modified | 0                                                  |
| Removed  | 0                                                  |
| Manifest | .../indexes/codebase_manifest.json                 |
| Index    | .../indexes/codebase_index.json                    |
+--------------------------------------------------------------+
```
**Vedi anche:** [features/codebase-sync.md](features/codebase-sync.md)

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
**Descrizione:** Per ogni video con frame già estratti (`videodoc frames`), esegue l'OCR (motore RapidOCR) su ogni immagine frame, registra il testo riconosciuto e la relativa confidenza in `workdir/<id>/ocr/<id>.json` e nelle colonne `ocr_text`/`ocr_confidence` della tabella `frames` di `project.db`, aggiornando `metadata.json` (`ocr_path`). Non tocca mai `contains_code`/`perceptual_hash` (riservate rispettivamente a `videodoc code` e alla fase frame). Idempotente per **due** condizioni indipendenti: le impostazioni effettive salvate in `ocr.json` (`engine`/`languages`/`min_confidence`) devono coincidere con quelle correnti, **e** l'insieme di frame-id correnti deve coincidere con quello registrato nel manifest — un video con frame senza `videodoc frames` mai eseguito viene saltato silenziosamente (non è un errore). Un testo riconosciuto con confidenza sotto `min_confidence` viene comunque registrato (testo vuoto, confidenza reale conservata), per distinguere "OCR eseguito ma rumore" da "OCR mai eseguito" (quest'ultimo resta `NULL`).
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

## code

**Sintassi:** `videodoc code <project> [--workers N]`
**Descrizione:** Per ogni video con OCR già presente, classifica il testo dei frame in `plain_text`, `terminal_command`, `source_code`, `configuration`, `error_message`, `file_path` o `ui_label`; salva solo i blocchi code-like deduplicati in `workdir/<id>/code/<id>.json` e nella tabella `code_blocks`, aggiorna solo `frames.contains_code`, e rigenera `workdir/<id>/code/code_review_report.md` per i blocchi che richiedono controllo umano. JSON/YAML/Python vengono validati con parser reali; comandi, path ed errori usano regole deterministiche; altri linguaggi vengono classificati ma marcati per revisione in strict mode.
**Exit code:** 0 = successo, anche con errori per-video (manifest codice corrotto su un singolo video: stampato come `Warning`, gli altri continuano). 1 = progetto sconosciuto, `config.yaml` non valido, nessun video ancora registrato (`ingest` mai eseguito), o problema strutturale su `project.db`.
**Prerequisito:** richiede `videodoc ocr` per produrre input utili, ma non carica RapidOCR e non rilegge immagini; un video senza frame o senza OCR viene saltato silenziosamente. L'idempotenza confronta impostazioni `code.*` e firma completa degli input OCR (`frame_id`, timestamp, hash percettivo, hash del testo OCR e confidenza), quindi cambi di frame o OCR innescano una nuova analisi.
**Esempio:**
```
$ videodoc code corso-software-x
Project: corso-software-x
+---------------+
| Processed | 8 |
| Skipped   | 0 |
+---------------+

$ videodoc code corso-software-x
Project: corso-software-x
+---------------+
| Processed | 0 |
| Skipped   | 8 |
+---------------+
```
**Vedi anche:** [features/code-extraction.md](features/code-extraction.md)

---

## chunk

**Sintassi:** `videodoc chunk <project> [--workers N]`
**Descrizione:** Per ogni video con transcript, OCR o blocchi codice disponibili, crea chunk temporali arricchiti in `workdir/<id>/chunks/<id>.json`, sostituisce le righe del video nella tabella `chunks`, e aggiorna `metadata.json` (`chunks_path`). Il transcript guida i confini quando presente; OCR e code blocks vengono agganciati allo stesso intervallo. Ogni blocco codice genera anche un chunk separato `source_type="code"` per l'indicizzazione futura del codice come documento autonomo.
**Exit code:** 0 = successo, anche con errori per-video (manifest chunk corrotto su un singolo video: stampato come `Warning`, gli altri continuano). 1 = progetto sconosciuto, `config.yaml` non valido, nessun video ancora registrato (`ingest` mai eseguito), o problema strutturale su `project.db`.
**Prerequisito:** usa dati già prodotti da `transcribe`, `ocr` e `code`; un video senza nessuno di questi input viene saltato silenziosamente. L'idempotenza confronta impostazioni `chunking.*` e firme complete degli input transcript/frame/code, quindi cambi upstream innescano una nuova generazione.
**Esempio:**
```
$ videodoc chunk corso-software-x
Project: corso-software-x
+---------------+
| Processed | 8 |
| Skipped   | 0 |
+---------------+

$ videodoc chunk corso-software-x
Project: corso-software-x
+---------------+
| Processed | 0 |
| Skipped   | 8 |
+---------------+
```
**Vedi anche:** [features/chunking.md](features/chunking.md)

---

## embed

**Sintassi:** `videodoc embed <project> [--workers N]`
**Descrizione:** Per ogni video con manifest chunk già generato, crea embedding per `transcript`, `ocr`, `code`, `summary` e `combined`, salvandoli in `indexes/embeddings/<id>.json`. Il backend attuale è locale e deterministico (`feature-hashing`, 256 dimensioni): non scarica modelli, non richiede servizi esterni e registra comunque `config.embedding.provider`/`model` per idempotenza e upgrade futuri.
**Exit code:** 0 = successo, anche con errori per-video (manifest chunk/embedding corrotto su un singolo video: stampato come `Warning`, gli altri continuano). 1 = progetto sconosciuto, `config.yaml` non valido, nessun video ancora registrato (`ingest` mai eseguito), provider embedding non supportato, o problema strutturale su `project.db`.
**Prerequisito:** richiede `videodoc chunk` per produrre input utili; un video senza chunk viene saltato silenziosamente. Cambi ai chunk o a `config.embedding.*` innescano una nuova generazione.
**Esempio:**
```
$ videodoc embed corso-software-x
Project: corso-software-x
+---------------+
| Processed | 8 |
| Skipped   | 0 |
+---------------+

$ videodoc embed corso-software-x
Project: corso-software-x
+---------------+
| Processed | 0 |
| Skipped   | 8 |
+---------------+
```
**Vedi anche:** [features/embedding.md](features/embedding.md)

---

## index

**Sintassi:** `videodoc index <project>`
**Descrizione:** Legge i manifest embedding in `indexes/embeddings/<id>.json` e costruisce `indexes/vector_index.json`, un indice vettoriale locale (`backend: local-json`, distanza cosine) con un record per embedding e payload ricco pronto per la fase retrieval. `config.retrieval.vector_db` viene registrato come target configurato (default `qdrant`), ma il comando non richiede ancora Qdrant.
**Exit code:** 0 = successo o skip idempotente, anche con errori per-video su manifest embedding corrotti (stampati come `Warning`). 1 = progetto sconosciuto, `config.yaml` non valido, nessun video ancora registrato (`ingest` mai eseguito), vector DB configurato non supportato, o problema strutturale su `project.db`.
**Prerequisito:** richiede `videodoc embed` per produrre input utili; un progetto senza manifest embedding viene saltato senza errore.
**Esempio:**
```
$ videodoc index corso-software-x
Project: corso-software-x
+---------------+
| Indexed | yes |
| Skipped | no  |
| Videos  | 8   |
| Records | 120 |
+---------------+

$ videodoc index corso-software-x
Project: corso-software-x
+---------------+
| Indexed | no  |
| Skipped | yes |
| Videos  | 8   |
| Records | 120 |
+---------------+
```
**Vedi anche:** [features/vector-indexing.md](features/vector-indexing.md)

---

## index-docs

**Sintassi:** `videodoc index-docs <project>`
**Descrizione:** Indicizza esplicitamente le sezioni Markdown generate (`docs/[0-9][0-9]-*.md`) in `indexes/documentation_index.json`, usando lo stesso `DocumentationIndexService` richiamato automaticamente da `ask`/`chat` in modalità `docs`. I payload hanno `source_type="generated_documentation"` e includono i riferimenti video/timestamp letti da `docs/sources/*.sources.json`, quando presenti.
**Exit code:** 0 = indice scritto, anche con zero sezioni (indice vuoto). 1 = progetto sconosciuto, `config.yaml` non valido, indice/documentazione non leggibile, o errore di scrittura.
**Esempio:**
```
$ videodoc index-docs corso-software-x
Project: corso-software-x
+------------------------------------------------+
| Records | 8                                    |
| Inputs  | 1                                    |
| Index   | .../indexes/documentation_index.json |
+------------------------------------------------+
```
**Vedi anche:** [features/chat.md](features/chat.md)

---

## ask

**Sintassi:** `videodoc ask <project> "domanda" [--source docs|raw|hybrid] [--video NAME]... [--from HH:MM:SS] [--to HH:MM:SS] [--top-k N]`
**Descrizione:** Interroga la knowledge base in modalità one-shot. `--source docs` (default) usa la documentazione generata indicizzata in `indexes/documentation_index.json`; `raw` usa `indexes/vector_index.json` e/o `indexes/codebase_index.json`; `hybrid` combina documentazione, chunk raw e snippet codebase. I filtri `--video`, `--from` e `--to` limitano le fonti video recuperate. La risposta resta estrattiva e cita solo fonti recuperate.
**Exit code:** 0 = risposta prodotta o nessuna fonte sufficiente trovata. 1 = progetto sconosciuto, `config.yaml` non valido, indici mancanti (`run 'videodoc generate'`/`index` first), indice corrotto/non ricercabile localmente, timecode non valido, fonte non valida, o domanda vuota.
**Prerequisito:** per `docs` servono sezioni generate; per `raw` serve `videodoc index` e/o `videodoc sync-codebase`. Se `docs` non ha ancora sezioni ma esiste un indice raw/codebase, `ask` usa automaticamente quelle fonti per mantenere interrogabile una pipeline parziale.
**Esempio:**
```
$ videodoc ask corso-software-x "Come si configura il database?" --top-k 3
Project: corso-software-x
Answer:
Risposta basata solo sulle fonti recuperate:
- La configurazione del database viene mostrata nel file config.yaml ... [1]
Sources:
[1] workshop_03_database.mp4 00:12:10-00:18:45 score=0.842 chunk=workshop_03_database_chunk_0004 type=combined source=transcript topic=Database
    La configurazione del database viene mostrata nel file config.yaml ...
```
**Vedi anche:** [features/retrieval-rag.md](features/retrieval-rag.md)

---

## chat

**Sintassi:** `videodoc chat <project> [--message "domanda"] [--session ID] [--source docs|raw|hybrid] [--video NAME]... [--from HH:MM:SS] [--to HH:MM:SS] [--top-k N]`
**Descrizione:** Avvia una chat salvata sul progetto. Senza `--message` entra in modalità interattiva; con `--message` invia un turno e termina. In modalità `raw`/`hybrid` interroga anche `indexes/codebase_index.json` quando `videodoc sync-codebase` è stato eseguito. Ogni turno viene salvato in `project.db` (`chat_sessions`, `chat_messages`) e in `sessions/<session_id>.json`. Le sessioni esistenti si continuano con `--session`.
**Exit code:** 0 = turno completato o sessione interattiva chiusa. 1 = progetto sconosciuto, `config.yaml` non valido, indici mancanti, indice corrotto, timecode/fonte non valido, o domanda vuota.
**Esempio:**
```
$ videodoc chat corso-software-x --message "Come si configura il database?" --source hybrid
Project: corso-software-x
Session: chat_20260718T215705_ab28b6bb
Answer:
Risposta basata solo sulle fonti recuperate:
- La configurazione del database ... [1]
Sources:
[1] docs/04-configurazione-database.md score=0.812 type=generated_documentation section=Configurazione database
    # Configurazione database ...
```
**Vedi anche:** [features/chat.md](features/chat.md)

---

## status

**Sintassi:** `videodoc status <project>`
**Descrizione:** Mostra una vista non distruttiva dello stato pipeline del progetto: fonti scansionate, video registrati, audio, trascrizioni, frame, OCR, codice, chunk, embedding, indici, documentazione, export e chat salvate. Il comando legge manifest, file e `project.db`; non crea tabelle né modifica artefatti.
**Exit code:** 0 = riepilogo stampato. 1 = progetto sconosciuto, `config.yaml` non valido, o problema strutturale su `project.db` (es. `project.db` è una cartella).
**Esempio:**
```
$ videodoc status corso-software-x
Project: corso-software-x
+----------------------+--------------------------------------------------+
| Path                 | .../corso-software-x                             |
| Sources scan         | yes (videos=8, attachments=3, codebase_files=42) |
| Videos               | 8                                                |
| Audio extracted      | 8/8                                              |
| Transcribed          | 8/8                                              |
| Frames extracted     | 8/8                                              |
| OCR completed        | 7/8                                              |
| Code extracted       | 7/8                                              |
| Chunks generated     | 8/8                                              |
| Embeddings generated | 8/8                                              |
| Raw index            | yes (512 records, 8 inputs)                      |
| Codebase index       | yes (96 records, 1 inputs)                       |
| Documentation index  | yes (8 records, 8 inputs)                        |
| Documentation        | outline=yes, sections=8, sources=8, review=yes, exports=mkdocs |
| Chat sessions        | 3                                                |
+----------------------+--------------------------------------------------+
```
**Vedi anche:** [features/status-inspect.md](features/status-inspect.md)

---

## inspect

**Sintassi:** `videodoc inspect <project> --timestamp HH:MM:SS [--video NAME]`
**Descrizione:** Ispeziona un timestamp e mostra il contesto grezzo più vicino o direttamente collegato: segmento transcript, frame, OCR del frame, blocchi codice vicini, chunk e sezioni Markdown che citano quel range. `--video` accetta id video, nome file o stem del nome file; se il progetto contiene un solo video può essere omesso.
**Exit code:** 0 = contesto stampato. 1 = progetto sconosciuto, `config.yaml` non valido, nessun video registrato, timestamp non valido, selettore video mancante/ambiguo/sconosciuto, o problema strutturale su `project.db`.
**Esempio:**
```
$ videodoc inspect corso-software-x --video workshop_01.mp4 --timestamp 00:21:04
Project: corso-software-x
+--------------------+--------------------------------------------------+
| Video              | workshop_01.mp4 (workshop_01)                  |
| Timestamp          | 00:21:04                                        |
| Transcript         | 00:21:00-00:21:10, confidence 0.94: Ora lanciamo il comando... |
| Frame              | workdir/workshop_01/frames/frame_0042.jpg @00:21:04 (distance 0.0s) |
| OCR                | npm create vite@latest my-app (confidence 0.91) |
| Chunk              | workshop_01_chunk_0008 00:20:30-00:22:00 Installazione |
| Documentation hits | 1                                                |
+--------------------+--------------------------------------------------+
Detected code:
- workshop_01_code_0003 bash @00:21:04 distance=0.0s
  npm create vite@latest my-app
Documentation:
- docs/03-installazione.md [2] Installazione 00:20:30-00:22:00 Installazione
```
**Vedi anche:** [features/status-inspect.md](features/status-inspect.md)

---

## outline

**Sintassi:** `videodoc outline <project> [--force]`
**Descrizione:** Genera `docs/outline.md`, un indice Markdown modificabile manualmente prima della futura generazione sezioni. Usa video registrati, chunk (`topic`, `summary`, transcript/OCR), blocchi codice e, quando disponibile, `sources.yaml` per allegati e codebase. Se `docs/outline.md` esiste già, lo preserva e segnala skip; `--force` lo rigenera.
**Exit code:** 0 = outline generato o preservato. 1 = progetto sconosciuto, `config.yaml` non valido, nessun video ancora registrato (`ingest` mai eseguito), nessun chunk disponibile (`run 'videodoc chunk' first`), o problema strutturale su `project.db`.
**Prerequisito:** richiede `videodoc chunk` per produrre fonti strutturate utili.
**Esempio:**
```
$ videodoc outline corso-software-x
Project: corso-software-x
+----------------------------------------------+
| Generated | yes                              |
| Skipped   | no                               |
| Sections  | 8                                |
| Outline   | .../corso-software-x/docs/outline.md |
+----------------------------------------------+
```
**Vedi anche:** [features/documentation-outline.md](features/documentation-outline.md)

---

## generate

**Sintassi:** `videodoc generate <project> [--force] [--top-k N]`
**Descrizione:** Legge `docs/outline.md`, recupera chunk pertinenti da `indexes/vector_index.json` per ogni sezione, collega i blocchi codice in `project.db`, e scrive un file Markdown per sezione (`docs/<NN>-<slug>.md`) più un manifest fonti (`docs/sources/<NN>-<slug>.sources.json`). Il backend attuale è estrattivo e locale: non chiama ancora un LLM e non inventa contenuto non presente nelle fonti recuperate.
**Exit code:** 0 = sezioni generate o preservate. 1 = progetto sconosciuto, `config.yaml` non valido, outline mancante (`run 'videodoc outline' first`), indice vettoriale mancante (`run 'videodoc index' first`), indice corrotto/non ricercabile, nessun video registrato, o problema strutturale su `project.db`.
**Prerequisito:** richiede `videodoc outline` e `videodoc index`; `videodoc chunk`/`embed` restano prerequisiti indiretti dell'indice.
**Esempio:**
```
$ videodoc generate corso-software-x --top-k 6
Project: corso-software-x
+-------------+
| Generated | 8 |
| Skipped   | 0 |
+-------------+
Generated: .../corso-software-x/docs/01-introduzione.md
```
**Vedi anche:** [features/markdown-generation.md](features/markdown-generation.md)

---

## regenerate

**Sintassi:** `videodoc regenerate <project> --section SECTION [--top-k N]`
**Descrizione:** Rigenera una sola sezione già definita in `docs/outline.md`, identificandola per titolo, slug o numero outline (`1`, `01`). Usa lo stesso motore di `generate` con `force=True`, quindi riscrive solo `docs/<NN>-<slug>.md` e il relativo manifest `docs/sources/<NN>-<slug>.sources.json`, preservando tutte le altre sezioni modificate a mano.
**Exit code:** 0 = sezione rigenerata. 1 = progetto sconosciuto, `config.yaml` non valido, outline mancante, sezione non trovata/ambigua, indice vettoriale mancante o corrotto, nessun video registrato, o problema strutturale su `project.db`.
**Prerequisito:** richiede gli stessi prerequisiti di `generate`: `videodoc outline` e `videodoc index`.
**Esempio:**
```
$ videodoc regenerate corso-software-x --section "Configurazione database"
Project: corso-software-x
+---------------+
| Regenerated | 1 |
| Skipped     | 0 |
+---------------+
Regenerated: .../docs/04-configurazione-database.md
```
**Vedi anche:** [features/markdown-generation.md](features/markdown-generation.md)

---

## review

**Sintassi:** `videodoc review <project>`
**Descrizione:** Controlla le sezioni generate (`docs/[0-9][0-9]-*.md`) e i rispettivi manifest `docs/sources/*.sources.json`, verifica struttura Markdown, fonti, video, timestamp, citazioni, overlap con i testi indicizzati, duplicati di codice e classificazione dei blocchi codice. Scrive `docs/review_report.md` e `docs/review_report.json`; non modifica i Markdown.
**Exit code:** 0 = review completata, anche se il report contiene issue da correggere. 1 = progetto sconosciuto, `config.yaml` non valido, nessuna sezione generata (`run 'videodoc generate' first`), manifest review/section corrotto, indice vettoriale corrotto, o errore di scrittura report.
**Prerequisito:** richiede `videodoc generate`; l'indice vettoriale consente il controllo anti-allucinazione con overlap lessicale sui record sorgente.
**Esempio:**
```
$ videodoc review corso-software-x
Project: corso-software-x
+----------------------------------------------+
| Sections | 8                                |
| Issues   | 0                                |
| Errors   | 0                                |
| Warnings | 0                                |
| Report   | .../corso-software-x/docs/review_report.md |
+----------------------------------------------+
```
**Vedi anche:** [features/documentation-review.md](features/documentation-review.md)

---

## export

**Sintassi:** `videodoc export <project> [--format markdown|mkdocs|docusaurus|github-pages|pdf|html]`
**Descrizione:** Esporta le sezioni generate da `docs/` in `exports/<format>/`. Il formato `markdown` copia i Markdown generati; `mkdocs` crea `mkdocs.yml` e `docs/index.md`; `docusaurus` crea uno scaffold minimale; `html` e `github-pages` creano pagine HTML statiche; `github-pages` aggiunge `.nojekyll`; `pdf` crea un PDF testuale semplice e locale.
**Exit code:** 0 = export completato. 1 = progetto sconosciuto, `config.yaml` non valido, formato non supportato, nessuna sezione generata (`run 'videodoc generate' first`), o errore di scrittura/copia.
**Prerequisito:** richiede `videodoc generate`.
**Esempio:**
```
$ videodoc export corso-software-x --format mkdocs
Project: corso-software-x
+-----------------------------+
| Format | mkdocs             |
| Files  | 10                 |
| Output | .../exports/mkdocs |
+-----------------------------+
```
**Vedi anche:** [features/documentation-export.md](features/documentation-export.md)

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
