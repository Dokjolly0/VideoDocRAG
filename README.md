# VideoDocRAG - Sistema locale per trasformare video tecnici in documentazione Markdown tramite RAG

## Indice

1. [Obiettivo del progetto](#1-obiettivo-del-progetto)
2. [Problema che il progetto risolve](#2-problema-che-il-progetto-risolve)
3. [Risultato finale atteso](#3-risultato-finale-atteso)
4. [Principi di progettazione](#4-principi-di-progettazione)
5. [Architettura generale](#5-architettura-generale)
6. [Stack tecnologico consigliato](#6-stack-tecnologico-consigliato)
7. [Struttura del progetto](#7-struttura-del-progetto)
8. [Formato dei dati e metadati](#8-formato-dei-dati-e-metadati)
9. [Pipeline completa](#9-pipeline-completa)
10. [Fase 1 — Inizializzazione del progetto](#10-fase-1--inizializzazione-del-progetto)
11. [Fase 2 — Ingestion dei video](#11-fase-2--ingestion-dei-video)
12. [Fase 3 — Estrazione audio](#12-fase-3--estrazione-audio)
13. [Fase 4 — Trascrizione audio](#13-fase-4--trascrizione-audio)
14. [Fase 5 — Estrazione frame e screenshot](#14-fase-5--estrazione-frame-e-screenshot)
15. [Fase 6 — OCR delle schermate](#15-fase-6--ocr-delle-schermate)
16. [Fase 7 — Riconoscimento ed estrazione del codice](#16-fase-7--riconoscimento-ed-estrazione-del-codice)
17. [Fase 8 — Chunking intelligente](#17-fase-8--chunking-intelligente)
18. [Fase 9 — Creazione degli embedding](#18-fase-9--creazione-degli-embedding)
19. [Fase 10 — Indicizzazione nel vector database](#19-fase-10--indicizzazione-nel-vector-database)
20. [Fase 11 — Retrieval e RAG](#20-fase-11--retrieval-e-rag)
21. [Fase 12 — Generazione dell’indice della documentazione](#21-fase-12--generazione-dellindice-della-documentazione)
22. [Fase 13 — Generazione delle sezioni Markdown](#22-fase-13--generazione-delle-sezioni-markdown)
23. [Fase 14 — Revisione, validazione e controllo qualità](#23-fase-14--revisione-validazione-e-controllo-qualità)
24. [Fase 15 — Export della documentazione](#24-fase-15--export-della-documentazione)
25. [CLI del progetto](#25-cli-del-progetto)
26. [Configurazione del progetto](#26-configurazione-del-progetto)
27. [Schema database SQLite](#27-schema-database-sqlite)
28. [Schema Qdrant](#28-schema-qdrant)
29. [Prompt principali](#29-prompt-principali)
30. [Gestione del codice estratto dai video](#30-gestione-del-codice-estratto-dai-video)
31. [Gestione dei materiali allegati](#31-gestione-dei-materiali-allegati)
32. [Modalità operative](#32-modalità-operative)
33. [Interfaccia web opzionale](#33-interfaccia-web-opzionale)
34. [Roadmap di sviluppo](#34-roadmap-di-sviluppo)
35. [Best practice](#35-best-practice)
36. [Limiti del sistema](#36-limiti-del-sistema)
37. [Esempio di output Markdown generato](#37-esempio-di-output-markdown-generato)
38. [Conclusione](#38-conclusione)

---

# 1. Obiettivo del progetto

L’obiettivo del progetto è creare un sistema riusabile, preferibilmente locale, capace di trasformare video tecnici, workshop, corsi, registrazioni di demo software e tutorial in una documentazione testuale dettagliata, strutturata e navigabile in formato Markdown.

Il sistema deve analizzare video di lunga durata, estrarre le informazioni principali, comprendere le procedure mostrate, recuperare eventuale codice visualizzato a schermo, collegare ogni informazione al video di origine e generare documentazione tecnica completa.

Il progetto non deve essere limitato a un singolo software o a un singolo corso. Deve essere progettato come una pipeline general-purpose, configurabile e riutilizzabile su materiali diversi.

L’obiettivo finale è ottenere un sistema in grado di prendere in input una cartella contenente video e materiali opzionali, per esempio repository, file sorgenti, slide, PDF o note, e produrre automaticamente una documentazione Markdown organizzata in sezioni, completa di spiegazioni, codice, procedure passo-passo, timestamp e riferimenti alle fonti.

Il sistema deve inoltre creare una base di conoscenza interrogabile tramite RAG, cioè Retrieval-Augmented Generation, così da poter fare domande ai contenuti dei video e generare nuove sezioni documentali basandosi sulle fonti estratte.

In sintesi, il progetto deve permettere di passare da questo scenario:

```text
Cartella con video workshop di molte ore
```

a questo risultato:

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

ma il comando è visibile solo a schermo. In questo caso la trascrizione audio non contiene il codice, quindi il sistema deve anche analizzare le immagini del video tramite OCR o modelli multimodali.

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

Un esempio di struttura attesa per una sezione:

```markdown
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

Il comando `npm create vite@latest my-app` crea una nuova applicazione...

## Risultato atteso

Al termine della procedura, l’applicazione dovrebbe essere disponibile in locale.

## Fonte

- Video: `workshop_01_installazione.mp4`
- Timestamp: `00:18:20–00:24:55`
```

---

# 4. Principi di progettazione

Il progetto deve essere costruito seguendo alcuni principi fondamentali.

## 4.1 Modularità

Ogni fase della pipeline deve essere indipendente. La trascrizione, l’OCR, il chunking, l’indicizzazione e la generazione documentale devono essere moduli separati.

Questo permette di sostituire facilmente un componente con un altro. Per esempio, si potrebbe iniziare con PaddleOCR e in futuro sostituirlo con Surya OCR o con un modello multimodale locale.

## 4.2 Tracciabilità

Ogni informazione generata deve poter essere ricondotta alla fonte originale. Questo significa che ogni chunk deve conservare:

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

Il sistema avrà due modalità principali:

1. modalità batch, per processare video e generare documentazione;
2. modalità interrogazione, per fare domande alla knowledge base.

La modalità batch serve a produrre file Markdown completi.

La modalità interrogazione serve a usare il contenuto dei video come base di conoscenza.

---

# 6. Stack tecnologico consigliato

## 6.1 Linguaggio principale

Il linguaggio consigliato è Python, perché dispone di ottime librerie per:

- elaborazione video;
- trascrizione audio;
- OCR;
- machine learning;
- database vettoriali;
- orchestrazione RAG;
- generazione file Markdown.

## 6.2 Componenti consigliati

| Componente | Strumento consigliato |
|---|---|
| CLI | Typer |
| Configurazione | YAML + Pydantic |
| Estrazione audio/video | FFmpeg |
| Trascrizione | faster-whisper |
| OCR | PaddleOCR, Surya OCR o Tesseract |
| Scene detection | PySceneDetect |
| Embedding | bge-m3, nomic-embed-text, multilingual-e5-large |
| Vector DB | Qdrant |
| Database strutturato | SQLite |
| LLM locale | Qwen Coder, Llama, Mistral, DeepSeek Coder |
| Orchestrazione RAG | LlamaIndex o LangChain |
| Export documentazione | Markdown, MkDocs, Docusaurus |
| UI opzionale | FastAPI + React oppure Streamlit |

---

# 7. Struttura del progetto

Una possibile struttura del repository è la seguente:

```text
video-doc-rag/
├── app/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── logging.py
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── ingest_video.py
│   │   ├── extract_audio.py
│   │   ├── transcribe.py
│   │   ├── extract_frames.py
│   │   ├── ocr_frames.py
│   │   ├── detect_code.py
│   │   ├── chunking.py
│   │   ├── embeddings.py
│   │   ├── index.py
│   │   ├── retrieve.py
│   │   ├── generate_outline.py
│   │   ├── generate_docs.py
│   │   └── review_docs.py
│   ├── models/
│   │   ├── video_asset.py
│   │   ├── transcript_segment.py
│   │   ├── frame_observation.py
│   │   ├── code_block.py
│   │   ├── knowledge_chunk.py
│   │   └── doc_section.py
│   ├── prompts/
│   │   ├── outline.md
│   │   ├── section_generation.md
│   │   ├── code_explanation.md
│   │   ├── review.md
│   │   └── rag_answer.md
│   ├── storage/
│   │   ├── sqlite.py
│   │   ├── qdrant.py
│   │   └── filesystem.py
│   └── utils/
│       ├── timecode.py
│       ├── hashing.py
│       ├── markdown.py
│       └── video.py
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
│       └── docs/
├── tests/
├── docker-compose.yml
├── pyproject.toml
├── README.md
└── .env.example
```

---

# 8. Formato dei dati e metadati

Il sistema deve salvare informazioni strutturate per ogni video, segmento, frame, blocco di codice e sezione documentale.

## 8.1 Video asset

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

## 8.2 Transcript segment

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

## 8.3 Frame observation

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

## 8.4 Code block

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

## 8.5 Knowledge chunk

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

---

# 9. Pipeline completa

La pipeline completa deve essere eseguibile in modo automatico, ma ogni fase deve poter essere rilanciata singolarmente.

Esempio di flusso:

```bash
videodoc init corso-software-x
videodoc ingest corso-software-x
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

---

# 10. Fase 1 — Inizializzazione del progetto

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
├── videos/
├── materials/
├── workdir/
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
```

---

# 11. Fase 2 — Ingestion dei video

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

---

# 12. Fase 3 — Estrazione audio

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

# 13. Fase 4 — Trascrizione audio

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

La trascrizione deve poi essere normalizzata in segmenti coerenti.

Esempio di segmento normalizzato:

```json
{
  "start_time": "00:00:12",
  "end_time": "00:00:28",
  "text": "In questa lezione vediamo come installare il software..."
}
```

---

# 14. Fase 5 — Estrazione frame e screenshot

La trascrizione audio non basta per documentare video tecnici. È necessario estrarre frame dal video per recuperare:

- codice mostrato nell’editor;
- comandi nel terminale;
- interfacce grafiche;
- slide;
- menu e impostazioni;
- messaggi di errore.

Strategie possibili:

## 14.1 Frame a intervalli regolari

Esempio: un frame ogni 8 secondi.

```bash
ffmpeg -i workshop_01.mp4 -vf fps=1/8 frames/frame_%05d.jpg
```

Vantaggio: semplice.

Svantaggio: può generare molti frame inutili.

## 14.2 Scene detection

Usare PySceneDetect per estrarre frame quando cambia la scena.

Vantaggio: riduce frame duplicati.

Svantaggio: potrebbe perdere piccoli cambiamenti nel codice.

## 14.3 Estrazione guidata dal testo

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

# 15. Fase 6 — OCR delle schermate

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

L’OCR può sbagliare caratteri critici, per esempio:

- `l` e `1`;
- `O` e `0`;
- virgolette;
- backtick;
- parentesi;
- underscore;
- trattini;
- indentazione.

Per questo il codice estratto da OCR deve essere sempre classificato con un livello di affidabilità.

---

# 16. Fase 7 — Riconoscimento ed estrazione del codice

Dopo l’OCR, il sistema deve identificare quali parti del testo sono codice.

Il codice può apparire in:

- terminale;
- editor;
- notebook;
- slide;
- browser;
- file di configurazione;
- console di debug.

## 16.1 Classificazione del contenuto

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

## 16.2 Riconoscimento del linguaggio

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

## 16.3 Deduplicazione del codice

Nei video lo stesso comando può restare a schermo per molti secondi. Il sistema deve evitare di salvare dieci volte lo stesso blocco.

Strategie:

- normalizzazione whitespace;
- hashing del testo;
- similarità testuale;
- confronto tra frame vicini.

## 16.4 Validazione del codice

Quando possibile, il codice deve essere validato.

Esempi:

- JSON può essere verificato con un parser JSON;
- YAML può essere verificato con un parser YAML;
- Python può essere verificato con `ast.parse`;
- comandi shell possono essere solo classificati, non necessariamente eseguiti.

---

# 17. Fase 8 — Chunking intelligente

Il chunking è una delle parti più importanti del progetto.

Un chunk non deve essere troppo piccolo, perché perderebbe contesto. Non deve essere troppo grande, perché renderebbe il retrieval poco preciso.

Un buon chunk per video tecnici può coprire da 2 a 8 minuti, a seconda della densità del contenuto.

## 17.1 Criteri per creare chunk

Il sistema deve considerare:

- pause nel parlato;
- cambio argomento;
- cambio schermata;
- presenza di codice;
- inizio/fine di una procedura;
- parole chiave;
- titoli di slide;
- azioni nel software.

## 17.2 Struttura del chunk

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

## 17.3 Chunk separati per codice

È utile indicizzare anche i blocchi di codice come documenti separati, collegati al chunk principale.

Questo permette query come:

```text
Quale comando viene usato per avviare il progetto?
```

oppure:

```text
Mostrami tutti i file di configurazione modificati nel corso.
```

---

# 18. Fase 9 — Creazione degli embedding

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

# 19. Fase 10 — Indicizzazione nel vector database

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

# 20. Fase 11 — Retrieval e RAG

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

# 21. Fase 12 — Generazione dell’indice della documentazione

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

Questo è importante perché l’utente potrebbe voler riorganizzare la documentazione prima della generazione finale.

---

# 22. Fase 13 — Generazione delle sezioni Markdown

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

# 23. Fase 14 — Revisione, validazione e controllo qualità

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

## 23.1 Controllo anti-allucinazione

Il sistema deve confrontare ogni sezione generata con le fonti usate.

Se trova frasi non supportate, deve marcarle.

Esempio:

```markdown
> Revisione richiesta: questa affermazione non è stata trovata chiaramente nelle fonti.
```

## 23.2 Controllo codice

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

# 24. Fase 15 — Export della documentazione

Il formato principale è Markdown.

Formati esportabili:

- cartella Markdown semplice;
- MkDocs;
- Docusaurus;
- GitHub Pages;
- PDF;
- HTML statico.

## 24.1 Export MkDocs

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

# 25. CLI del progetto

La CLI è il modo più semplice per usare il sistema.

Comandi consigliati:

```bash
videodoc init <project_name>
videodoc ingest <project_name>
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

## 25.1 Comando status

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

## 25.2 Comando inspect

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

---

# 26. Configurazione del progetto

Esempio completo di `config.yaml`:

```yaml
project:
  name: "Corso Software X"
  slug: "corso-software-x"
  language: "it"
  timezone: "Europe/Rome"

paths:
  videos: "videos"
  materials: "materials"
  workdir: "workdir"
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
  extract_from_materials: true
  strict_mode: true
  mark_uncertain_code: true

documentation:
  format: "markdown"
  include_video_name: true
  include_timestamps: true
  include_code_explanation: true
  include_expected_result: true
  include_common_errors: true
  include_sources_section: true
```

---

# 27. Schema database SQLite

SQLite serve per salvare metadati strutturati.

## 27.1 Tabella projects

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

## 27.2 Tabella videos

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

## 27.3 Tabella transcript_segments

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

## 27.4 Tabella frames

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

## 27.5 Tabella code_blocks

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

## 27.6 Tabella chunks

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

## 27.7 Tabella doc_sections

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

# 28. Schema Qdrant

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
project_materials
```

Oppure una sola collection con `source_type` differenziato.

---

# 29. Prompt principali

## 29.1 Prompt per generare outline

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

## 29.2 Prompt per generare una sezione

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

## 29.3 Prompt per spiegare codice

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

## 29.4 Prompt per revisione

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

# 30. Gestione del codice estratto dai video

Il codice è la parte più delicata del progetto.

Il sistema deve distinguere tra codice:

```text
1. preso da file sorgente allegati;
2. letto chiaramente tramite OCR;
3. ricostruito da OCR e trascrizione;
4. ipotizzato dal modello.
```

Il quarto caso deve essere evitato o marcato esplicitamente come non verificato.

## 30.1 Strict mode

In strict mode il sistema include solo codice:

- proveniente da file sorgenti;
- letto da OCR con confidenza alta;
- validato da parser o regole semplici.

## 30.2 Assistive mode

In assistive mode il sistema può ricostruire codice incompleto, ma deve marcarlo.

Esempio:

```markdown
> Nota: il seguente blocco è stato ricostruito combinando OCR e trascrizione. Verificare prima dell’uso.
```

## 30.3 Verifica umana

Il sistema dovrebbe produrre un report dei blocchi di codice da controllare:

```text
code_review_report.md
```

Con contenuto simile:

```markdown
# Blocchi di codice da verificare

## workshop_01.mp4 — 00:21:04

Confidenza OCR: 0.61

```bash
npm create vite@latest my-app
```

Motivo revisione: OCR sotto soglia minima.
```

---

# 31. Gestione dei materiali allegati

I video non dovrebbero essere l’unica fonte.

Il sistema deve poter importare:

- repository Git;
- file `.zip`;
- notebook;
- slide;
- PDF;
- documenti Markdown;
- file sorgenti;
- configurazioni;
- dataset di esempio.

I materiali allegati sono spesso più affidabili del codice letto da video.

Se un comando o un file appare sia nel video sia nel repository, il repository deve avere priorità per il codice esatto, mentre il video fornisce il contesto procedurale.

---

# 32. Modalità operative

## 32.1 Modalità documentazione

Genera documentazione completa.

```bash
videodoc generate corso-software-x
```

## 32.2 Modalità domanda-risposta

Permette di interrogare i video.

```bash
videodoc ask corso-software-x "Come si configura il database?"
```

Risposta attesa:

```markdown
La configurazione del database viene mostrata nel video `workshop_03_database.mp4`, tra `00:12:10` e `00:18:45`.

La procedura consiste in...
```

## 32.3 Modalità rigenerazione parziale

Rigenera solo una sezione.

```bash
videodoc regenerate corso-software-x --section "Configurazione database"
```

## 32.4 Modalità ispezione

Mostra fonti grezze collegate a un timestamp.

```bash
videodoc inspect corso-software-x --video workshop_03.mp4 --timestamp 00:14:20
```

---

# 33. Interfaccia web opzionale

Una UI web può essere aggiunta dopo l’MVP.

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

Stack possibile:

```text
Backend: FastAPI
Frontend: React / Next.js
Database: SQLite + Qdrant
Worker: Celery / RQ / Dramatiq
```

Per una versione semplice si può usare Streamlit.

---

# 34. Roadmap di sviluppo

## 34.1 MVP 1 — Pipeline base

Obiettivo: trasformare un video in Markdown usando trascrizione audio.

Funzioni:

- CLI base;
- ingestion video;
- estrazione audio;
- trascrizione;
- chunking temporale;
- generazione Markdown semplice.

## 34.2 MVP 2 — OCR e codice

Obiettivo: recuperare codice e informazioni visive.

Funzioni:

- estrazione frame;
- OCR;
- deduplicazione frame;
- riconoscimento blocchi codice;
- codice incluso nella documentazione.

## 34.3 MVP 3 — RAG completo

Obiettivo: interrogare i contenuti.

Funzioni:

- embedding locali;
- Qdrant;
- retrieval;
- chat RAG;
- generazione sezioni tramite retrieval.

## 34.4 MVP 4 — Multi-video e documentazione completa

Obiettivo: generare una documentazione completa da più workshop.

Funzioni:

- outline globale;
- generazione sezione per sezione;
- riferimenti multi-video;
- export MkDocs.

## 34.5 MVP 5 — Revisione e UI

Obiettivo: rendere il sistema usabile da utenti non tecnici.

Funzioni:

- dashboard;
- editor Markdown;
- revisione codice;
- approvazione sezioni;
- rigenerazione parziale.

---

# 35. Best practice

## 35.1 Salvare sempre i dati intermedi

Non bisogna cancellare trascrizioni, OCR, frame o chunk dopo la generazione.

Questi dati permettono di:

- rigenerare documentazione;
- correggere errori;
- cambiare modello;
- migliorare prompt;
- fare audit delle fonti.

## 35.2 Non fidarsi ciecamente dell’OCR

L’OCR può sbagliare caratteri importanti. Il codice va sempre marcato con una confidenza.

## 35.3 Usare materiali originali quando disponibili

Repository, slide e file sorgenti sono spesso più precisi del video.

## 35.4 Generare una sezione alla volta

Questo riduce errori e migliora qualità.

## 35.5 Mantenere timestamp ovunque

I timestamp rendono la documentazione verificabile.

## 35.6 Separare generazione e revisione

La pipeline deve generare, poi revisionare. Non bisogna considerare la prima generazione come definitiva.

---

# 36. Limiti del sistema

Il sistema può essere molto utile, ma ha limiti importanti.

## 36.1 Codice non sempre leggibile

Se il video è compresso, sfocato o il font è piccolo, l’OCR può fallire.

## 36.2 Audio ambiguo

La trascrizione può contenere errori, soprattutto con termini tecnici, nomi di librerie o accenti.

## 36.3 Azioni grafiche difficili da descrivere

Alcune azioni svolte nell’interfaccia possono non essere comprese correttamente senza un modello multimodale.

## 36.4 Rischio allucinazioni

Il LLM può inventare dettagli se il prompt non è rigido o se le fonti sono incomplete.

## 36.5 Necessità di revisione umana

Per documentazione professionale, soprattutto con codice, è necessaria una fase di revisione.

---

# 37. Esempio di output Markdown generato

```markdown
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
```

---

# 38. Conclusione

Il progetto VideoDocRAG permette di trasformare video tecnici lunghi e difficili da consultare in documentazione Markdown strutturata, navigabile, interrogabile e versionabile.

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

Il sistema deve essere pensato come uno strumento riusabile, non come una soluzione specifica per un solo corso.

La forma più efficace è una pipeline modulare:

```text
Video → Audio → Trascrizione → Frame → OCR → Codice → Chunk → Embedding → RAG → Markdown → Revisione → Export
```

Con questa architettura è possibile creare una base solida per generare documentazione tecnica da workshop, corsi, tutorial, demo software e registrazioni interne, mantenendo sempre il collegamento tra ogni informazione generata e la fonte video originale.
