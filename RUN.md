# VideoDocRAG — Guida all'esecuzione

Questa guida spiega come installare ed eseguire VideoDocRAG così com'è oggi (Step 1: gestione progetti — `init`, `list`, `link`, `unlink`, `path`; Step 2: scansione delle fonti — `scan`, percorsi sorgente esterni). Le fasi successive della pipeline (ingestion, trascrizione, OCR, RAG, generazione documentazione, chat — vedi `README.md`) non sono ancora implementate.

## Indice

1. [Prerequisiti](#1-prerequisiti)
2. [Nota importante: quale Python usare (Windows)](#2-nota-importante-quale-python-usare-windows)
3. [Setup iniziale dell'ambiente](#3-setup-iniziale-dellambiente)
4. [Attivare l'ambiente nelle sessioni successive](#4-attivare-lambiente-nelle-sessioni-successive)
5. [Comandi disponibili](#5-comandi-disponibili)
6. [Personalizzare i percorsi (variabili d'ambiente)](#6-personalizzare-i-percorsi-variabili-dambiente)
7. [Eseguire i test](#7-eseguire-i-test)
8. [Risoluzione problemi](#8-risoluzione-problemi)
9. [Cosa non è ancora disponibile](#9-cosa-non-è-ancora-disponibile)

---

## 1. Prerequisiti

- Windows con PowerShell (le istruzioni sotto usano la sintassi PowerShell).
- Python 3.11 o superiore.
- Nessuna altra dipendenza esterna richiesta in questo step (niente Ollama, FFmpeg, Qdrant: servono solo dalle fasi successive della pipeline).

## 2. Nota importante: quale Python usare (Windows)

Su Windows, digitare `python` può risolvere a build diverse. **Evita la build "Microsoft Store"** di Python (quella installata dal Microsoft Store, tipicamente con percorso tipo `...\AppData\Local\Microsoft\WindowsApps\python.exe` o `...\Packages\PythonSoftwareFoundation.Python.3.13_...`): Windows applica a queste build una virtualizzazione del filesystem che reindirizza silenziosamente le scritture sotto `%LOCALAPPDATA%` in una cartella privata del pacchetto, invisibile a PowerShell, Esplora File o altri programmi. VideoDocRAG scrive proprio lì il registro locale dei progetti (vedi §6), quindi con la build Store rischi di non trovare più i file che il programma dice di aver creato.

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

## 3. Setup iniziale dell'ambiente

Da eseguire una sola volta (o ogni volta che si vuole un ambiente pulito):

```powershell
cd D:\Projects\VideoDocRAG

# Usa l'interprete ufficiale trovato al passo 2. Sostituisci il percorso se diverso.
& "C:\Users\<utente>\AppData\Local\Programs\Python\Python313\python.exe" -m venv .venv

.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Verifica che l'installazione sia andata a buon fine:

```powershell
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

```powershell
cd D:\Projects\VideoDocRAG
.venv\Scripts\Activate.ps1
```

Per uscire dal virtual environment a fine sessione:

```powershell
deactivate
```

## 5. Comandi disponibili

### 5.1 Creare un nuovo progetto

Nel percorso di default (fuori dalla cartella del programma, vedi README §8.1.2):

```powershell
videodoc init corso-software-x
```

```text
Project 'corso-software-x' initialized at C:\Users\<utente>\VideoDocRAG\projects\corso-software-x
Registered as 'corso-software-x' in the local project registry.
```

In un percorso a scelta (es. un'altra unità, una cartella condivisa, una chiavetta):

```powershell
videodoc init corso-software-x --path "D:\Corsi\corso-software-x"
```

**Video (o allegati, o codebase) già presenti altrove sul disco**: non serve copiarli dentro il progetto. `--videos`/`--attachments`/`--codebase` impostano un percorso esterno, referenziato non copiato (stesso principio dei "media collegati" di un editor video):

```powershell
videodoc init corso-software-x --videos "D:\Corsi\Registrazioni"
```

Questi tre flag hanno effetto **solo alla prima creazione** del progetto: se rilanciati su un progetto già esistente vengono ignorati con un avviso esplicito (`config.yaml` non viene mai sovrascritto), non silenziosamente scartati:

```text
Project 'corso-software-x' already initialized at ... (config.yaml kept unchanged)
Warning: --videos ignored: config.yaml already exists and 'init' never overwrites it.
```

Un progetto con sorgenti esterne non è più interamente autocontenuto: spostare la cartella del progetto non porta con sé i video/allegati/codebase esterni (che restano dove sono). È una scelta consapevole — l'isolamento dei dati generati (`project.db`, indice Qdrant) resta comunque garantito, solo i materiali sorgente possono vivere altrove.

Rilanciare `init` sullo stesso progetto è sicuro: non sovrascrive un `config.yaml` già esistente, riporta solo lo stato ("already initialized").

Struttura creata:

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

```powershell
videodoc list
```

```text
+-----------------------------------------------------------------------------+
| Name              | Path                              | Created at         |
|-------------------+------------------------------------+--------------------|
| corso-software-x  | D:\Corsi\corso-software-x          | 2026-07-09T14:00:25 |
+-----------------------------------------------------------------------------+
```

Se non ci sono progetti registrati, il comando lo dice esplicitamente e suggerisce `init`/`link`.

### 5.3 Ottenere il percorso assoluto di un progetto

Utile per script o per navigare rapidamente:

```powershell
videodoc path corso-software-x
cd (videodoc path corso-software-x)
```

### 5.4 Registrare un progetto esistente (creato o spostato a mano)

Se una cartella progetto (con un `config.yaml` valido) esiste già ma non è nel registro locale — per esempio dopo averla spostata, copiata da un altro PC, o clonata da un backup:

```powershell
videodoc link "D:\Corsi\corso-software-x"
```

`--name` registra il progetto sotto un **alias locale esplicito**, diverso dallo slug canonico presente nel suo `config.yaml` — utile per risolvere una collisione locale tra due progetti il cui slug coincide per caso, o per usare un nickname più corto. Non modifica mai il `config.yaml` del progetto: l'identità "vera" resta quella scritta lì. L'alias viene comunque normalizzato con le stesse regole dello slug (niente spazi/maiuscole/punteggiatura nel registro), e il comando lo segnala esplicitamente in output quando differisce dallo slug reale:

```powershell
videodoc link "D:\Corsi\corso-software-x" --name "Alias Locale!!"
# Linked as alias 'alias-locale' -> D:\Corsi\corso-software-x (the project's own slug is 'corso-software-x')
```

Se invece non lo differenzi mai, il comando registra semplicemente con lo slug canonico e lo dice senza menzionare alcun alias:

```powershell
videodoc link "D:\Corsi\corso-software-x"
# Linked 'corso-software-x' -> D:\Corsi\corso-software-x
```

### 5.5 Rimuovere un progetto dal registro (senza cancellare i file)

```powershell
videodoc unlink corso-software-x
```

Questo comando **non cancella mai i file del progetto**: agisce solo sul registro locale. Per riaverlo disponibile basta rilanciare `videodoc link <percorso>`.

### 5.6 Scansionare le fonti di un progetto

Enumera video, allegati e codebase (interni o esterni) e scrive `sources.yaml`:

```powershell
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
Videos: 8 found (external: D:\Corsi\Registrazioni)
```

Zero video trovati **non** fa fallire il comando (`exit code` resta `0`): sarà una fase successiva (ingestion) a rifiutarsi di procedere senza video, non lo scan. Allo stesso modo, una sorgente esterna mancante (es. un'unità scollegata) o che punta a un file invece che a una cartella produce solo un avviso, mai un crash:

```text
Warning: external videos path not found: Z:\NonEsiste\Videos
```

Le esclusioni si basano sulla sezione `scan:` di `config.yaml` (default già ragionevoli — `.git/`, `node_modules/`, `__pycache__/`, ecc. — personalizzabili con `add_excludes`/`remove_excludes`, vedi README §8.3). `sources.yaml` viene **sempre rigenerato per intero** a ogni scan, mai preservato: rilanciarlo dopo aver aggiunto un video aggiorna semplicemente il manifest.

## 6. Personalizzare i percorsi (variabili d'ambiente)

Due variabili d'ambiente permettono di controllare dove VideoDocRAG legge/scrive i propri dati, utili per test, ambienti sandbox o setup non standard:

| Variabile | Effetto | Default se non impostata |
|---|---|---|
| `VIDEODOC_HOME` | Cartella in cui `init` crea i progetti quando non si usa `--path` | `%USERPROFILE%\VideoDocRAG\projects` |
| `VIDEODOC_DATA_DIR` | Cartella in cui vive il registro locale (`registry.json`) | Cartella dati dell'applicazione via `platformdirs` (tipicamente `%LOCALAPPDATA%\videodoc`) |

Esempio, per lavorare in una sandbox completamente separata dal proprio profilo utente reale:

```powershell
$env:VIDEODOC_HOME = "D:\Sandbox\VideoDocRAG\home"
$env:VIDEODOC_DATA_DIR = "D:\Sandbox\VideoDocRAG\appdata"

videodoc init progetto-di-prova
```

Le variabili valgono solo per la sessione di terminale corrente. Per rimuoverle:

```powershell
Remove-Item Env:\VIDEODOC_HOME
Remove-Item Env:\VIDEODOC_DATA_DIR
```

## 7. Eseguire i test

```powershell
cd D:\Projects\VideoDocRAG
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"   # se non già fatto

pytest
```

Con report di copertura:

```powershell
pytest --cov=src/videodoc --cov-report=term-missing
```

I test sono isolati automaticamente (vedi `tests/conftest.py`): non toccano mai il vero `%LOCALAPPDATA%` né la vera home utente, indipendentemente da come è configurato l'ambiente in cui vengono lanciati.

## 8. Risoluzione problemi

**`videodoc` non è riconosciuto come comando.**
Il virtual environment non è attivo. Esegui `.venv\Scripts\Activate.ps1` dalla root del progetto (§4). Se il problema persiste, verifica che `pip install -e ".[dev]"` sia andato a buon fine senza errori.

**Ho creato/rilanciato un progetto ma non trovo i file dove me li aspetto.**
Probabilmente stai usando la build Microsoft Store di Python — vedi §2. Verifica con `where python` e ricrea il venv con l'interprete ufficiale.

**`Error: Project '<nome>' is already registered at <percorso>, which differs from the requested path <altro percorso>`.**
Il nome (in realtà lo slug: `videodoc init "Corso Software X"` viene registrato come `corso-software-x`, mai col nome grezzo) è già registrato su un percorso diverso da quello richiesto. Usa un nome diverso, oppure `videodoc unlink <nome>` seguito da `videodoc link <nuovo percorso>` se vuoi effettivamente spostare la registrazione.

**`Error: <percorso> already contains a different project ('<slug>', named '<nome>'). Refusing to re-initialize it as '<altro-slug>'...`.**
Hai lanciato `videodoc init <nome> --path <percorso>` su una cartella che contiene già un `config.yaml` valido di un *altro* progetto. Per evitare di creare un alias fuorviante (la stessa cartella registrata sotto due nomi diversi), l'init si rifiuta e non tocca il `config.yaml` esistente. Se il tuo intento era registrare quel progetto esistente con il suo nome reale, usa `videodoc link <percorso>` invece di `init`.

**`Error: Invalid configuration in <percorso>\config.yaml: ...`.**
Il file `config.yaml` è stato modificato a mano con un valore fuori dai limiti consentiti o una chiave sconosciuta (lo schema è validato in modo rigoroso — chiavi non previste vengono rifiutate, non ignorate silenziosamente). Il messaggio d'errore indica il campo esatto e il vincolo violato.

**Il registro locale sembra "resettato" dopo un errore.**
Se `registry.json` risultava corrotto (JSON non valido o struttura inattesa), viene automaticamente rinominato in `registry.json.corrupted-<timestamp>` nella stessa cartella e si riparte da un registro vuoto, senza bloccare il comando. Controlla quella cartella (§6, `VIDEODOC_DATA_DIR`) se pensi di aver perso delle registrazioni: i progetti non vengono mai cancellati dal disco, puoi sempre ri-registrarli con `videodoc link <percorso>`.

**`Error: paths.videos must be either a clean relative path ... or a fully absolute path ...`.**
Il valore passato a `--videos`/`--attachments`/`--codebase` (o scritto a mano in `config.yaml`) è una forma Windows ambigua tipo `C:foo` (relativa alla cartella corrente sul drive C:) o `\foo`/`/foo` (relativa alla radice del drive corrente) — nessuna delle due è né un percorso relativo pulito al progetto né un percorso assoluto esplicito. Usa un percorso completo (`D:\Corsi\Workshop`) o un nome relativo semplice (`videos`).

**`Error: ... must not contain '..' path segments ...`.**
Un valore relativo tipo `../altrove` o `sub/../../altrove` per `workdir`/`indexes`/`output`/`database`/`--videos`/`--attachments`/`--codebase` verrebbe risolto uscendo dalla cartella del progetto una volta unito al suo percorso — non è ammesso. Se l'intento è davvero riferirsi a una cartella esterna, usa un percorso assoluto esplicito (`D:\Corsi\Workshop`); per `workdir`/`indexes`/`output`/`database` non è mai ammesso un riferimento esterno (devono restare dentro il progetto, vedi §5.1).

**`scan` riporta "Videos: 0 found" ma i video ci sono.**
Verifica che l'estensione dei file sia tra quelle riconosciute (`config.scan.allowed_video_extensions`, default `.mp4 .mkv .mov .avi .webm .m4v .wmv`) e che, se hai configurato un percorso esterno, quel percorso esista davvero e sia una cartella (non un file) — `scan` lo segnala con un `Warning` esplicito in entrambi i casi di problema.

## 9. Cosa non è ancora disponibile

Questi due step coprono solo la gestione dei progetti e la scansione delle fonti. Non sono ancora implementati (vedi la roadmap completa in `README.md`, §37, e il changelog in `docs/CHANGELOG.md`):

- `videodoc ingest`, `sync-codebase` — registrazione video e sincronizzazione codebase;
- `videodoc transcribe`, `frames`, `ocr`, `code` — trascrizione audio, estrazione frame, OCR, riconoscimento codice;
- `videodoc chunk`, `index` — chunking ed embedding/indicizzazione vettoriale;
- `videodoc outline`, `generate`, `review`, `export` — generazione e revisione della documentazione;
- `videodoc ask`, `chat` — interrogazione RAG e chat sulla knowledge base;
- `videodoc status`, `inspect` — stato pipeline e ispezione puntuale;
- l'interfaccia GUI (`videodoc gui`).

Nessuno di questi comandi esiste ancora nella CLI: verranno aggiunti negli step successivi.
