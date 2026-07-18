# Codebase sync

Implementazione README §9.6, §15 e §35.

## Comando

`videodoc sync-codebase <project>` carica il progetto e chiama `CodebaseSyncService`.

## Artefatti

Il servizio scrive due file sotto `indexes/`:

- `codebase_manifest.json`: manifest verificabile con file, hash SHA-256, snippet estratti, link sorgente e warning di scan;
- `codebase_index.json`: indice vettoriale locale `local-json`/`cosine`, con embedding feature-hashing degli snippet.

Il comando è idempotente: se hash dei file, impostazioni di scan/embedding e indice esistente non cambiano, stampa `Skipped: yes` e non riscrive gli artefatti.

## Snippet

I file sono raccolti con `filesystem.scan_codebase()`, quindi rispettano:

- esclusioni default e override `scan.add_excludes`/`scan.remove_excludes`;
- `scan.allowed_code_extensions`;
- `scan.max_file_size_mb`;
- `scan.follow_symlinks`.

Per i file Python parseabili, gli snippet corrispondono a funzioni/classi top-level. Per gli altri file, o Python non parseabile, il servizio crea blocchi logici di righe. Ogni snippet conserva:

- percorso relativo alla root codebase;
- linguaggio derivato dall'estensione;
- righe `start_line`/`end_line`;
- `symbol_name`, quando disponibile;
- contenuto;
- hash del file;
- link citabile nel formato `codebase/<path>#L<start>-L<end>`.

## Retrieval

`ChatAnswerService` include `indexes/codebase_index.json` nelle modalità `raw` e `hybrid`, insieme al normale `indexes/vector_index.json` se presente. Le fonti codebase usano `source_type="codebase"` e `doc_path` impostato al link citabile, così l'output di `ask`/`chat` può mostrare riferimenti come `codebase/src/app.py#L1-L12`.

## Verifica

Copertura aggiunta:

- `tests/core/test_codebase_sync_service.py`;
- `tests/cli/test_cli_sync_codebase_command.py`;
- test di integrazione chat raw su indice codebase sincronizzato.
