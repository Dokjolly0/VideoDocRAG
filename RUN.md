# VideoDocRAG — Guida all'esecuzione

Questa guida spiega come installare ed eseguire VideoDocRAG così com'è oggi (Step 1: gestione progetti — `init`, `list`, `link`, `unlink`, `path`; Step 2: scansione delle fonti — `scan`, percorsi sorgente esterni; Step 3: ingestion dei video — `ingest`; Step 4: estrazione audio — `extract-audio`) su **Windows, Linux o macOS**. Per l'elenco completo di ogni comando con sintassi ed esempio di output, vedi [`docs/commands.md`](docs/commands.md). Le fasi successive della pipeline (trascrizione, OCR, RAG, generazione documentazione, chat — vedi `README.md`) non sono ancora implementate.

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
Videos: 8 found
Attachments: 3 found
Codebase: present (42 files)
Excluded directories: .git, node_modules, __pycache__, dist, build, ...
Excluded file patterns: .DS_Store
Sources manifest updated: sources.yaml
```

Se una sorgente è esterna, viene segnalata esplicitamente:

```text
Videos: 8 found (external: /mnt/corsi/registrazioni)
```

Zero video trovati **non** fa fallire il comando (`exit code` resta `0`): sarà una fase successiva (ingestion) a rifiutarsi di procedere senza video, non lo scan. Allo stesso modo, una sorgente esterna mancante (es. un'unità scollegata, o un mount point non montato su Linux/macOS) o che punta a un file invece che a una cartella produce solo un avviso, mai un crash:

```text
Warning: external videos path not found: /mnt/corsi/registrazioni
```

Le esclusioni si basano sulla sezione `scan:` di `config.yaml` (default già ragionevoli — `.git/`, `node_modules/`, `__pycache__/`, ecc. — personalizzabili con `add_excludes`/`remove_excludes`, vedi README §8.3). `sources.yaml` viene **sempre rigenerato per intero** a ogni scan, mai preservato: rilanciarlo dopo aver aggiunto un video aggiorna semplicemente il manifest.

### 5.7 Registrare (ingest) i video di un progetto

Calcola l'hash di ogni video, ne estrae durata/formato/risoluzione/codec con `ffprobe` (vedi §1 per l'installazione), lo registra in `project.db` e crea `workdir/<id>/{audio,frames,transcript,ocr,chunks}/` + `metadata.json`:

```bash
videodoc ingest corso-software-x
```

```text
Project: corso-software-x
Videos ingested: 8, reingested (changed): 0, skipped (unchanged): 0
Database updated: project.db
```

È idempotente per contenuto: un video invariato viene saltato (senza nemmeno essere ri-analizzato da `ffprobe`); un video modificato viene riprocessato e genera un avviso, non un errore, sui possibili artefatti obsoleti nelle sue sottocartelle (mai cancellate automaticamente):

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
Audio extracted: 8, skipped (already extracted): 0
```

È idempotente per presenza del file: rilanciandolo, i video già estratti vengono saltati senza richiamare `ffmpeg`:

```bash
videodoc extract-audio corso-software-x
```

```text
Project: corso-software-x
Audio extracted: 0, skipped (already extracted): 8
```

Se nessun video è ancora stato registrato (`ingest` non è mai stato eseguito) o se `ffmpeg` non è disponibile in `PATH`, il comando fallisce subito (`exit code` 1) senza creare o modificare nulla. Un problema di estrazione su un singolo video (es. codec non supportato) non blocca gli altri: viene segnalato con un `Warning`, il comando resta a `exit code` 0.

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

**`scan` riporta "Videos: 0 found" ma i video ci sono.**
Verifica che l'estensione dei file sia tra quelle riconosciute (`config.scan.allowed_video_extensions`, default `.mp4 .mkv .mov .avi .webm .m4v .wmv`) e che, se hai configurato un percorso esterno, quel percorso esista davvero e sia una cartella (non un file) — `scan` lo segnala con un `Warning` esplicito in entrambi i casi di problema.

**`videodoc ingest` fallisce con "ffprobe ... was not found on PATH".**
FFmpeg non è installato o `ffprobe` non è raggiungibile dal terminale corrente — vedi §1 per l'installazione per OS, poi verifica con `ffprobe -version`. `ingest` non crea nulla (né `project.db` né cartelle) quando questo controllo fallisce.

## 9. Cosa non è ancora disponibile

Questi quattro step coprono la gestione dei progetti, la scansione delle fonti, l'ingestion dei video e l'estrazione audio. Non sono ancora implementati (vedi la roadmap completa in `README.md`, §37, e il changelog in `docs/CHANGELOG.md`):

- `videodoc sync-codebase` — sincronizzazione e indicizzazione della codebase;
- `videodoc transcribe`, `frames`, `ocr`, `code` — trascrizione audio, estrazione frame, OCR, riconoscimento codice;
- `videodoc chunk`, `index` — chunking ed embedding/indicizzazione vettoriale;
- `videodoc outline`, `generate`, `review`, `export` — generazione e revisione della documentazione;
- `videodoc ask`, `chat` — interrogazione RAG e chat sulla knowledge base;
- `videodoc status`, `inspect` — stato pipeline e ispezione puntuale;
- l'interfaccia GUI (`videodoc gui`).

Nessuno di questi comandi esiste ancora nella CLI: verranno aggiunti negli step successivi.
