# VideoDocRAG - Sistema locale per trasformare video tecnici in documentazione Markdown tramite RAG

## Indice

1. [Obiettivo del progetto](#1-obiettivo-del-progetto)
2. [Problema che il progetto risolve](#2-problema-che-il-progetto-risolve)
3. [Risultato finale atteso](#3-risultato-finale-atteso)
4. [Principi di progettazione](#4-principi-di-progettazione)
5. [Architettura generale](#5-architettura-generale)
6. [Organizzazione modulare: core, CLI e GUI](#6-organizzazione-modulare-core-cli-e-gui)
7. [Stack tecnologico consigliato](#7-stack-tecnologico-consigliato)
8. [Struttura del progetto](#8-struttura-del-progetto)
   - [8.2 Modello progetto per ogni RAG](#82-modello-progetto-per-ogni-rag)
   - [8.3 Scansione delle fonti ed esclusioni](#83-scansione-delle-fonti-ed-esclusioni)
9. [Formato dei dati e metadati](#9-formato-dei-dati-e-metadati)
10. [Pipeline completa](#10-pipeline-completa)
11. [Modulo core](#11-modulo-core)
12. [Modulo CLI](#12-modulo-cli)
13. [Modulo GUI](#13-modulo-gui)
14. [Fase 1 — Inizializzazione del progetto](#14-fase-1--inizializzazione-del-progetto)
15. [Fase 2 — Ingestion dei video](#15-fase-2--ingestion-dei-video)
16. [Fase 3 — Estrazione audio](#16-fase-3--estrazione-audio)
17. [Fase 4 — Trascrizione audio](#17-fase-4--trascrizione-audio)
18. [Fase 5 — Estrazione frame e screenshot](#18-fase-5--estrazione-frame-e-screenshot)
19. [Fase 6 — OCR delle schermate](#19-fase-6--ocr-delle-schermate)
20. [Fase 7 — Riconoscimento ed estrazione del codice](#20-fase-7--riconoscimento-ed-estrazione-del-codice)
21. [Fase 8 — Chunking intelligente](#21-fase-8--chunking-intelligente)
22. [Fase 9 — Creazione degli embedding](#22-fase-9--creazione-degli-embedding)
23. [Fase 10 — Indicizzazione nel vector database](#23-fase-10--indicizzazione-nel-vector-database)
24. [Fase 11 — Retrieval e RAG](#24-fase-11--retrieval-e-rag)
25. [Fase 12 — Generazione dell’indice della documentazione](#25-fase-12--generazione-dellindice-della-documentazione)
26. [Fase 13 — Generazione delle sezioni Markdown](#26-fase-13--generazione-delle-sezioni-markdown)
27. [Fase 14 — Revisione, validazione e controllo qualità](#27-fase-14--revisione-validazione-e-controllo-qualità)
28. [Fase 15 — Export della documentazione](#28-fase-15--export-della-documentazione)
29. [Configurazione del progetto](#29-configurazione-del-progetto)
30. [Schema database SQLite](#30-schema-database-sqlite)
31. [Schema Qdrant](#31-schema-qdrant)
32. [Prompt principali](#32-prompt-principali)
33. [Gestione del codice estratto dai video](#33-gestione-del-codice-estratto-dai-video)
34. [Gestione dei materiali allegati](#34-gestione-dei-materiali-allegati)
35. [Modalità operative](#35-modalità-operative)
36. [Roadmap di sviluppo](#36-roadmap-di-sviluppo)
37. [Best practice](#37-best-practice)
38. [Limiti del sistema](#38-limiti-del-sistema)
39. [Esempio di output Markdown generato](#39-esempio-di-output-markdown-generato)
40. [Conclusione](#40-conclusione)

---

# 1. Obiettivo del progetto

L’obiettivo del progetto è creare un sistema riusabile, preferibilmente locale, capace di trasformare video tecnici, workshop, corsi, registrazioni di demo software e tutorial in una documentazione testuale dettagliata, strutturata e navigabile in formato Markdown.

Il sistema deve analizzare video di lunga durata, estrarre le informazioni principali, comprendere le procedure mostrate, recuperare eventuale codice visualizzato a schermo, collegare ogni informazione al video di origine e generare documentazione tecnica completa.

Il progetto non deve essere limitato a un singolo software o a un singolo corso. Deve essere progettato come una pipeline general-purpose, configurabile e riutilizzabile su materiali diversi.

L’obiettivo finale è ottenere un sistema in grado di creare un progetto per ogni nuovo RAG e prendere in input una cartella strutturata contenente video obbligatori e materiali opzionali, per esempio allegati, repository, file sorgenti, slide, PDF o note. A partire da queste fonti, il sistema deve produrre automaticamente una documentazione Markdown organizzata in sezioni, completa di spiegazioni, codice, procedure passo-passo, timestamp e riferimenti alle fonti.

Il sistema deve inoltre creare una base di conoscenza interrogabile tramite RAG, cioè Retrieval-Augmented Generation, così da poter fare domande ai contenuti dei video e generare nuove sezioni documentali basandosi sulle fonti estratte.

In sintesi, il progetto deve permettere di passare da questo scenario:

```text
Cartella con video workshop di molte ore
```

A questo risultato:

```text
Documentazione Markdown dettagliata
Indice navigabile
Procedure passo-passo
Codice estratto e spiegato
Riferimenti a video e timestamp
Database RAG interrogabile
Output esportabile in MkDocs, Docusaurus o GitHub Pages
```

Il valore principale del progetto consiste nel rendere riutilizzabile e consultabile un patrimonio informativo che normalmente rimane intrappolato dentro ore di registrazioni video.

---

# 2. Problema che il progetto risolve

Molti contenuti tecnici importanti vengono trasmessi attraverso video: corsi, workshop, tutorial, demo interne, registrazioni di meeting tecnici, lezioni online o presentazioni di prodotto.

Questi video sono molto utili, ma presentano diversi problemi pratici:

- richiedono molto tempo per essere consultati;
- è difficile cercare rapidamente una procedura specifica;
- il codice mostrato a schermo non è sempre disponibile come file;
- i passaggi eseguiti nell’interfaccia grafica possono essere difficili da ritrovare;
- non esiste una documentazione testuale derivata dal video;
- i contenuti non sono facilmente versionabili;
- è difficile riusare le informazioni in un team;
- è complesso trasformare il materiale video in guide, manuali o knowledge base.

Un semplice sistema RAG basato solo sulla trascrizione audio non è sufficiente, perché nei video tecnici molte informazioni importanti non vengono dette esplicitamente. Per esempio, il docente può dire:

```text
Ora copiamo questo comando nel terminale.
```

Ma il comando è visibile solo a schermo. In questo caso la trascrizione audio non contiene il codice, quindi il sistema deve anche analizzare le immagini del video tramite OCR o modelli multimodali.

Il progetto risolve questo problema creando una pipeline che combina:

- trascrizione audio;
- estrazione frame;
- OCR delle schermate;
- riconoscimento del codice;
- segmentazione temporale;
- indicizzazione vettoriale;
- generazione documentale tramite LLM;
- verifica e tracciabilità delle fonti.

---

# 3. Risultato finale atteso

Il risultato finale del progetto deve essere una cartella di documentazione Markdown simile a questa:

```text
docs/
├── index.md
├── 01-introduzione.md
├── 02-installazione.md
├── 03-configurazione-ambiente.md
├── 04-primo-progetto.md
├── 05-funzionalita-principali.md
├── 06-debug.md
├── 07-deployment.md
└── appendici/
    ├── comandi.md
    ├── errori-comuni.md
    └── riferimenti-video.md
```

Ogni sezione della documentazione deve contenere:

- titolo chiaro;
- obiettivo della sezione;
- video di riferimento;
- timestamp di inizio e fine;
- spiegazione discorsiva;
- procedura passo-passo;
- codice esaminato nel video;
- spiegazione del codice;
- risultato atteso;
- eventuali errori comuni;
- riferimenti alle fonti.

Esempio di struttura attesa per una sezione:

````markdown
# Configurazione iniziale del progetto

**Video di riferimento:** `workshop_01_installazione.mp4`  
**Timestamp:** `00:18:20–00:24:55`

## Obiettivo

In questa sezione viene configurato l’ambiente iniziale del progetto.

## Procedura passo-passo

1. Aprire il terminale.
2. Spostarsi nella cartella di lavoro.
3. Eseguire il comando di creazione progetto.

## Codice mostrato

```bash
npm create vite@latest my-app
cd my-app
npm install
npm run dev
```

## Spiegazione del codice

Il comando `npm create vite@latest my-app` crea una nuova applicazione.

## Risultato atteso

Al termine della procedura, l’applicazione dovrebbe essere disponibile in locale.

## Fonte

- Video: `workshop_01_installazione.mp4`
- Timestamp: `00:18:20–00:24:55`
````

---

# 4. Principi di progettazione

## 4.1 Modularità

Ogni fase della pipeline deve essere indipendente. La trascrizione, l’OCR, il chunking, l’indicizzazione e la generazione documentale devono essere moduli separati.

La modularità si applica anche a livello architetturale. Il progetto deve essere separato in tre macro-moduli:

- `core`, che contiene la logica applicativa e la pipeline;
- `cli`, che espone i comandi da terminale;
- `gui`, che fornisce un’interfaccia web opzionale.

Questa separazione permette di usare lo stesso motore applicativo da CLI, da GUI o da automazioni future.

## 4.2 Tracciabilità

Ogni informazione generata deve poter essere ricondotta alla fonte originale. Ogni chunk deve conservare:

- nome del video;
- timestamp di inizio;
- timestamp di fine;
- testo trascritto;
- testo OCR;
- codice estratto;
- eventuali file allegati utilizzati;
- livello di confidenza.

La tracciabilità è essenziale per ridurre le allucinazioni del modello e permettere una revisione umana affidabile.

## 4.3 Riutilizzabilità

Il sistema deve poter essere usato su progetti diversi. Per questo motivo non deve contenere logica hardcoded legata a un singolo software.

Ogni progetto deve avere un file di configurazione dedicato.

## 4.4 Generazione incrementale

La documentazione non deve essere generata tutta in una sola richiesta al modello. È preferibile generare:

1. outline generale;
2. sezioni singole;
3. appendici;
4. revisione finale.

Questo approccio riduce gli errori e rende il processo più controllabile.

## 4.5 Funzionamento locale

Il sistema deve poter funzionare localmente, usando modelli open-source eseguiti con Ollama, llama.cpp, vLLM o altre soluzioni simili.

Questo è importante per:

- privacy;
- costi ridotti;
- uso offline;
- controllo sui dati;
- utilizzo su materiale aziendale o riservato.

## 4.6 Separazione tra dati grezzi e documentazione finale

Il progetto deve distinguere chiaramente:

- dati grezzi estratti dai video;
- dati strutturati e normalizzati;
- documentazione finale generata.

Questa separazione permette di rigenerare la documentazione senza dover rielaborare i video da zero.

---

# 5. Architettura generale

L’architettura del sistema può essere rappresentata così:

```text
Video sorgenti
   ↓
Ingestion
   ↓
Estrazione audio
   ↓
Trascrizione audio
   ↓
Estrazione frame
   ↓
OCR schermate
   ↓
Riconoscimento codice
   ↓
Chunking intelligente
   ↓
Embedding
   ↓
Vector database
   ↓
Retrieval/RAG
   ↓
Generazione Markdown
   ↓
Revisione e validazione
   ↓
Export documentazione
```

Dal punto di vista software, la stessa pipeline viene esposta da tre livelli distinti:

```text
core
  ├── modelli dati
  ├── servizi pipeline
  ├── storage
  ├── RAG
  ├── generatori Markdown
  └── validazione

cli
  ├── comandi Typer
  ├── output testuale
  ├── comandi batch
  └── ispezione progetto

gui
  ├── API FastAPI
  ├── dashboard web
  ├── player video
  ├── editor Markdown
  └── chat RAG
```

Il sistema avrà due modalità principali:

1. modalità batch, per processare video e generare documentazione;
2. modalità interrogazione, per fare domande alla knowledge base.

La modalità batch serve a produrre file Markdown completi.

La modalità interrogazione serve a usare il contenuto dei video come base di conoscenza.

---

# 6. Organizzazione modulare: core, CLI e GUI

Il progetto deve essere diviso in tre moduli principali.

## 6.1 Core

Il modulo `core` contiene tutta la logica indipendente dall’interfaccia utente.

Responsabilità principali:

- gestione configurazione;
- modelli dati;
- ingestion video;
- estrazione audio;
- trascrizione;
- estrazione frame;
- OCR;
- riconoscimento codice;
- chunking;
- embedding;
- indicizzazione Qdrant;
- retrieval RAG;
- generazione documentazione;
- revisione e validazione;
- export.

Il `core` non deve dipendere né dalla CLI né dalla GUI.

Regola architetturale:

```text
core non importa cli
core non importa gui
cli importa core
gui importa core
```

## 6.2 CLI

Il modulo `cli` espone il sistema da terminale.

Responsabilità principali:

- definire i comandi `videodoc`;
- validare gli argomenti utente;
- chiamare i servizi del `core`;
- mostrare stato, progressi, errori e risultati;
- permettere esecuzione batch e automazione.

La CLI deve essere leggera. Non deve contenere logica di pipeline complessa.

## 6.3 GUI

Il modulo `gui` fornisce un’interfaccia web opzionale per utenti meno tecnici.

Responsabilità principali:

- upload o selezione dei video;
- visualizzazione dello stato pipeline;
- consultazione trascrizioni, OCR e chunk;
- revisione blocchi codice;
- editor Markdown;
- chat RAG;
- export documentazione.

La GUI deve usare il `core` tramite servizi applicativi o API interne, senza duplicare la logica della CLI.

---

# 7. Stack tecnologico consigliato

## 7.1 Linguaggio principale

Il linguaggio consigliato è Python, perché dispone di ottime librerie per:

- elaborazione video;
- trascrizione audio;
- OCR;
- machine learning;
- database vettoriali;
- orchestrazione RAG;
- generazione file Markdown.

## 7.2 Componenti consigliati

| Area | Componente | Strumento consigliato |
|---|---|---|
| Core | Configurazione | YAML + Pydantic |
| Core | Estrazione audio/video | FFmpeg |
| Core | Trascrizione | faster-whisper |
| Core | OCR | PaddleOCR, Surya OCR o Tesseract |
| Core | Scene detection | PySceneDetect |
| Core | Embedding | bge-m3, nomic-embed-text, multilingual-e5-large |
| Core | Vector DB | Qdrant |
| Core | Database strutturato | SQLite |
| Core | LLM locale | Qwen Coder, Llama, Mistral, DeepSeek Coder |
| Core | Orchestrazione RAG | LlamaIndex o LangChain |
| Core | Export documentazione | Markdown, MkDocs, Docusaurus |
| CLI | Framework comandi | Typer |
| GUI | Backend | FastAPI |
| GUI | Frontend | React, Next.js o Streamlit |
| GUI | Worker opzionale | Celery, RQ o Dramatiq |

---

# 8. Struttura del progetto

Una possibile struttura del repository è la seguente:

```text
video-doc-rag/
├── src/
│   └── videodoc/
│       ├── __init__.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   ├── logging.py
│       │   ├── pipeline/
│       │   │   ├── __init__.py
│       │   │   ├── ingest_video.py
│       │   │   ├── extract_audio.py
│       │   │   ├── transcribe.py
│       │   │   ├── extract_frames.py
│       │   │   ├── ocr_frames.py
│       │   │   ├── detect_code.py
│       │   │   ├── chunking.py
│       │   │   ├── embeddings.py
│       │   │   ├── index.py
│       │   │   ├── retrieve.py
│       │   │   ├── generate_outline.py
│       │   │   ├── generate_docs.py
│       │   │   └── review_docs.py
│       │   ├── models/
│       │   │   ├── video_asset.py
│       │   │   ├── transcript_segment.py
│       │   │   ├── frame_observation.py
│       │   │   ├── code_block.py
│       │   │   ├── knowledge_chunk.py
│       │   │   └── doc_section.py
│       │   ├── prompts/
│       │   │   ├── outline.md
│       │   │   ├── section_generation.md
│       │   │   ├── code_explanation.md
│       │   │   ├── review.md
│       │   │   └── rag_answer.md
│       │   ├── storage/
│       │   │   ├── sqlite.py
│       │   │   ├── qdrant.py
│       │   │   └── filesystem.py
│       │   └── utils/
│       │       ├── timecode.py
│       │       ├── hashing.py
│       │       ├── markdown.py
│       │       └── video.py
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── app.py
│       │   ├── commands/
│       │   │   ├── init.py
│       │   │   ├── ingest.py
│       │   │   ├── transcribe.py
│       │   │   ├── frames.py
│       │   │   ├── ocr.py
│       │   │   ├── code.py
│       │   │   ├── chunk.py
│       │   │   ├── index.py
│       │   │   ├── generate.py
│       │   │   ├── review.py
│       │   │   ├── export.py
│       │   │   ├── ask.py
│       │   │   ├── status.py
│       │   │   └── inspect.py
│       │   └── output.py
│       └── gui/
│           ├── __init__.py
│           ├── api/
│           │   ├── main.py
│           │   ├── routes_projects.py
│           │   ├── routes_pipeline.py
│           │   ├── routes_docs.py
│           │   └── routes_chat.py
│           ├── services/
│           │   └── jobs.py
│           └── web/
│               ├── package.json
│               ├── src/
│               └── README.md
├── data/
│   ├── audio/
│   ├── frames/
│   ├── transcripts/
│   ├── ocr/
│   ├── chunks/
│   ├── indexes/
│   └── generated_docs/
├── projects/
│   └── esempio-corso/
│       ├── config.yaml
│       ├── sources.yaml
│       ├── videos/
│       ├── materials/
│       ├── workdir/
│       └── docs/
├── tests/
│   ├── core/
│   ├── cli/
│   └── gui/
├── docker-compose.yml
├── pyproject.toml
├── README.md
└── .env.example
```

## 8.1 Regola sulle dipendenze interne

Le dipendenze devono seguire questa direzione:

```text
cli  ─┐
      ├──> core
gui  ─┘
```

Il modulo `core` deve rimanere puro e riusabile.

## 8.2 Modello progetto per ogni RAG

Ogni volta che viene inizializzato un nuovo RAG, il sistema deve creare un progetto isolato. Il progetto rappresenta l’unità logica e fisica di lavoro: contiene le fonti, la configurazione, gli indici, i dati intermedi e la documentazione finale.

La cartella `videos/` è obbligatoria. Le cartelle `attachments/` e `codebase/` sono opzionali.

Struttura consigliata:

```text
projects/
└── corso-software-x/
    ├── config.yaml
    ├── sources.yaml
    ├── videos/              # required
    ├── attachments/         # optional: PDF, slide, documenti, note, zip, dataset
    ├── codebase/            # optional: repository o sorgenti collegati al corso
    ├── workdir/
    ├── indexes/
    └── docs/
```

Regole operative:

- se è presente solo `videos/`, il RAG viene creato esclusivamente da video, audio, trascrizione, frame, OCR e codice estratto dal video;
- se è presente anche `attachments/`, il RAG deve indicizzare i materiali allegati come fonti aggiuntive;
- se è presente anche `codebase/`, il RAG deve sincronizzare e indicizzare la codebase oltre a video, audio e allegati;
- ogni snippet derivato dalla codebase deve mantenere il riferimento al file sorgente, al percorso relativo, al linguaggio e, quando possibile, all’intervallo di righe;
- quando un frammento di codice compare sia nel video sia nella codebase, la codebase ha priorità per il contenuto esatto, mentre il video resta la fonte del contesto operativo e dei timestamp.

Esempio di progetto minimo:

```text
projects/corso-base/
├── config.yaml
├── sources.yaml
├── videos/
├── workdir/
└── docs/
```

Esempio di progetto completo:

```text
projects/corso-avanzato/
├── config.yaml
├── sources.yaml
├── videos/
│   ├── workshop_01.mp4
│   └── workshop_02.mp4
├── attachments/
│   ├── slides.pdf
│   └── appunti.md
├── codebase/
│   ├── package.json
│   ├── src/
│   └── README.md
├── workdir/
├── indexes/
└── docs/
```

## 8.3 Scansione delle fonti ed esclusioni

La scansione del progetto deve essere configurabile. Di default il sistema deve ignorare directory tecniche o non pertinenti, per evitare di indicizzare file generati, cache, dipendenze esterne o artefatti di build.

Esclusioni predefinite consigliate:

```text
.git/
.hg/
.svn/
node_modules/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.venv/
venv/
env/
dist/
build/
out/
target/
coverage/
.next/
.nuxt/
.cache/
.parcel-cache/
.turbo/
.vite/
.DS_Store
```

Le esclusioni devono essere modificabili tramite configurazione, permettendo sia di aggiungere nuove regole sia di rimuovere una regola predefinita quando una cartella normalmente ignorata è invece rilevante per il corso.

Esempio:

```yaml
scan:
  default_excludes: true
  add_excludes:
    - "tmp/"
    - "logs/"
    - "*.min.js"
  remove_excludes:
    - "dist/"
```

In questo esempio `tmp/`, `logs/` e i file `*.min.js` vengono esclusi, mentre `dist/` viene reinclusa anche se normalmente sarebbe ignorata come cartella di build.

---

# 9. Formato dei dati e metadati

Il sistema deve salvare informazioni strutturate per ogni video, segmento, frame, blocco di codice e sezione documentale.

## 9.1 Video asset

```json
{
  "video_id": "workshop_01",
  "video_name": "workshop_01_installazione.mp4",
  "title": "Installazione e setup iniziale",
  "duration_seconds": 7420,
  "language": "it",
  "hash": "abc123",
  "audio_path": "data/audio/workshop_01.wav",
  "transcript_path": "data/transcripts/workshop_01.json",
  "frames_path": "data/frames/workshop_01/",
  "ocr_path": "data/ocr/workshop_01.json",
  "chunks_path": "data/chunks/workshop_01.json"
}
```

## 9.2 Transcript segment

```json
{
  "segment_id": "seg_0001",
  "video_id": "workshop_01",
  "start_time": "00:00:12",
  "end_time": "00:00:28",
  "text": "In questa lezione vediamo come installare il software...",
  "confidence": 0.94
}
```

## 9.3 Frame observation

```json
{
  "frame_id": "frame_0042",
  "video_id": "workshop_01",
  "timestamp": "00:21:04",
  "image_path": "data/frames/workshop_01/frame_0042.jpg",
  "ocr_text": "npm create vite@latest my-app",
  "contains_code": true,
  "contains_terminal": true,
  "contains_editor": false,
  "confidence": 0.86
}
```

## 9.4 Code block

```json
{
  "code_block_id": "code_0012",
  "video_id": "workshop_01",
  "timestamp": "00:21:04",
  "language": "bash",
  "code": "npm create vite@latest my-app",
  "source": "ocr",
  "confidence": 0.86,
  "verified": false
}
```

## 9.5 Knowledge chunk

```json
{
  "chunk_id": "workshop_01_chunk_0007",
  "video_id": "workshop_01",
  "video_name": "workshop_01_installazione.mp4",
  "start_time": "00:18:20",
  "end_time": "00:24:55",
  "topic": "Creazione del primo progetto",
  "transcript": "...",
  "ocr_text": "...",
  "code_blocks": ["code_0012", "code_0013"],
  "source_type": "video",
  "metadata": {
    "language": "it",
    "confidence": 0.88
  }
}
```

## 9.6 Codebase snippet

Quando il progetto contiene una cartella `codebase/`, i file sorgenti devono essere indicizzati come snippet separati e collegati ai relativi file. Ogni snippet deve conservare il percorso relativo alla root della codebase.

```json
{
  "snippet_id": "codebase_src_app_main_py_001",
  "project_id": "corso-software-x",
  "source_type": "codebase",
  "file_path": "src/app/main.py",
  "language": "python",
  "start_line": 24,
  "end_line": 58,
  "symbol_name": "create_app",
  "content": "def create_app():\n    ...",
  "file_hash": "def456",
  "metadata": {
    "indexed_from": "codebase",
    "link": "codebase/src/app/main.py#L24-L58"
  }
}
```

## 9.7 Material attachment

Gli allegati caricati in `attachments/` devono essere tracciati come fonti documentali autonome.

```json
{
  "attachment_id": "slides_intro_pdf",
  "project_id": "corso-software-x",
  "source_type": "attachment",
  "file_path": "attachments/slides_intro.pdf",
  "mime_type": "application/pdf",
  "title": "Slide introduttive",
  "extracted_text_path": "workdir/attachments/slides_intro/text.json",
  "file_hash": "ghi789"
}
```

---

# 10. Pipeline completa

La pipeline completa deve essere eseguibile in modo automatico, ma ogni fase deve poter essere rilanciata singolarmente.

Esempio di flusso da CLI:

```bash
videodoc init corso-software-x
videodoc scan corso-software-x
videodoc ingest corso-software-x
videodoc sync-codebase corso-software-x
videodoc transcribe corso-software-x
videodoc frames corso-software-x
videodoc ocr corso-software-x
videodoc code corso-software-x
videodoc chunk corso-software-x
videodoc index corso-software-x
videodoc outline corso-software-x
videodoc generate corso-software-x
videodoc review corso-software-x
videodoc export corso-software-x --format mkdocs
```

Deve inoltre essere possibile eseguire tutto con un solo comando:

```bash
videodoc run corso-software-x
```

Lo stesso flusso deve essere avviabile anche dalla GUI, che internamente richiama i servizi del modulo `core`.

---

# 11. Modulo core

Il modulo `core` è il cuore del sistema.

Deve contenere:

- modelli dati;
- configurazione;
- servizi di pipeline;
- servizi RAG;
- storage locale;
- gestione file system;
- generazione e revisione documentazione.

## 11.1 Servizi principali

Esempi di servizi del core:

```text
ProjectService
SourceScanService
VideoIngestionService
AttachmentIngestionService
CodebaseSyncService
AudioExtractionService
TranscriptionService
FrameExtractionService
OCRService
CodeDetectionService
ChunkingService
EmbeddingService
IndexingService
RetrievalService
DocumentationService
ReviewService
ExportService
```

## 11.2 API interne del core

Il core dovrebbe esporre funzioni o classi utilizzabili sia da CLI sia da GUI.

Esempio concettuale:

```python
from videodoc.core.services import ProjectService, PipelineService

project = ProjectService.load("corso-software-x")
PipelineService(project).run_all()
```

## 11.3 Cosa non deve fare il core

Il core non deve:

- stampare direttamente output CLI complesso;
- dipendere da Typer;
- dipendere da React o Streamlit;
- contenere logica di routing HTTP;
- contenere codice specifico dell’interfaccia utente.

---

# 12. Modulo CLI

La CLI è il modo più semplice per usare e automatizzare il sistema.

## 12.1 Comandi consigliati

```bash
videodoc init <project_name>
videodoc scan <project_name>
videodoc ingest <project_name>
videodoc sync-codebase <project_name>
videodoc transcribe <project_name>
videodoc frames <project_name>
videodoc ocr <project_name>
videodoc code <project_name>
videodoc chunk <project_name>
videodoc index <project_name>
videodoc outline <project_name>
videodoc generate <project_name>
videodoc review <project_name>
videodoc export <project_name>
videodoc ask <project_name> "domanda"
videodoc status <project_name>
videodoc inspect <project_name> --timestamp 00:21:04
```

## 12.2 Comando status

Mostra lo stato del progetto:

```text
Project: corso-software-x
Videos: 8
Transcribed: 8/8
Frames extracted: 8/8
OCR completed: 7/8
Chunks generated: 8/8
Indexed: yes
Documentation generated: partial
```

## 12.3 Comando inspect

Permette di ispezionare un timestamp specifico:

```bash
videodoc inspect corso-software-x --video workshop_01.mp4 --timestamp 00:21:04
```

Output:

```text
Video: workshop_01.mp4
Timestamp: 00:21:04
Transcript: Ora lanciamo il comando per creare il progetto...
OCR: npm create vite@latest my-app
Detected code: npm create vite@latest my-app
Frame: data/frames/workshop_01/frame_0042.jpg
```

## 12.4 Regola di implementazione CLI

La CLI deve limitarsi a:

1. leggere argomenti;
2. caricare configurazione;
3. chiamare il core;
4. mostrare risultati.

Esempio concettuale:

```python
@app.command()
def transcribe(project_name: str):
    project = ProjectService.load(project_name)
    TranscriptionService(project).run()
```

---

# 13. Modulo GUI

La GUI è opzionale e deve essere costruita sopra il modulo `core`.

## 13.1 Obiettivo della GUI

La GUI serve a rendere il sistema utilizzabile anche senza terminale.

Funzioni utili:

- caricamento video;
- visualizzazione stato pipeline;
- player video con timestamp;
- visualizzazione trascrizione;
- visualizzazione OCR;
- revisione blocchi codice;
- editor Markdown;
- chat RAG;
- export documentazione.

## 13.2 Architettura GUI consigliata

```text
Backend: FastAPI
Frontend: React / Next.js
Database: SQLite + Qdrant
Worker: Celery / RQ / Dramatiq
```

Per una versione semplice si può usare Streamlit.

## 13.3 API web consigliate

Esempi di endpoint:

```text
GET    /projects
POST   /projects
GET    /projects/{project_id}/status
POST   /projects/{project_id}/run
POST   /projects/{project_id}/transcribe
POST   /projects/{project_id}/ocr
POST   /projects/{project_id}/generate
GET    /projects/{project_id}/docs
POST   /projects/{project_id}/ask
GET    /projects/{project_id}/videos/{video_id}/inspect
```

## 13.4 Regola di implementazione GUI

La GUI non deve duplicare la logica della CLI.

Deve chiamare il `core` direttamente o tramite un livello di servizi applicativi.

---

# 14. Fase 1 — Inizializzazione del progetto

La fase di inizializzazione crea una nuova cartella progetto con la configurazione base.

Comando:

```bash
videodoc init corso-software-x
```

Output atteso:

```text
projects/corso-software-x/
├── config.yaml
├── sources.yaml
├── videos/          # required
├── attachments/     # optional
├── codebase/        # optional
├── workdir/
├── indexes/
└── docs/
```

Il file `config.yaml` contiene le impostazioni principali della pipeline.

Il file `sources.yaml` contiene l’elenco delle fonti da processare.

Esempio:

```yaml
project_name: "Corso Software X"
language: "it"
output_format: "markdown"

llm:
  provider: "ollama"
  model: "qwen2.5-coder:14b"
  temperature: 0.1

embedding:
  provider: "local"
  model: "bge-m3"

transcription:
  engine: "faster-whisper"
  model: "large-v3"
  language: "it"

ocr:
  engine: "paddleocr"
  frame_interval_seconds: 8
  detect_scene_changes: true

retrieval:
  vector_db: "qdrant"
  top_k: 12
  hybrid_search: true

documentation:
  include_timestamps: true
  include_video_name: true
  include_code_explanation: true
  include_common_errors: true
  output_dir: "docs"

scan:
  default_excludes: true
  add_excludes: []
  remove_excludes: []
```

---

# 15. Fase 2 — Ingestion dei video

La fase di ingestion registra i video da processare.

Attività principali:

1. leggere i file video nella cartella `videos/`;
2. calcolare un hash del file;
3. estrarre durata, formato, risoluzione e codec;
4. registrare il video nel database SQLite;
5. creare una cartella di lavoro dedicata al video.

Esempio di comando:

```bash
videodoc ingest corso-software-x
```

Esempio di struttura generata:

```text
workdir/
└── workshop_01_installazione/
    ├── metadata.json
    ├── audio/
    ├── frames/
    ├── transcript/
    ├── ocr/
    └── chunks/
```

Questa fase deve essere idempotente. Se un video è già stato registrato e l’hash non è cambiato, non deve essere processato nuovamente.

## 15.1 Scansione progetto e sincronizzazione fonti

Prima dell’ingestion, il sistema deve eseguire una scansione della cartella progetto per identificare le fonti disponibili:

```text
projects/<project_name>/
├── videos/
├── attachments/
└── codebase/
```

La cartella `videos/` è obbligatoria. Se manca o non contiene video supportati, il progetto non può avviare la pipeline RAG.

Le cartelle `attachments/` e `codebase/` sono opzionali:

- `attachments/` viene usata per PDF, slide, documenti, note, file Markdown, archivi e altri materiali di supporto;
- `codebase/` viene usata per sorgenti, repository o esempi di codice collegati ai video.

Comando consigliato:

```bash
videodoc scan corso-software-x
```

Output atteso:

```text
Project: corso-software-x
Videos: 8 found
Attachments: 3 found
Codebase: present
Excluded directories: .git, node_modules, __pycache__, dist, build
Sources manifest updated: sources.yaml
```

Se `codebase/` è presente, il sistema deve sincronizzarla in modo idempotente:

```bash
videodoc sync-codebase corso-software-x
```

La sincronizzazione deve:

1. rispettare le esclusioni configurate;
2. calcolare hash dei file;
3. rilevare file nuovi, modificati o rimossi;
4. estrarre snippet per file, simboli o blocchi logici;
5. indicizzare gli snippet nel vector database;
6. conservare per ogni snippet il link al file relativo, per esempio `codebase/src/app/main.py#L24-L58`.

---

# 16. Fase 3 — Estrazione audio

L’audio viene estratto dal video per poter essere trascritto.

Comando FFmpeg consigliato:

```bash
ffmpeg -i workshop_01_installazione.mp4 \
  -vn \
  -acodec pcm_s16le \
  -ar 16000 \
  -ac 1 \
  workshop_01_installazione.wav
```

Spiegazione:

- `-i` indica il file di input;
- `-vn` rimuove il video dall’output;
- `pcm_s16le` produce audio WAV non compresso;
- `-ar 16000` imposta il sample rate a 16 kHz;
- `-ac 1` converte l’audio in mono.

L’audio estratto deve essere salvato nella cartella di lavoro del video.

---

# 17. Fase 4 — Trascrizione audio

La trascrizione serve a convertire il parlato in testo con timestamp.

Strumenti consigliati:

- faster-whisper;
- whisper.cpp;
- Whisper locale.

Output atteso:

```json
[
  {
    "start": 12.4,
    "end": 28.7,
    "text": "In questa lezione vediamo come installare il software..."
  }
]
```

La trascrizione deve essere conservata in formato JSON, non solo TXT, perché i timestamp sono fondamentali.

---

# 18. Fase 5 — Estrazione frame e screenshot

La trascrizione audio non basta per documentare video tecnici. È necessario estrarre frame dal video per recuperare:

- codice mostrato nell’editor;
- comandi nel terminale;
- interfacce grafiche;
- slide;
- menu e impostazioni;
- messaggi di errore.

Strategie possibili:

## 18.1 Frame a intervalli regolari

Esempio: un frame ogni 8 secondi.

```bash
ffmpeg -i workshop_01.mp4 -vf fps=1/8 frames/frame_%05d.jpg
```

Vantaggio: semplice.

Svantaggio: può generare molti frame inutili.

## 18.2 Scene detection

Usare PySceneDetect per estrarre frame quando cambia la scena.

Vantaggio: riduce frame duplicati.

Svantaggio: potrebbe perdere piccoli cambiamenti nel codice.

## 18.3 Estrazione guidata dal testo

Estrarre più frame quando nella trascrizione compaiono parole come:

- codice;
- comando;
- terminale;
- funzione;
- classe;
- file;
- configurazione;
- errore;
- copiamo;
- incolliamo;
- eseguiamo.

Questa è spesso la strategia migliore per video tecnici.

---

# 19. Fase 6 — OCR delle schermate

L’OCR serve a leggere il testo visibile nei frame.

Può recuperare:

- codice;
- nomi di file;
- comandi terminale;
- messaggi di errore;
- testi di interfaccia;
- titoli di slide.

Output consigliato:

```json
{
  "frame_id": "frame_0042",
  "timestamp": "00:21:04",
  "ocr_text": "npm create vite@latest my-app",
  "blocks": [
    {
      "text": "npm create vite@latest my-app",
      "bbox": [120, 430, 780, 460],
      "confidence": 0.86
    }
  ]
}
```

È importante conservare anche la confidenza dell’OCR.

---

# 20. Fase 7 — Riconoscimento ed estrazione del codice

Dopo l’OCR, il sistema deve identificare quali parti del testo sono codice.

Il codice può apparire in:

- terminale;
- editor;
- notebook;
- slide;
- browser;
- file di configurazione;
- console di debug.

## 20.1 Classificazione del contenuto

Ogni blocco OCR può essere classificato come:

```text
plain_text
terminal_command
source_code
configuration
error_message
file_path
ui_label
```

## 20.2 Riconoscimento del linguaggio

Il sistema deve provare a identificare il linguaggio:

- bash;
- Python;
- JavaScript;
- TypeScript;
- JSON;
- YAML;
- HTML;
- CSS;
- SQL;
- Dockerfile;
- altro.

## 20.3 Deduplicazione del codice

Nei video lo stesso comando può restare a schermo per molti secondi. Il sistema deve evitare di salvare dieci volte lo stesso blocco.

Strategie:

- normalizzazione whitespace;
- hashing del testo;
- similarità testuale;
- confronto tra frame vicini.

## 20.4 Validazione del codice

Quando possibile, il codice deve essere validato.

Esempi:

- JSON può essere verificato con un parser JSON;
- YAML può essere verificato con un parser YAML;
- Python può essere verificato con `ast.parse`;
- comandi shell possono essere solo classificati, non necessariamente eseguiti.

---

# 21. Fase 8 — Chunking intelligente

Il chunking è una delle parti più importanti del progetto.

Un chunk non deve essere troppo piccolo, perché perderebbe contesto. Non deve essere troppo grande, perché renderebbe il retrieval poco preciso.

Un buon chunk per video tecnici può coprire da 2 a 8 minuti, a seconda della densità del contenuto.

## 21.1 Criteri per creare chunk

Il sistema deve considerare:

- pause nel parlato;
- cambio argomento;
- cambio schermata;
- presenza di codice;
- inizio/fine di una procedura;
- parole chiave;
- titoli di slide;
- azioni nel software.

## 21.2 Struttura del chunk

```json
{
  "chunk_id": "workshop_01_chunk_0007",
  "start_time": "00:18:20",
  "end_time": "00:24:55",
  "topic": "Creazione del primo progetto",
  "summary": "Viene creato il primo progetto tramite terminale.",
  "transcript": "...",
  "ocr_text": "...",
  "code_blocks": [
    {
      "language": "bash",
      "code": "npm create vite@latest my-app",
      "timestamp": "00:21:04"
    }
  ],
  "video_name": "workshop_01_installazione.mp4"
}
```

## 21.3 Chunk separati per codice

È utile indicizzare anche i blocchi di codice come documenti separati, collegati al chunk principale.

---

# 22. Fase 9 — Creazione degli embedding

Gli embedding trasformano i chunk in vettori numerici, così possono essere cercati semanticamente.

Ogni chunk può generare diversi embedding:

1. embedding del transcript;
2. embedding dell’OCR;
3. embedding del codice;
4. embedding del riassunto;
5. embedding combinato.

Modelli consigliati:

- `bge-m3`;
- `nomic-embed-text`;
- `multilingual-e5-large`;
- `jina-embeddings-v2`.

Per contenuti italiani e tecnici, è preferibile usare un modello multilingua di buona qualità.

---

# 23. Fase 10 — Indicizzazione nel vector database

Il vector database conserva gli embedding e permette retrieval semantico.

Qdrant è una scelta adatta perché può essere usato sia localmente sia in modalità server.

Ogni record indicizzato deve contenere:

```json
{
  "id": "workshop_01_chunk_0007",
  "vector": [0.012, -0.032, 0.221],
  "payload": {
    "project_id": "corso-software-x",
    "video_name": "workshop_01_installazione.mp4",
    "start_time": "00:18:20",
    "end_time": "00:24:55",
    "topic": "Creazione del primo progetto",
    "text": "...",
    "source_type": "transcript_ocr_code"
  }
}
```

Payload consigliati:

- `project_id`;
- `video_id`;
- `video_name`;
- `start_time`;
- `end_time`;
- `topic`;
- `source_type`;
- `language`;
- `contains_code`;
- `confidence`.

---

# 24. Fase 11 — Retrieval e RAG

Il RAG serve a recuperare le fonti più rilevanti prima di generare una risposta o una sezione documentale.

Flusso:

```text
Domanda o titolo sezione
   ↓
Embedding della query
   ↓
Ricerca nel vector database
   ↓
Recupero chunk rilevanti
   ↓
Reranking opzionale
   ↓
Prompt al LLM con fonti
   ↓
Risposta o sezione Markdown
```

Il prompt deve obbligare il modello a usare solo le fonti fornite.

Regola fondamentale:

```text
Se una procedura, un comando o una spiegazione non appare nelle fonti recuperate, il modello non deve inventarla.
```

---

# 25. Fase 12 — Generazione dell’indice della documentazione

Prima di generare le sezioni, il sistema deve creare un outline generale.

Input:

- titoli dei video;
- sommari dei chunk;
- argomenti principali;
- codice rilevante;
- eventuali materiali allegati.

Output:

```markdown
# Documentazione Software X

## 1. Introduzione
## 2. Installazione
## 3. Configurazione ambiente
## 4. Creazione del primo progetto
## 5. Funzionalità principali
## 6. Debug e troubleshooting
## 7. Deployment
## 8. Appendici
```

L’outline deve essere salvato e modificabile manualmente.

---

# 26. Fase 13 — Generazione delle sezioni Markdown

Ogni sezione deve essere generata separatamente.

Per ogni sezione:

1. leggere il titolo e la descrizione dall’outline;
2. recuperare i chunk rilevanti;
3. recuperare eventuale codice collegato;
4. creare prompt con fonti;
5. generare Markdown;
6. salvare file `.md`;
7. registrare le fonti usate.

Struttura consigliata:

```markdown
# Titolo sezione

## Obiettivo

## Fonti utilizzate

## Spiegazione dettagliata

## Procedura passo-passo

## Codice esaminato

## Spiegazione del codice

## Risultato atteso

## Errori comuni

## Riferimenti
```

Ogni sezione deve contenere il nome del video e i timestamp.

---

# 27. Fase 14 — Revisione, validazione e controllo qualità

La generazione automatica deve essere controllata.

Il sistema deve eseguire una revisione automatica per verificare:

- presenza dei riferimenti video;
- presenza dei timestamp;
- coerenza tra procedura e fonti;
- codice completo;
- codice non duplicato inutilmente;
- sezioni vuote;
- affermazioni non supportate;
- Markdown valido.

## 27.1 Controllo anti-allucinazione

Il sistema deve confrontare ogni sezione generata con le fonti usate.

Se trova frasi non supportate, deve marcarle.

Esempio:

```markdown
> Revisione richiesta: questa affermazione non è stata trovata chiaramente nelle fonti.
```

## 27.2 Controllo codice

Il codice deve essere classificato come:

```text
verified
high_confidence
ocr_extracted
reconstructed
needs_review
```

Se il codice deriva da OCR incerto, deve essere segnalato.

---

# 28. Fase 15 — Export della documentazione

Il formato principale è Markdown.

Formati esportabili:

- cartella Markdown semplice;
- MkDocs;
- Docusaurus;
- GitHub Pages;
- PDF;
- HTML statico.

## 28.1 Export MkDocs

Struttura:

```text
site/
├── mkdocs.yml
└── docs/
    ├── index.md
    ├── installazione.md
    └── configurazione.md
```

Esempio `mkdocs.yml`:

```yaml
site_name: Documentazione Software X
site_description: Documentazione generata dai workshop video
theme:
  name: material
nav:
  - Home: index.md
  - Installazione: installazione.md
  - Configurazione: configurazione.md
```

---

# 29. Configurazione del progetto

Esempio completo di `config.yaml`:

```yaml
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

ocr:
  engine: "paddleocr"
  languages:
    - "it"
    - "en"
  min_confidence: 0.65

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

documentation:
  format: "markdown"
  include_video_name: true
  include_timestamps: true
  include_code_explanation: true
  include_expected_result: true
  include_common_errors: true
  include_sources_section: true

gui:
  enabled: false
  backend: "fastapi"
  frontend: "react"
  host: "127.0.0.1"
  port: 8000
```

---

# 30. Schema database SQLite

SQLite serve per salvare metadati strutturati.

## 30.1 Tabella projects

```sql
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    language TEXT,
    created_at TEXT,
    updated_at TEXT
);
```

## 30.2 Tabella videos

```sql
CREATE TABLE videos (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    title TEXT,
    duration_seconds REAL,
    file_hash TEXT,
    path TEXT,
    created_at TEXT,
    FOREIGN KEY(project_id) REFERENCES projects(id)
);
```

## 30.3 Tabella transcript_segments

```sql
CREATE TABLE transcript_segments (
    id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    start_seconds REAL NOT NULL,
    end_seconds REAL NOT NULL,
    text TEXT NOT NULL,
    confidence REAL,
    FOREIGN KEY(video_id) REFERENCES videos(id)
);
```

## 30.4 Tabella frames

```sql
CREATE TABLE frames (
    id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    timestamp_seconds REAL NOT NULL,
    image_path TEXT NOT NULL,
    perceptual_hash TEXT,
    ocr_text TEXT,
    ocr_confidence REAL,
    contains_code INTEGER DEFAULT 0,
    FOREIGN KEY(video_id) REFERENCES videos(id)
);
```

## 30.5 Tabella code_blocks

```sql
CREATE TABLE code_blocks (
    id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    chunk_id TEXT,
    timestamp_seconds REAL,
    language TEXT,
    code TEXT NOT NULL,
    source TEXT,
    confidence REAL,
    verified INTEGER DEFAULT 0,
    FOREIGN KEY(video_id) REFERENCES videos(id)
);
```

## 30.5.1 Tabella source_files

```sql
CREATE TABLE source_files (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    language TEXT,
    file_hash TEXT,
    size_bytes INTEGER,
    indexed_at TEXT,
    FOREIGN KEY(project_id) REFERENCES projects(id)
);
```

## 30.5.2 Tabella codebase_snippets

```sql
CREATE TABLE codebase_snippets (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_file_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    language TEXT,
    symbol_name TEXT,
    start_line INTEGER,
    end_line INTEGER,
    content TEXT NOT NULL,
    file_hash TEXT,
    FOREIGN KEY(project_id) REFERENCES projects(id),
    FOREIGN KEY(source_file_id) REFERENCES source_files(id)
);
```

## 30.6 Tabella chunks

```sql
CREATE TABLE chunks (
    id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    start_seconds REAL NOT NULL,
    end_seconds REAL NOT NULL,
    topic TEXT,
    summary TEXT,
    transcript TEXT,
    ocr_text TEXT,
    metadata_json TEXT,
    FOREIGN KEY(video_id) REFERENCES videos(id)
);
```

## 30.7 Tabella doc_sections

```sql
CREATE TABLE doc_sections (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    slug TEXT NOT NULL,
    markdown_path TEXT,
    source_chunks_json TEXT,
    generated_at TEXT,
    reviewed INTEGER DEFAULT 0,
    FOREIGN KEY(project_id) REFERENCES projects(id)
);
```

---

# 31. Schema Qdrant

Ogni chunk deve essere indicizzato in Qdrant con payload ricco.

Esempio payload:

```json
{
  "project_id": "corso-software-x",
  "video_id": "workshop_01",
  "video_name": "workshop_01_installazione.mp4",
  "start_time": "00:18:20",
  "end_time": "00:24:55",
  "topic": "Creazione del primo progetto",
  "source_type": "chunk",
  "contains_code": true,
  "language": "it",
  "confidence": 0.88,
  "text": "Trascrizione, OCR e codice combinati..."
}
```

È utile creare più collection:

```text
project_chunks
project_code_blocks
project_frames
project_attachments
project_codebase_files
project_codebase_snippets
```

Oppure una sola collection con `source_type` differenziato.

Per gli snippet della codebase, il payload deve includere sempre il riferimento al file:

```json
{
  "project_id": "corso-software-x",
  "source_type": "codebase_snippet",
  "file_path": "src/app/main.py",
  "language": "python",
  "symbol_name": "create_app",
  "start_line": 24,
  "end_line": 58,
  "link": "codebase/src/app/main.py#L24-L58",
  "text": "def create_app(): ..."
}
```

Nel retrieval, quando una risposta usa uno snippet della codebase, la sezione `Fonti` deve riportare il percorso del file e, quando disponibili, le righe.

---

# 32. Prompt principali

## 32.1 Prompt per generare outline

```text
Sei un technical writer esperto.

Devi creare l’indice di una documentazione tecnica a partire dai contenuti estratti da video workshop.

Usa solo le informazioni presenti nelle fonti.
Organizza l’indice in modo logico e progressivo.
Non inventare argomenti non presenti.
Raggruppa contenuti simili.
Evidenzia eventuali sezioni che richiedono revisione umana.

Fonti:
{{sources}}

Output richiesto:
Markdown con titolo principale e sezioni numerate.
```

## 32.2 Prompt per generare una sezione

```text
Sei un technical writer specializzato in documentazione software.

Genera una sezione Markdown dettagliata usando esclusivamente le fonti fornite.

Regole obbligatorie:
- Non inventare passaggi non presenti nelle fonti.
- Includi nome del video e timestamp.
- Spiega il procedimento passo-passo.
- Includi tutto il codice rilevante.
- Spiega ogni blocco di codice.
- Se il codice deriva da OCR incerto, segnalalo.
- Non rimuovere dettagli tecnici importanti.
- Usa un linguaggio chiaro e didattico.
- Mantieni la struttura Markdown.

Titolo sezione:
{{section_title}}

Fonti:
{{retrieved_chunks}}

Output:
Markdown completo.
```

## 32.3 Prompt per spiegare codice

```text
Analizza il seguente blocco di codice.

Spiega:
1. a cosa serve;
2. come funziona;
3. quali parametri o parti sono importanti;
4. quale risultato produce;
5. eventuali errori comuni.

Codice:
{{code}}

Contesto video:
{{context}}
```

## 32.4 Prompt per revisione

```text
Verifica la seguente sezione Markdown confrontandola con le fonti.

Controlla:
- affermazioni non supportate;
- codice non presente nelle fonti;
- timestamp mancanti;
- passaggi procedurali poco chiari;
- duplicazioni;
- errori Markdown.

Se trovi problemi, restituisci una lista di correzioni.

Sezione:
{{markdown}}

Fonti:
{{sources}}
```

---

# 33. Gestione del codice estratto dai video

Il codice è la parte più delicata del progetto.

Il sistema deve distinguere tra codice:

```text
1. preso da file sorgente allegati;
2. letto chiaramente tramite OCR;
3. ricostruito da OCR e trascrizione;
4. ipotizzato dal modello.
```

Il quarto caso deve essere evitato o marcato esplicitamente come non verificato.

## 33.1 Strict mode

In strict mode il sistema include solo codice:

- proveniente da file sorgenti;
- letto da OCR con confidenza alta;
- validato da parser o regole semplici.

## 33.2 Assistive mode

In assistive mode il sistema può ricostruire codice incompleto, ma deve marcarlo.

Esempio:

```markdown
> Nota: il seguente blocco è stato ricostruito combinando OCR e trascrizione. Verificare prima dell’uso.
```

## 33.3 Verifica umana

Il sistema dovrebbe produrre un report dei blocchi di codice da controllare:

```text
code_review_report.md
```

Con contenuto simile:

````markdown
# Blocchi di codice da verificare

## workshop_01.mp4 — 00:21:04

Confidenza OCR: 0.61

```bash
npm create vite@latest my-app
```

Motivo revisione: OCR sotto soglia minima.
````

---

# 34. Gestione dei materiali allegati e della codebase

I video non dovrebbero essere l’unica fonte.

Il sistema deve poter importare materiali da due aree opzionali del progetto:

```text
attachments/
codebase/
```

La cartella `attachments/` può contenere:

- file `.zip`;
- notebook;
- slide;
- PDF;
- documenti Markdown;
- documenti testuali;
- configurazioni;
- dataset di esempio.

La cartella `codebase/` può contenere:

- repository Git copiati localmente;
- file sorgenti;
- esempi applicativi;
- configurazioni di progetto;
- script;
- test;
- documentazione tecnica collegata al codice.

I materiali allegati e la codebase sono spesso più affidabili del codice letto da video.

Se un comando o un file appare sia nel video sia nella codebase, la codebase deve avere priorità per il codice esatto, mentre il video fornisce il contesto procedurale, il timestamp e la spiegazione mostrata durante il workshop.

Ogni snippet proveniente dalla codebase deve essere citabile nella documentazione con un riferimento simile a:

```markdown
Fonte codice: `codebase/src/app/main.py#L24-L58`
```

Il sistema deve evitare di indicizzare cartelle non pertinenti come `.git`, `node_modules`, `__pycache__` e artefatti di build, salvo diversa configurazione.

---

# 35. Modalità operative

## 35.1 Modalità documentazione

Genera documentazione completa.

```bash
videodoc generate corso-software-x
```

## 35.2 Modalità domanda-risposta

Permette di interrogare i video.

```bash
videodoc ask corso-software-x "Come si configura il database?"
```

Risposta attesa:

```markdown
La configurazione del database viene mostrata nel video `workshop_03_database.mp4`, tra `00:12:10` e `00:18:45`.

La procedura consiste in...
```

## 35.3 Modalità rigenerazione parziale

Rigenera solo una sezione.

```bash
videodoc regenerate corso-software-x --section "Configurazione database"
```

## 35.4 Modalità ispezione

Mostra fonti grezze collegate a un timestamp.

```bash
videodoc inspect corso-software-x --video workshop_03.mp4 --timestamp 00:14:20
```

## 35.5 Modalità GUI

Avvia l’interfaccia web.

```bash
videodoc gui corso-software-x
```

Oppure, in modalità sviluppo:

```bash
videodoc gui dev corso-software-x
```

---

# 36. Roadmap di sviluppo

## 36.1 MVP 1 — Core pipeline base

Obiettivo: trasformare un video in Markdown usando trascrizione audio.

Funzioni:

- struttura `core`;
- modelli dati;
- configurazione progetto;
- ingestion video;
- estrazione audio;
- trascrizione;
- chunking temporale;
- generazione Markdown semplice.

## 36.2 MVP 2 — CLI completa

Obiettivo: usare il sistema da terminale.

Funzioni:

- modulo `cli`;
- comandi Typer;
- `init`, `ingest`, `transcribe`, `chunk`, `generate`;
- comando `status`;
- comando `inspect`.

## 36.3 MVP 3 — OCR e codice

Obiettivo: recuperare codice e informazioni visive.

Funzioni:

- estrazione frame;
- OCR;
- deduplicazione frame;
- riconoscimento blocchi codice;
- codice incluso nella documentazione.

## 36.4 MVP 4 — RAG completo

Obiettivo: interrogare i contenuti.

Funzioni:

- embedding locali;
- Qdrant;
- retrieval;
- chat RAG;
- generazione sezioni tramite retrieval.

## 36.5 MVP 5 — Multi-video ed export

Obiettivo: generare una documentazione completa da più workshop.

Funzioni:

- outline globale;
- generazione sezione per sezione;
- riferimenti multi-video;
- export MkDocs.

## 36.6 MVP 6 — GUI

Obiettivo: rendere il sistema usabile da utenti non tecnici.

Funzioni:

- dashboard;
- editor Markdown;
- revisione codice;
- approvazione sezioni;
- chat RAG;
- rigenerazione parziale;
- export da interfaccia.

---

# 37. Best practice

## 37.1 Salvare sempre i dati intermedi

Non bisogna cancellare trascrizioni, OCR, frame o chunk dopo la generazione.

Questi dati permettono di:

- rigenerare documentazione;
- correggere errori;
- cambiare modello;
- migliorare prompt;
- fare audit delle fonti.

## 37.2 Non fidarsi ciecamente dell’OCR

L’OCR può sbagliare caratteri importanti. Il codice va sempre marcato con una confidenza.

## 37.3 Usare materiali originali quando disponibili

Repository, slide e file sorgenti sono spesso più precisi del video.

## 37.4 Generare una sezione alla volta

Questo riduce errori e migliora qualità.

## 37.5 Mantenere timestamp ovunque

I timestamp rendono la documentazione verificabile.

## 37.6 Separare generazione e revisione

La pipeline deve generare, poi revisionare. Non bisogna considerare la prima generazione come definitiva.

## 37.7 Tenere separati core, CLI e GUI

La logica deve vivere nel `core`.

La CLI e la GUI devono essere solo interfacce verso il motore applicativo.

---

# 38. Limiti del sistema

Il sistema può essere molto utile, ma ha limiti importanti.

## 38.1 Codice non sempre leggibile

Se il video è compresso, sfocato o il font è piccolo, l’OCR può fallire.

## 38.2 Audio ambiguo

La trascrizione può contenere errori, soprattutto con termini tecnici, nomi di librerie o accenti.

## 38.3 Azioni grafiche difficili da descrivere

Alcune azioni svolte nell’interfaccia possono non essere comprese correttamente senza un modello multimodale.

## 38.4 Rischio allucinazioni

Il LLM può inventare dettagli se il prompt non è rigido o se le fonti sono incomplete.

## 38.5 Necessità di revisione umana

Per documentazione professionale, soprattutto con codice, è necessaria una fase di revisione.

## 38.6 Complessità della GUI

La GUI aumenta la complessità del progetto. Per questo dovrebbe arrivare dopo un `core` stabile e una CLI funzionante.

---

# 39. Esempio di output Markdown generato

````markdown
# Installazione dell’ambiente

**Video di riferimento:** `workshop_01_installazione.mp4`  
**Timestamp:** `00:04:12–00:16:40`

## Obiettivo

Questa sezione spiega come preparare l’ambiente di lavoro necessario per seguire il corso. L’obiettivo è installare gli strumenti di base, verificare che siano disponibili da terminale e creare una cartella di lavoro dedicata al progetto.

## Procedura passo-passo

1. Aprire il terminale.
2. Verificare che Node.js sia installato.
3. Verificare che npm sia disponibile.
4. Creare una nuova cartella di progetto.
5. Spostarsi nella cartella appena creata.

## Codice mostrato

```bash
node -v
npm -v
mkdir my-project
cd my-project
```

## Spiegazione del codice

Il comando `node -v` mostra la versione di Node.js installata nel sistema. Il comando `npm -v` verifica la presenza di npm, il package manager usato per installare dipendenze JavaScript.

Il comando `mkdir my-project` crea una nuova cartella chiamata `my-project`. Il comando `cd my-project` sposta il terminale all’interno della cartella.

## Risultato atteso

Al termine della procedura, il terminale deve trovarsi nella cartella del progetto e i comandi `node -v` e `npm -v` devono restituire una versione valida.

## Fonte

- Video: `workshop_01_installazione.mp4`
- Timestamp: `00:04:12–00:16:40`
````

---

# 40. Conclusione

VideoDocRAG permette di trasformare video tecnici lunghi e difficili da consultare in documentazione Markdown strutturata, navigabile, interrogabile e versionabile.

La parte più importante non è soltanto usare un LLM locale, ma costruire una pipeline robusta che gestisca correttamente:

- trascrizione audio;
- contenuto visivo;
- codice mostrato a schermo;
- chunking;
- metadati;
- retrieval;
- generazione sezione per sezione;
- revisione;
- tracciabilità delle fonti.

La nuova separazione in `core`, `cli` e `gui` rende il progetto più pulito e manutenibile:

```text
core = logica applicativa e pipeline
cli  = interfaccia da terminale
gui  = interfaccia web opzionale
```

La forma più efficace è una pipeline modulare:

```text
Progetto → Scansione fonti → Video/Audio → Trascrizione → Frame → OCR → Codebase/Allegati → Chunk → Embedding → RAG → Markdown → Revisione → Export
```

Con questa architettura è possibile creare una base solida per generare documentazione tecnica da workshop, corsi, tutorial, demo software e registrazioni interne, mantenendo sempre il collegamento tra ogni informazione generata e la fonte video originale.
