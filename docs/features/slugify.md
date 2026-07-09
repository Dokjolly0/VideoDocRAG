# Canonical project identifiers (`slugify`)

## Summary
VideoDocRAG needs exactly one canonical, machine-safe identifier per project — used as the local registry key, the default `project.slug` in `config.yaml`, and the default folder name under the projects home. `slugify()` (`src/videodoc/core/utils/slug.py`) is the single place that turns a human-readable project name into that identifier, and it is now used consistently everywhere a project is created or registered.

## Two related but distinct concepts

It's important to keep these apart, because one is a hard invariant and the other is a deliberate, documented exception to it:

- **Canonical slug** (`config.project.slug`): the project's own identity, fixed once at `videodoc init` time from `slugify(name)`. Never guessed or overridden elsewhere — it lives inside the project's own `config.yaml` and travels with it regardless of registry state.
- **Registry key**: the local, per-machine label a given `ProjectRegistry` uses to point at a project's path. It **defaults** to the canonical slug, and does so unconditionally for `init` (no override exists there — see below). `videodoc link` is the one place where it can be told to differ, via an explicit `--name` alias (see next section).

## The rule
**By default, the registry key is always the slug, never the raw display name the user typed — with one documented exception (`link --name`), never a silent one.**

`videodoc init "Corso Software X"` and `videodoc link <same folder>` (without `--name`) must always resolve to the *same* registry key — otherwise the same project would be reachable under two different identifiers depending on how it was created, which defeats the point of having a registry at all.

Concretely:
- `ProjectService.init(name, ...)` computes `slug = slugify(name)` and registers under `slug`, not under the raw `name`. The human-readable `name` is preserved as `config.project.name`; only the *slug* becomes the registry key, `config.project.slug`, and (when `--path` is omitted) the folder name. `init` has **no** `--name`/alias override: at creation time there is no pre-existing identity to alias around, so the slug it derives *is* the project's identity by construction.
- `ProjectService.link(path, name=None, ...)` defaults to `config.project.slug` when no explicit `--name` is given — this is what `init` was made consistent with.
- `ProjectInitResult.name` (and therefore the CLI's "Project '<name>' initialized/registered..." messages) always reports the actual registry key used, so the user immediately sees the identifier to use in later commands. `ProjectInitResult.canonical_slug` always reports the project's own slug, so callers can detect when the two diverge (see below).

## Explicit aliases (`videodoc link --name <alias>`)

Once more than a couple of projects exist, two unrelated projects can legitimately slugify to the same string (e.g. "Test!" and "Test?" both become `test`), or a user may just want a shorter local nickname than a project's real slug. `videodoc link --name <alias>` exists for exactly this: it registers the project under a **deliberately different, explicit** local identifier.

This is not a loophole in the canonical-slug rule, it's a scoped, clearly-signposted exception to it:
- the alias is still run through `slugify()` — every registry key stays slug-shaped and quoting-free in later commands, whether it's the default or an override;
- it is never written to the project's own `config.yaml` — `config.project.slug` is untouched, so the project's canonical identity never depends on which machine/registry it happens to be linked into;
- when the alias differs from the project's own slug, the CLI says so explicitly: `Linked as alias 'alias-locale' -> <path> (the project's own slug is 'corso-software-x')`, instead of a plain `Linked '<name>' -> <path>` when they match.

```bash
videodoc link "D:\Corsi\corso-software-x" --name "Alias Locale!!"
# Linked as alias 'alias-locale' -> D:\Corsi\corso-software-x (the project's own slug is 'corso-software-x')
```

## Algorithm

See the docstring on `slugify()` for the exact transliteration rules (Unicode NFKD normalization, ASCII-fold, lowercase, non-alphanumeric runs collapsed to a single hyphen). In short:

```text
"Corso Software X"        -> "corso-software-x"
"Città è già pronta!!"    -> "citta-e-gia-pronta"
"!!!"                     -> raises ValueError (no usable characters)
```

## Related fix: refusing to alias someone else's project

A related risk: running `videodoc init <name> --path <dir>` where `<dir>` already contains a *different* project's valid `config.yaml` used to succeed silently — it kept the existing config untouched but registered `<dir>` under the newly-requested slug too, creating an unintended second alias for the same folder. `ProjectService.init` now compares the requested slug against `config.project.slug` already on disk at that path and raises `RegistryConflictError` if they differ, pointing the user at `videodoc link <dir>` instead (see `docs/features/project-initialization.md`).

## Tests
- `tests/core/test_project_service.py::test_slugify_basic`, `test_slugify_accents_and_symbols`, `test_slugify_empty_result_raises`
- `tests/core/test_project_service.py::test_init_creates_expected_structure` (asserts the registry key is the slug, not the display name)
- `tests/core/test_project_service.py::test_init_registers_by_slug_not_display_name` (init and link agree on the same key)
- `tests/core/test_project_service.py::test_init_on_path_with_different_existing_project_raises`
- `tests/core/test_project_service.py::test_link_with_explicit_alias_is_slugified_and_flagged`
- `tests/core/test_project_service.py::test_link_with_invalid_alias_raises_domain_error`
- `tests/cli/test_cli_project_commands.py::test_init_registers_by_slug_not_raw_display_name`
- `tests/cli/test_cli_project_commands.py::test_init_on_path_with_different_existing_project_fails`
- `tests/cli/test_cli_project_commands.py::test_link_with_explicit_alias_is_flagged_in_output`
- `tests/cli/test_cli_project_commands.py::test_link_with_invalid_alias_fails`
