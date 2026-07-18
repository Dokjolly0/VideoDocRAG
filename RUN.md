# VideoDocRAG — Guida all'esecuzione

Questa guida spiega come installare ed eseguire VideoDocRAG così com'è oggi (Step 1: gestione progetti — `init`, `list`, `link`, `unlink`, `path`; Step 2: scansione delle fonti — `scan`, percorsi sorgente esterni; Step 3: ingestion dei video — `ingest`; Step 4: estrazione audio — `extract-audio`; Step 5: trascrizione audio — `transcribe`; Step 6: estrazione frame — `frames`; Step 7: OCR degli screenshot — `ocr`; più `doctor`/`setup`, diagnostica e correzione guidata dell'ambiente) su **Windows, Linux o macOS**. Per l'elenco completo di ogni comando con sintassi ed esempio di output, vedi [`docs/commands.md`](docs/commands.md). Le fasi successive della pipeline (riconoscimento del codice, RAG, generazione documentazione, chat — vedi `README.md`) non sono ancora implementate.

Ogni sezione con un comando che differisce tra sistemi operativi mostra un blocco **Windows (PowerShell)** e un blocco **Linux/macOS (bash/zsh)** affiancati — i due comandi di shell sono praticamente identici su Linux e macOS, quindi condividono lo stesso blocco salvo dove specificato diversamente.

## Indice

1. [Prerequisiti](#1-prerequisiti)
2. [Nota importante: quale Python usare](#2-nota-importante-quale-python-usare)
3. [Setup iniziale dell'ambiente](#3-setup-iniziale-dellambiente)
4. [Attivare l'ambiente nelle sessioni successive](#4-attivare-lambiente-nelle-sessioni-successive)
5. [Comandi disponibili](#5-comandi-disponibili)
6. [Personalizzare i percorsi (variabili d'ambiente)](#6-personalizzare-i-percorsi-variabili-dambiente)
7. [Eseguire i test](#7-eseguire-i-test)
8. [Risoluzione problemi](#8-risoluzione-problemi)
9. [Cosa non è ancora disponibile](#9-cosa-non-è-ancora-disponibile)

---

## 1. Prerequisiti

- Windows, Linux o macOS, con un terminale (PowerShell su Windows; bash/zsh su Linux/macOS).
- Python 3.11 o superiore.
- Nessuna dipendenza esterna richiesta per `init`/`scan`/`list`/`link`/`unlink`/`path` (niente Ollama, FFmpeg, Qdrant: servono solo dalle fasi successive della pipeline).
- **`ffprobe` e `ffmpeg` (entrambi parte di FFmpeg) sono richiesti rispettivamente da `videodoc ingest`** (Step 3) **e `videodoc extract-audio`** (Step 4) — sono i primi due comandi che hanno bisogno di uno strumento esterno. Una singola installazione di FFmpeg fornisce entrambi i binari:

  **Windows (PowerShell):**
  ```powershell
  winget install Gyan.FFmpeg
  # oppure: choco install ffmpeg
  ```

  **Linux (bash):**
  ```bash
  sudo apt install ffmpeg   # Debian/Ubuntu; usa il gestore pacchetti della tua distro
  ```

  **macOS (zsh):**
  ```bash
  brew install ffmpeg
  ```

  Verifica che entrambi siano disponibili in `PATH`:

  ```bash
  ffprobe -version
  ffmpeg -version
  ```

- **`faster-whisper`, richiesto da `videodoc transcribe`** (Step 5), è una dipendenza Python normale: viene installata automaticamente da `pip install -e ".[dev]"` (§3), nessun passo manuale aggiuntivo. Al **primo utilizzo reale** di `transcribe`, scarica da Hugging Face il modello configurato in `config.yaml` (`transcription.model`, default `large-v3`, diversi GB) — la prima esecuzione può richiedere tempo e spazio su disco significativi, soprattutto su CPU senza GPU dedicata. Vedi §8 per un problema noto relativo al rilevamento hardware.

## 2. Nota importante: quale Python usare

### Windows

Digitare `python` può risolvere a build diverse. **Evita la build "Microsoft Store"** di Python (quella installata dal Microsoft Store, tipicamente con percorso tipo `...\AppData\Local\Microsoft\WindowsApps\python.exe` o `...\Packages\PythonSoftwareFoundation.Python.3.13_...`): Windows applica a queste build una virtualizzazione del filesystem che reindirizza silenziosamente le scritture sotto `%LOCALAPPDATA%` in una cartella privata del pacchetto, invisibile a PowerShell, Esplora File o altri programmi. VideoDocRAG scrive proprio lì il registro locale dei progetti (vedi §6), quindi con la build Store rischi di non trovare più i file che il programma dice di aver creato.

Verifica quale Python useresti:

```powershell
where python
py -0p
```

Se `where python` punta a `WindowsApps` o a un percorso `Packages\PythonSoftwareFoundation...`, installa la build ufficiale da [python.org](https://www.python.org/downloads/) oppure con:

```powershell
winget install Python.Python.3.13
```

e usa il suo percorso esplicito (es. `C:\Users\<utente>\AppData\Local\Programs\Python\Python313\python.exe`) per creare il virtual environment al passo successivo, anche se non è la prima voce in `PATH`.

### Linux/macOS

Non è nota nessuna virtualizzazione del filesystem paragonabile a quella di Windows Store. Il Python di sistema o quello installato tramite il gestore pacchetti della distribuzione (`apt`, `dnf`, ...) o `pyenv` su Linux, `brew install python@3.13` o `pyenv` su macOS, è normalmente sufficiente — usa semplicemente `python3` (su molte distribuzioni `python` senza suffisso non è garantito puntare a Python 3).

```bash
python3 --version
which python3
```

## 3. Setup iniziale dell'ambiente

Da eseguire una sola volta (o ogni volta che si vuole un ambiente pulito).

**Windows (PowerShell):**

```powershell
cd D:\Projects\VideoDocRAG

# Usa l'interprete ufficiale trovato al passo 2. Sostituisci il percorso se diverso.
& "C:\Users\<utente>\AppData\Local\Programs\Python\Python313\python.exe" -m venv .venv

.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

**Linux/macOS (bash/zsh):**

```bash
cd ~/Projects/VideoDocRAG

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Verifica che l'installazione sia andata a buon fine (identico su tutti gli OS, venv attivo):

```bash
videodoc --help
```

Output atteso:

```text
Usage: videodoc [OPTIONS] COMMAND [ARGS]...

 VideoDocRAG command-line interface.

+- Commands ------------------------------------------------------------------+
| init                                                                        |
| list                                                                        |
| link                                                                        |
| unlink                                                                      |
| path                                                                        |
| scan                                                                        |
+-----------------------------------------------------------------------------+
```

## 4. Attivare l'ambiente nelle sessioni successive

Non serve rifare il setup ogni volta: in una nuova finestra di terminale basta riattivare il venv già creato.

**Windows (PowerShell):**

```powershell
cd D:\Projects\VideoDocRAG
.venv\Scripts\Activate.ps1
```

**Linux/macOS (bash/zsh):**

```bash
cd ~/Projects/VideoDocRAG
source .venv/bin/activate
```

Per uscire dal virtual environment a fine sessione (identico ovunque):

```bash
deactivate
```

## 5. Comandi disponibili

I comandi `videodoc ...` sono identici su tutti gli OS (Python multipiattaforma) — solo i percorsi passati come argomento cambiano sintassi. Gli esempi sotto mostrano entrambe le forme dove rilevante.

### 5.1 Creare un nuovo progetto

Nel percorso di default (fuori dalla cartella del programma, vedi README §8.1.2):

```bash
videodoc init corso-software-x
```

```text
Project 'corso-software-x' initialized at <home>/VideoDocRAG/projects/corso-software-x
Registered as 'corso-software-x' in the local project registry.
```

In un percorso a scelta:

```powershell
# Windows
videodoc init corso-software-x --path "D:\Corsi\corso-software-x"
```

```bash
# Linux/macOS
videodoc init corso-software-x --path "/home/utente/Corsi/corso-software-x"
```

**Video (o allegati, o codebase) già presenti altrove sul disco**: non serve copiarli dentro il progetto. `--videos`/`--attachments`/`--codebase` impostano un percorso esterno, referenziato non copiato (stesso principio dei "media collegati" di un editor video). Un valore assoluto è sempre nella sintassi nativa dell'OS che eseguirà VideoDocRAG — un percorso assoluto è per natura un dato specifico della macchina, non è richiesta né garantita portabilità dello stesso valore tra OS diversi:

```powershell
# Windows
videodoc init corso-software-x --videos "D:\Corsi\Registrazioni"
```

```bash
# Linux/macOS
videodoc init corso-software-x --videos "/mnt/corsi/registrazioni"
```

Questi tre flag hanno effetto **solo alla prima creazione** del progetto: se rilanciati su un progetto già esistente vengono ignorati con un avviso esplicito (`config.yaml` non viene mai sovrascritto), non silenziosamente scartati:

```text
Project 'corso-software-x' already initialized at ... (config.yaml kept unchanged)
Warning: --videos ignored: config.yaml already exists and 'init' never overwrites it.
```

Un progetto con sorgenti esterne non è più interamente autocontenuto: spostare la cartella del progetto non porta con sé i video/allegati/codebase esterni (che restano dove sono). È una scelta consapevole — l'isolamento dei dati generati (`project.db`, indice Qdrant) resta comunque garantito, solo i materiali sorgente possono vivere altrove.

Rilanciare `init` sullo stesso progetto è sicuro: non sovrascrive un `config.yaml` già esistente, riporta solo lo stato ("already initialized").

Struttura creata (identica su tutti gli OS):

```text
corso-software-x/
├── config.yaml
├── sources.yaml
├── videos/          # obbligatoria: qui vanno messi i video da elaborare
├── attachments/     # opzionale
├── codebase/        # opzionale
├── workdir/
├── indexes/
├── sessions/
└── docs/
```

### 5.2 Elencare i progetti registrati

```bash
videodoc list
```

```text
+-----------------------------------------------------------------------------+
| Name              | Path                              | Created at         |
|-------------------+------------------------------------+--------------------|
| corso-software-x  | /home/utente/Corsi/corso-software-x | 2026-07-09T14:00:25 |
+-----------------------------------------------------------------------------+
```

Se non ci sono progetti registrati, il comando lo dice esplicitamente e suggerisce `init`/`link`.

### 5.3 Ottenere il percorso assoluto di un progetto

Utile per script o per navigare rapidamente:

```powershell
# Windows
videodoc path corso-software-x
cd (videodoc path corso-software-x)
```

```bash
# Linux/macOS
videodoc path corso-software-x
cd "$(videodoc path corso-software-x)"
```

### 5.4 Registrare un progetto esistente (creato o spostato a mano)

Se una cartella progetto (con un `config.yaml` valido) esiste già ma non è nel registro locale — per esempio dopo averla spostata, copiata da un altro PC, o clonata da un backup:

```bash
videodoc link "/home/utente/Corsi/corso-software-x"
```

`--name` registra il progetto sotto un **alias locale esplicito**, diverso dallo slug canonico presente nel suo `config.yaml` — utile per risolvere una collisione locale tra due progetti il cui slug coincide per caso, o per usare un nickname più corto. Non modifica mai il `config.yaml` del progetto: l'identità "vera" resta quella scritta lì. L'alias viene comunque normalizzato con le stesse regole dello slug (niente spazi/maiuscole/punteggiatura nel registro), e il comando lo segnala esplicitamente in output quando differisce dallo slug reale:

```bash
videodoc link "/home/utente/Corsi/corso-software-x" --name "Alias Locale!!"
# Linked as alias 'alias-locale' -> /home/utente/Corsi/corso-software-x (the project's own slug is 'corso-software-x')
```

Se invece non lo differenzi mai, il comando registra semplicemente con lo slug canonico e lo dice senza menzionare alcun alias:

```bash
videodoc link "/home/utente/Corsi/corso-software-x"
# Linked 'corso-software-x' -> /home/utente/Corsi/corso-software-x
```

### 5.5 Rimuovere un progetto dal registro (senza cancellare i file)

```bash
videodoc unlink corso-software-x
```

Questo comando **non cancella mai i file del progetto**: agisce solo sul registro locale. Per riaverlo disponibile basta rilanciare `videodoc link <percorso>`.

### 5.6 Scansionare le fonti di un progetto

Enumera video, allegati e codebase (interni o esterni) e scrive `sources.yaml`:

```bash
videodoc scan corso-software-x
```

```text
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

Se una sorgente è esterna, viene segnalata esplicitamente nella stessa cella:

```text
| Videos | 8 found (external: /mnt/corsi/registrazioni) |
```

Zero video trovati **non** fa fallire il comando (`exit code` resta `0`): sarà una fase successiva (ingestion) a rifiutarsi di procedere senza video, non lo scan. Allo stesso modo, una sorgente esterna mancante (es. un'unità scollegata, o un mount point non montato su Linux/macOS) o che punta a un file invece che a una cartella produce solo un avviso, mai un crash:

```text
Warning: external videos path not found: /mnt/corsi/registrazioni
```

Le esclusioni si basano sulla sezione `scan:` di `config.yaml` (default già ragionevoli — `.git/`, `node_modules/`, `__pycache__/`, ecc. — personalizzabili con `add_excludes`/`remove_excludes`, vedi README §8.3). `sources.yaml` viene **sempre rigenerato per intero** a ogni scan, mai preservato: rilanciarlo dopo aver aggiunto un video aggiorna semplicemente il manifest.

### 5.7 Registrare (ingest) i video di un progetto

Usa un fingerprint rapido (`size` + `mtime` + `inode`) per saltare i video invariati senza rileggerli, calcola l'hash SHA-256 quando serve (o sempre con `--verify`), estrae durata/formato/risoluzione/codec con `ffprobe` (vedi §1 per l'installazione), registra in `project.db` e crea `workdir/<id>/{audio,frames,transcript,ocr,chunks}/` + `metadata.json`:

```bash
videodoc ingest corso-software-x
```

```text
Project: corso-software-x
+----------------+
| Ingested   | 8 |
| Reingested | 0 |
| Skipped    | 0 |
+----------------+
Database updated: project.db
```

È idempotente per contenuto: un video invariato viene saltato tramite fingerprint rapido (senza hash completo né `ffprobe`); un video modificato viene riprocessato e genera un avviso, non un errore, sui possibili artefatti obsoleti nelle sue sottocartelle (mai cancellate automaticamente):

```text
Warning: workshop-05: video content changed and was reingested -- workdir/workshop-05/{audio,frames,transcript,ocr,chunks} may still contain artifacts from the previous version (never deleted automatically); re-run the relevant pipeline phase(s) to refresh them.
```

A differenza di `scan`, **zero video trovati fa fallire `ingest`** (`exit code` 1): è il primo comando della pipeline vera e propria, e README §15.1 richiede che un progetto senza video non possa avviarla. Se `ffprobe` non è disponibile in `PATH`, `ingest` fallisce subito, senza creare `project.db` né alcuna cartella.

### 5.8 Estrarre l'audio dai video di un progetto

Per ogni video già registrato con `ingest`, estrae l'audio in WAV mono a 16kHz (via `ffmpeg`, vedi §1 per l'installazione) in `workdir/<id>/audio/<id>.wav` e aggiorna `metadata.json`:

```bash
videodoc extract-audio corso-software-x
```

```text
Project: corso-software-x
+---------------+
| Extracted | 8 |
| Skipped   | 0 |
+---------------+
```

È idempotente per presenza del file: rilanciandolo, i video già estratti vengono saltati senza richiamare `ffmpeg`:

```bash
videodoc extract-audio corso-software-x
```

```text
Project: corso-software-x
+---------------+
| Extracted | 0 |
| Skipped   | 8 |
+---------------+
```

Se nessun video è ancora stato registrato (`ingest` non è mai stato eseguito) o se `ffmpeg` non è disponibile in `PATH`, il comando fallisce subito (`exit code` 1) senza creare o modificare nulla. Un problema di estrazione su un singolo video (es. codec non supportato) non blocca gli altri: viene segnalato con un `Warning`, il comando resta a `exit code` 0.

### 5.9 Trascrivere l'audio di un progetto

Per ogni video con audio già estratto, trascrive con `faster-whisper` (vedi §1 per la nota sul download del modello) in `workdir/<id>/transcript/<id>.json` e nella tabella `transcript_segments` di `project.db`, aggiornando `metadata.json`:

```bash
videodoc transcribe corso-software-x
```

```text
Project: corso-software-x
+-----------------+
| Transcribed | 8 |
| Skipped     | 0 |
+-----------------+
```

È idempotente per presenza del file: rilanciandolo, i video già trascritti vengono saltati senza richiamare il motore di trascrizione (il modello, potenzialmente pesante da caricare, non viene nemmeno inizializzato se non c'è nulla da fare):

```bash
videodoc transcribe corso-software-x
```

```text
Project: corso-software-x
+-----------------+
| Transcribed | 0 |
| Skipped     | 8 |
+-----------------+
```

Se nessun video ha ancora l'audio estratto (`extract-audio` non è mai stato eseguito), il comando fallisce subito (`exit code` 1) senza caricare alcun modello. Un problema di trascrizione su un singolo video non blocca gli altri: viene segnalato con un `Warning`, il comando resta a `exit code` 0 — vedi §8 per un caso reale (libreria CUDA mancante) riscontrato durante lo sviluppo. Su GPU NVIDIA, `auto` usa CUDA, modalità batched, VAD e `beam_size: 1`; `compute_type` e `batch_size` vengono calcolati dalla VRAM dedicata libera, mai dalla memoria GPU condivisa di Windows.

### 5.10 Estrarre i frame (screenshot) dai video di un progetto

Per ogni video già registrato con `ingest`, estrae i frame in `workdir/<id>/frames/frame_NNNN.jpg` (via `ffmpeg`, vedi §1 per l'installazione) e li registra in `workdir/<id>/frames/frames.json` e nella tabella `frames` di `project.db`, aggiornando `metadata.json`:

```bash
videodoc frames corso-software-x
```

```text
Project: corso-software-x
+---------------+
| Extracted | 8 |
| Skipped   | 0 |
+---------------+
```

I timestamp da cui estrarre i frame combinano tre segnali: un intervallo fisso (`frames.interval_seconds`, default 8s), i cambi scena rilevati direttamente da FFmpeg (`select=gt(scene\,threshold)`, default `frames.scene_threshold=0.10`) e i segmenti della trascrizione che contengono parole chiave come "codice"/"comando"/"terminale"/"errore" (README sezione 18.3) se `videodoc transcribe` e gia stato eseguito per quel video. Un frame boosted (cambio scena o parola chiave) visivamente quasi identico al frame precedente viene scartato tramite un hash percettivo, per non salvare screenshot ridondanti.

E idempotente per presenza di `frames.json` **con le stesse impostazioni effettive** (intervallo, scene detection, keyword boost e, se la scene detection e attiva, scene threshold - salvate dentro `frames.json` stesso): rilanciandolo con le stesse opzioni, i video gia processati vengono saltati senza richiamare `ffmpeg`:

```bash
videodoc frames corso-software-x
```

```text
Project: corso-software-x
+---------------+
| Extracted | 0 |
| Skipped   | 8 |
+---------------+
```

**Attenzione:** se rilanci il comando con impostazioni semantiche diverse (es. `--interval-seconds`, `--scene-detection`/`--no-scene-detection`, `--keyword-boost`/`--no-keyword-boost` o `--scene-threshold` quando la scene detection e attiva), i video interessati **non vengono saltati**: vengono ri-estratti da zero con le nuove impostazioni, sostituendo i frame precedenti. `--hwaccel` non conta per l'idempotenza: puoi passare da `--hwaccel auto` a `--hwaccel none` senza forzare una ri-estrazione.

`ffmpeg` viene richiesto solo se **almeno un video** necessita davvero di una nuova estrazione: un progetto gia completamente processato (ogni video con `frames.json` corrispondente alle impostazioni correnti) puo essere rilanciato per autoripararsi (`project.db`/`metadata.json`) anche su una macchina priva di FFmpeg.

Se nessun video e ancora stato registrato (`ingest` non e mai stato eseguito), se `ffmpeg` non e disponibile in `PATH` quando serve, o se c'e un problema strutturale su `project.db`, il comando fallisce subito (`exit code` 1) senza creare o modificare nulla. Un problema di estrazione o scene detection su un singolo video, o un'estrazione che non produce nemmeno un frame utilizzabile, non blocca gli altri video: viene segnalato con un `Warning`, il comando resta a `exit code` 0. La scene detection e il keyword boost si disattivano con `--no-scene-detection`/`--no-keyword-boost`; l'assenza di una trascrizione per un video non e un errore, contribuisce semplicemente zero frame extra da parole chiave.

`--hwaccel auto` usa CUDA solo se FFmpeg la espone, il probe GPU riesce e c'e uno slot GPU libero; altrimenti usa CPU. `--hwaccel cuda` tenta CUDA e ritenta una volta su CPU se la passata fallisce. `--hwaccel none` forza CPU.
### 5.11 Eseguire l'OCR sugli screenshot di un progetto

Per ogni video con frame già estratti (`videodoc frames`), esegue l'OCR (motore RapidOCR) su ogni immagine frame e registra testo/confidenza in `workdir/<id>/ocr/<id>.json` e nelle colonne `ocr_text`/`ocr_confidence` della tabella `frames` di `project.db`, aggiornando `metadata.json`:

```bash
videodoc ocr corso-software-x
```

```text
Project: corso-software-x
+---------------+
| Processed | 8 |
| Skipped   | 0 |
+---------------+
```

Non modifica mai `contains_code`/`perceptual_hash`: `contains_code` resta riservato alla fase di riconoscimento del codice (`videodoc code`, README §20).

È idempotente per **due** condizioni indipendenti: le impostazioni effettive salvate in `ocr.json` (motore, lingue, soglia di confidenza) devono coincidere con quelle correnti, **e** l'insieme di frame-id correnti (dalla tabella `frames`) deve coincidere con quello registrato nel manifest. Questa seconda condizione è specifica di questa fase: se `videodoc frames` viene rieseguito producendo un insieme di frame diverso (es. un `--interval-seconds` più stretto), il video viene sottoposto di nuovo a OCR anche se nessuna impostazione OCR è cambiata:

```bash
videodoc ocr corso-software-x
```

```text
Project: corso-software-x
+---------------+
| Processed | 0 |
| Skipped   | 8 |
+---------------+
```

Un video con frame di cui non è mai stato eseguito `videodoc frames` (o che ne ha prodotti zero) viene saltato silenziosamente, senza errore. Un testo riconosciuto con confidenza sotto `ocr.min_confidence` (default 0.65) viene comunque registrato con testo vuoto e la confidenza reale conservata, per distinguere "OCR eseguito ma rumore a bassa confidenza" da "OCR mai eseguito su questo frame" (quest'ultimo resta `NULL`, e viene ritentato automaticamente al run successivo).

`rapidocr`/`onnxruntime` sono installati automaticamente come dipendenze del progetto (nessun passo manuale, a differenza di FFmpeg) e vengono richiesti solo se **almeno un video** necessita davvero di un nuovo OCR: un progetto già completamente processato può essere rilanciato per autoripararsi anche su una macchina priva di `rapidocr`. Se nessun video è ancora stato registrato, o se il pacchetto `rapidocr` non è installato quando serve, il comando fallisce subito (`exit code` 1). Un fallimento OCR su un singolo frame non blocca gli altri: viene segnalato con un `Warning`, quel frame viene ritentato al run successivo.

### 5.12 Riconoscere ed estrarre il codice dall'OCR

Per ogni video con risultati OCR già presenti, classifica il testo dei frame, identifica comandi, sorgenti, configurazioni, errori e path, deduplica i blocchi uguali e li registra in `workdir/<id>/code/<id>.json`, nella tabella `code_blocks` di `project.db` e nel flag `frames.contains_code`:

```bash
videodoc code corso-software-x
```

```text
Project: corso-software-x
+---------------+
| Processed | 8 |
| Skipped   | 0 |
+---------------+
```

Il comando non rilegge immagini e non richiama RapidOCR: usa solo `ocr_text`/`ocr_confidence` già salvati da `videodoc ocr`. Un video senza frame o senza OCR viene saltato senza errore. Ogni run fresco scrive anche `workdir/<id>/code/code_review_report.md`, con i blocchi che richiedono controllo umano perché la confidenza OCR è bassa, perché la validazione è fallita o perché il blocco non è verificabile in strict mode.

La validazione è conservativa: JSON, YAML e Python usano parser reali; comandi terminale, path ed errori sono verificati tramite regole deterministiche; JavaScript/TypeScript/HTML/CSS/SQL/Dockerfile vengono classificati, ma marcati per revisione quando non esiste ancora un parser dedicato. I blocchi ripetuti in più frame vengono salvati una sola volta, mantenendo però tutti i frame sorgente e i timestamp.

È idempotente sugli input OCR: se `videodoc ocr` o `videodoc frames` cambiano testo, confidenza, timestamp o hash percettivo, il video viene rianalizzato; se nulla cambia, `videodoc code` salta l'analisi e autoripara comunque `code_blocks`, `contains_code` e il report dal manifest.

```bash
videodoc code corso-software-x
```

```text
Project: corso-software-x
+---------------+
| Processed | 0 |
| Skipped   | 8 |
+---------------+
```

Se nessun video è ancora stato registrato (`ingest` non è mai stato eseguito), o se c'è un problema strutturale su `project.db`, il comando fallisce con `exit code` 1. Problemi per-video su manifest codice corrotti vengono stampati come `Warning` e non bloccano gli altri video.

### 5.13 Creare i chunk temporali del progetto

Per ogni video con trascrizione, OCR o blocchi codice già disponibili, crea chunk temporali in `workdir/<id>/chunks/<id>.json`, li registra nella tabella `chunks` di `project.db` e aggiorna `metadata.json` (`chunks_path`):

```bash
videodoc chunk corso-software-x
```

```text
Project: corso-software-x
+---------------+
| Processed | 8 |
| Skipped   | 0 |
+---------------+
```

Il transcript, quando presente, è la spina dorsale temporale: i segmenti vengono raggruppati tra `chunking.min_duration_seconds` e `chunking.max_duration_seconds` (default 90-480s), spezzando anche su pause evidenti. Ogni chunk viene arricchito con OCR e blocchi codice nello stesso intervallo; con `chunking.include_nearby_frames: true`, frame e codice entro 5 secondi dai bordi vengono inclusi per non perdere screenshot campionati appena prima o dopo il parlato.

Se non c'è transcript, il comando usa comunque timestamp OCR/codice per creare finestre visive. Ogni blocco codice genera inoltre un chunk separato `source_type="code"`, utile per la fase embedding/retrieval.

È idempotente sugli input strutturati: cambi a transcript, OCR, `contains_code`, code blocks o impostazioni `chunking.*` innescano una nuova generazione; se nulla cambia, il comando salta la generazione ma riallinea comunque `project.db` e `metadata.json` dal manifest.

```bash
videodoc chunk corso-software-x
```

```text
Project: corso-software-x
+---------------+
| Processed | 0 |
| Skipped   | 8 |
+---------------+
```

Un video senza transcript, OCR o codice viene saltato senza errore. Se nessun video è ancora stato registrato (`ingest` mai eseguito), o se c'è un problema strutturale su `project.db`, il comando fallisce con `exit code` 1. Problemi per-video su manifest chunk corrotti vengono stampati come `Warning`.

### 5.14 Generare gli embedding dei chunk

Per ogni video con chunk già generati, crea embedding numerici per transcript, OCR, codice, summary e contenuto combinato, salvandoli in `indexes/embeddings/<id>.json`:

```bash
videodoc embed corso-software-x
```

```text
Project: corso-software-x
+---------------+
| Processed | 8 |
| Skipped   | 0 |
+---------------+
```

Il backend attuale è locale e deterministico (`feature-hashing`, 256 dimensioni): non scarica modelli e non richiede servizi esterni. È un backend bootstrap riproducibile, pensato per sbloccare la pipeline e la fase di indicizzazione; `config.embedding.provider`/`model` restano registrati nel manifest per idempotenza e per una futura sostituzione con un modello reale.

È idempotente sui manifest chunk: se testo, metadata, intervalli o impostazioni embedding non cambiano, il video viene saltato. Se `videodoc chunk` produce nuovi chunk, o cambia `config.embedding`, gli embedding vengono rigenerati.

```bash
videodoc embed corso-software-x
```

```text
Project: corso-software-x
+---------------+
| Processed | 0 |
| Skipped   | 8 |
+---------------+
```

Un video senza chunk viene saltato senza errore. Provider embedding diversi da `local` falliscono esplicitamente finché non verrà implementato un backend dedicato.

### 5.15 Indicizzare gli embedding

Legge `indexes/embeddings/<id>.json` e costruisce l'indice vettoriale locale `indexes/vector_index.json`:

```bash
videodoc index corso-software-x
```

```text
Project: corso-software-x
+---------------+
| Indexed | yes |
| Skipped | no  |
| Videos  | 8   |
| Records | 120 |
+---------------+
```

Il backend attuale è `local-json` con distanza cosine. `config.retrieval.vector_db` resta registrato nel file di indice come target configurato (default `qdrant`), ma il comando non richiede ancora Qdrant né servizi esterni. Ogni record contiene vettore e payload con progetto, video, chunk, tipo embedding, testo e metadata utili al retrieval.

È idempotente sui manifest embedding: se gli embedding non cambiano, il comando non riscrive l'indice.

```bash
videodoc index corso-software-x
```

```text
Project: corso-software-x
+---------------+
| Indexed | no  |
| Skipped | yes |
| Videos  | 8   |
| Records | 120 |
+---------------+
```

Un progetto senza embedding viene saltato senza errore. Un manifest embedding corrotto viene segnalato come `Warning` per-video e non blocca gli altri video indicizzabili.

### 5.16 Verificare lo stato dell'ambiente (`doctor`)

Comando **senza argomento progetto**: verifica Python, FFmpeg, `faster-whisper`, GPU/CUDA, registro locale e cartella progetti di default. Non modifica nulla:

```bash
videodoc doctor
```

```text
OK    Python version: 3.13.14 (>= 3.11 required)
OK    FFmpeg (ffprobe + ffmpeg): both found on PATH
OK    faster-whisper: importable
OK    GPU / CUDA: 1 CUDA device(s) detected, cublas64_12.dll loadable; NVIDIA GeForce RTX 4070 Laptop GPU, 8188 MiB dedicated total, 7301 MiB dedicated free, CC 8.9, driver 555.99 (via nvml); auto plan: compute_type=int8_float16, batch_size=19 (...)
OK    Project registry: 3 project(s) registered -- ...
OK    Default projects folder: ... is writable (default location)
6 OK, 0 warning(s), 0 error(s).
```

Le parole `OK`/`WARN`/`ERROR` sono testo ASCII colorato, non simboli Unicode — verificato che simboli come spunte/triangoli di avviso causano un crash reale (`UnicodeEncodeError`) su alcune console Windows legacy, anche passando per Rich.

`exit code` `1` solo se almeno un controllo è in stato `error` (i `warning`, come un problema CUDA rilevato ma non bloccante, non cambiano l'exit code).

### 5.17 Applicare le correzioni automaticamente (`setup`)

Esegue gli stessi controlli di `doctor` e offre di correggerli. Le correzioni via pip (es. i pacchetti CUDA opzionali) vengono applicate **senza chiedere conferma** (operazione nel venv, reversibile); le correzioni di sistema (FFmpeg via `winget`/`apt`/`brew`) chiedono **conferma esplicita** prima di essere eseguite; un'eventuale correzione puramente manuale viene solo stampata, mai eseguita:

```bash
videodoc setup
```

```text
OK    Python version: 3.13.14 (>= 3.11 required)
OK    FFmpeg (ffprobe + ffmpeg): both found on PATH
OK    faster-whisper: importable
WARN  GPU / CUDA: 1 CUDA device(s) detected but cublas64_12.dll could not be loaded: ...
  Applying fix for 'GPU / CUDA': <venv>\Scripts\python.exe -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
  Applied: Successfully installed nvidia-cublas-cu12-... nvidia-cudnn-cu12-...
  On Windows the pip packages alone are not enough -- also run this in your PowerShell session before 'videodoc transcribe' (see RUN.md §8): $env:PATH = "<venv>\Lib\site-packages\nvidia\cublas\bin;<venv>\Lib\site-packages\nvidia\cudnn\bin;$env:PATH"
OK    Project registry: 3 project(s) registered -- ...
OK    Default projects folder: ... is writable
Re-checking automatically-fixed items...
WARN  GPU / CUDA: 1 CUDA device(s) detected but cublas64_12.dll could not be loaded: ...
```
(In questo esempio reale il solo `pip install` non basta ancora -- resta il passaggio manuale del `PATH`, mai automatizzato; vedi il paragrafo successivo.)

Le correzioni di sistema riuscite non vengono ri-verificate nello stesso processo (il `PATH` del processo già in esecuzione non si aggiorna) — solo le correzioni pip lo sono, per questo la sezione finale "Re-checking..." appare solo quando è stata applicata almeno una correzione pip.

**Argomento progetto opzionale**: `videodoc setup <progetto>` esegue in più anche il pre-download del modello Whisper configurato per quel progetto (`transcription.model`, motore `faster-whisper`), chiamando lo stesso caricamento usato da `transcribe`:

```bash
videodoc setup corso-software-x
```

```text
...
Pre-downloading transcription model 'large-v3' for 'corso-software-x' -- first use may download several GB from Hugging Face and show no progress while doing so.
Model 'large-v3' is ready (downloaded and cached, or already present).
```

Perché conviene farlo qui invece che al primo `transcribe`: `faster-whisper` disabilita deliberatamente la propria progress bar di download (`tqdm_class=disabled_tqdm`), quindi un primo download di alcuni GB durante `transcribe` non mostra alcun avanzamento e può sembrare bloccato. Eseguendo `videodoc setup <progetto>` una volta, il modello è già in cache locale prima di lanciare la pipeline vera e propria. Senza argomento, `setup` resta esattamente come prima (nessun download, solo i controlli macchina).

## 6. Personalizzare i percorsi (variabili d'ambiente)

Due variabili d'ambiente permettono di controllare dove VideoDocRAG legge/scrive i propri dati, utili per test, ambienti sandbox o setup non standard:

| Variabile | Effetto | Default se non impostata |
|---|---|---|
| `VIDEODOC_HOME` | Cartella in cui `init` crea i progetti quando non si usa `--path` | `%USERPROFILE%\VideoDocRAG\projects` (Windows) / `~/VideoDocRAG/projects` (Linux/macOS) |
| `VIDEODOC_DATA_DIR` | Cartella in cui vive il registro locale (`registry.json`) | Cartella dati dell'applicazione via `platformdirs`: `%LOCALAPPDATA%\videodoc` (Windows), `~/.local/share/videodoc` (Linux), `~/Library/Application Support/videodoc` (macOS) |

Esempio, per lavorare in una sandbox completamente separata dal proprio profilo utente reale:

**Windows (PowerShell):**

```powershell
$env:VIDEODOC_HOME = "D:\Sandbox\VideoDocRAG\home"
$env:VIDEODOC_DATA_DIR = "D:\Sandbox\VideoDocRAG\appdata"

videodoc init progetto-di-prova
```

Per rimuoverle:

```powershell
Remove-Item Env:\VIDEODOC_HOME
Remove-Item Env:\VIDEODOC_DATA_DIR
```

**Linux/macOS (bash/zsh):**

```bash
export VIDEODOC_HOME="/tmp/videodoc-sandbox/home"
export VIDEODOC_DATA_DIR="/tmp/videodoc-sandbox/appdata"

videodoc init progetto-di-prova
```

Per rimuoverle:

```bash
unset VIDEODOC_HOME
unset VIDEODOC_DATA_DIR
```

Le variabili valgono solo per la sessione di terminale corrente.

## 7. Eseguire i test

**Windows (PowerShell):**

```powershell
cd D:\Projects\VideoDocRAG
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"   # se non già fatto

pytest
```

**Linux/macOS (bash/zsh):**

```bash
cd ~/Projects/VideoDocRAG
source .venv/bin/activate
pip install -e ".[dev]"   # se non già fatto

pytest
```

Con report di copertura (identico ovunque, venv attivo):

```bash
pytest --cov=src/videodoc --cov-report=term-missing
```

I test sono isolati automaticamente (vedi `tests/conftest.py`): non toccano mai la vera cartella dati dell'applicazione né la vera home utente, indipendentemente da come è configurato l'ambiente in cui vengono lanciati.

VideoDocRAG viene anche testato automaticamente su Windows, Linux e macOS a ogni push tramite GitHub Actions (`.github/workflows/tests.yml`) — la verifica multipiattaforma reale non dipende solo da questa macchina di sviluppo.

## 8. Risoluzione problemi

**`videodoc` non è riconosciuto come comando.**
Il virtual environment non è attivo. Riattivalo (§4). Se il problema persiste, verifica che `pip install -e ".[dev]"` sia andato a buon fine senza errori.

**(Solo Windows) Ho creato/rilanciato un progetto ma non trovo i file dove me li aspetto.**
Probabilmente stai usando la build Microsoft Store di Python — vedi §2. Verifica con `where python` e ricrea il venv con l'interprete ufficiale. Non è un problema noto su Linux/macOS.

**`Error: Project '<nome>' is already registered at <percorso>, which differs from the requested path <altro percorso>`.**
Il nome (in realtà lo slug: `videodoc init "Corso Software X"` viene registrato come `corso-software-x`, mai col nome grezzo) è già registrato su un percorso diverso da quello richiesto. Usa un nome diverso, oppure `videodoc unlink <nome>` seguito da `videodoc link <nuovo percorso>` se vuoi effettivamente spostare la registrazione.

**`Error: <percorso> already contains a different project ('<slug>', named '<nome>'). Refusing to re-initialize it as '<altro-slug>'...`.**
Hai lanciato `videodoc init <nome> --path <percorso>` su una cartella che contiene già un `config.yaml` valido di un *altro* progetto. Per evitare di creare un alias fuorviante (la stessa cartella registrata sotto due nomi diversi), l'init si rifiuta e non tocca il `config.yaml` esistente. Se il tuo intento era registrare quel progetto esistente con il suo nome reale, usa `videodoc link <percorso>` invece di `init`.

**`Error: Invalid configuration in <percorso>/config.yaml: ...`.**
Il file `config.yaml` è stato modificato a mano con un valore fuori dai limiti consentiti o una chiave sconosciuta (lo schema è validato in modo rigoroso — chiavi non previste vengono rifiutate, non ignorate silenziosamente). Il messaggio d'errore indica il campo esatto e il vincolo violato.

**Il registro locale sembra "resettato" dopo un errore.**
Se `registry.json` risultava corrotto (JSON non valido o struttura inattesa), viene automaticamente rinominato in `registry.json.corrupted-<timestamp>` nella stessa cartella e si riparte da un registro vuoto, senza bloccare il comando. Controlla quella cartella (§6, `VIDEODOC_DATA_DIR`) se pensi di aver perso delle registrazioni: i progetti non vengono mai cancellati dal disco, puoi sempre ri-registrarli con `videodoc link <percorso>`.

**`Error: paths.videos must be either a clean relative path ... or a fully absolute path ...`.**
Il valore passato a `--videos`/`--attachments`/`--codebase` (o scritto a mano in `config.yaml`) è una forma ambigua specifica delle regole di path dell'OS in uso — su Windows, ad esempio, `C:foo` (relativo alla cartella corrente sul drive C:) o `\foo`/`/foo` (relativo alla radice del drive corrente): nessuna delle due è né un percorso relativo pulito al progetto né un percorso assoluto esplicito. Su Linux/macOS questa categoria di ambiguità non esiste (le regole POSIX non hanno un concetto equivalente). Usa un percorso assoluto completo (`D:\Corsi\Workshop` su Windows, `/mnt/corsi/workshop` su Linux/macOS) o un nome relativo semplice (`videos`).

**`Error: ... must not contain '..' path segments ...`.**
Un valore relativo tipo `../altrove` o `sub/../../altrove` per `workdir`/`indexes`/`output`/`database`/`--videos`/`--attachments`/`--codebase` verrebbe risolto uscendo dalla cartella del progetto una volta unito al suo percorso — non è ammesso. Se l'intento è davvero riferirsi a una cartella esterna, usa un percorso assoluto esplicito; per `workdir`/`indexes`/`output`/`database` non è mai ammesso un riferimento esterno (devono restare dentro il progetto, vedi §5.1).

**`scan` riporta `0 found` nella riga `Videos` ma i video ci sono.**
Verifica che l'estensione dei file sia tra quelle riconosciute (`config.scan.allowed_video_extensions`, default `.mp4 .mkv .mov .avi .webm .m4v .wmv`) e che, se hai configurato un percorso esterno, quel percorso esista davvero e sia una cartella (non un file) — `scan` lo segnala con un `Warning` esplicito in entrambi i casi di problema.

**`videodoc ingest` fallisce con "ffprobe ... was not found on PATH".**
FFmpeg non è installato o `ffprobe` non è raggiungibile dal terminale corrente — vedi §1 per l'installazione per OS, poi verifica con `ffprobe -version`. `ingest` non crea nulla (né `project.db` né cartelle) quando questo controllo fallisce.

**`videodoc transcribe` fallisce con un errore che menziona `cublas` o una libreria CUDA mancante.**
Esegui prima `videodoc doctor` (§5.16): il check "GPU / CUDA" rileva esattamente questo problema (device rilevato ma libreria non caricabile) senza dover prima lanciare `transcribe` per scoprirlo. `videodoc setup` (§5.17) applica automaticamente la parte pip-installabile della correzione qui sotto — resta comunque il passaggio manuale del `PATH` (mai automatizzabile da nessun comando, vedi perché sotto).

`faster-whisper` rileva automaticamente l'hardware disponibile e, su una macchina dove viene individuata una GPU ma mancano le librerie runtime CUDA (es. `cublas64_12.dll` su Windows), fallisce invece di ripiegare in modo pulito sulla CPU. **Dove esattamente fallisce cambia il comportamento del comando**, e dipende da un dettaglio interno di `faster-whisper`/`ctranslate2` non controllabile da questo codice:
- Se il problema si manifesta solo alla prima trascrizione effettiva (osservato durante lo sviluppo: il caricamento del modello riesce, l'errore emerge alla prima chiamata reale) — non è un crash del comando: il video interessato viene segnalato con un `Warning` e saltato, gli altri (e le esecuzioni successive) continuano normalmente, `exit code` resta `0`.
- Se invece il problema impedisce già il caricamento del modello stesso (`WhisperModel(...)`) — è strutturale, non recuperabile per l'intero run: il comando fallisce con `Error: Could not load transcription engine ...` ed `exit code` `1`, senza processare alcun video.

`config.transcription` ora consente di scegliere esplicitamente `device`, `compute_type`, `mode`, `workers`, `batch_size` e altri parametri di decoding. Se vuoi forzare la CPU, usa ad esempio:

```powershell
videodoc transcribe <progetto> --device cpu --mode standard --compute-type int8
```

Se hai una GPU NVIDIA reale e vuoi usarla, puoi installare le librerie runtime CUDA come pacchetti pip puri, senza installare l'intero CUDA Toolkit di sistema (`videodoc setup` fa esattamente questo passaggio in automatico):

```powershell
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

**Su Windows questo da solo non basta**: a differenza di Linux, Windows non individua automaticamente le DLL installate così — vanno aggiunte esplicitamente al `PATH` della sessione prima di eseguire `transcribe` (verificato: senza questo passaggio l'errore persiste identico anche a pacchetti installati):

```powershell
$env:PATH = "<percorso-venv>\Lib\site-packages\nvidia\cublas\bin;<percorso-venv>\Lib\site-packages\nvidia\cudnn\bin;$env:PATH"
```

Vale solo per la sessione di terminale corrente — da ripetere ad ogni nuova sessione, oppure aggiungi questi due percorsi al `PATH` di sistema in modo permanente. In alternativa, esegui su una macchina senza GPU rilevata (nessun problema di CUDA in quel caso, dato che `faster-whisper` non tenta nemmeno di usarla).

**`videodoc transcribe` è molto lento o scarica diversi GB al primo avvio.**
Il modello configurato (default `transcription.model: large-v3`) viene scaricato da Hugging Face al primo utilizzo reale. Per throughput massimo su una GPU da 8 GB come una RTX 4070 Laptop, usa o lascia i default aggiornati: CUDA, `mode: batched`, `beam_size: 1`, VAD attivo e `word_timestamps: false`; `compute_type` e `batch_size` restano `auto`, così il planner li calcola dalla VRAM dedicata libera con un margine di sicurezza. Su una 4070 Laptop da 8 GB libera, il batch può salire oltre il vecchio default 8; se la VRAM disponibile è minore, scende automaticamente.

```powershell
videodoc transcribe <progetto> --device cuda --mode batched --beam-size 1 --workers 1 --no-word-timestamps
```

Se resta lento, controlla `nvidia-smi`: la CPU bassa è normale quando CTranslate2 lavora su GPU; il dato più importante è `utilization.gpu`. Il planner considera solo VRAM dedicata (`memory.free`), non la memoria GPU condivisa di Windows. Se compare un OOM, il comando prova a dimezzare il batch o a usare un compute type più leggero; per una prova manuale puoi forzare `--batch-size 4` o `--device cpu`. Se vuoi una prova rapida sacrificando qualità, modifica temporaneamente `transcription.model` in `config.yaml` con un modello più piccolo (es. `medium`, `small`, `base`).

## 9. Cosa non è ancora disponibile

Questi step coprono la gestione dei progetti, la scansione delle fonti, l'ingestion dei video, l'estrazione audio, la trascrizione, l'estrazione frame e l'OCR. Non sono ancora implementati (vedi la roadmap completa in `README.md`, §37, e il changelog in `docs/CHANGELOG.md`):

- `videodoc sync-codebase` — sincronizzazione e indicizzazione della codebase;
- `videodoc code` — riconoscimento ed estrazione del codice;
- `videodoc chunk`, `index` — chunking ed embedding/indicizzazione vettoriale;
- `videodoc outline`, `generate`, `review`, `export` — generazione e revisione della documentazione;
- `videodoc ask`, `chat` — interrogazione RAG e chat sulla knowledge base;
- `videodoc status`, `inspect` — stato pipeline e ispezione puntuale;
- l'interfaccia GUI (`videodoc gui`).

Nessuno di questi comandi esiste ancora nella CLI: verranno aggiunti negli step successivi.
