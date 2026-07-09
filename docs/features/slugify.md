# Canonical project identifiers (`slugify`)

## Summary
VideoDocRAG needs exactly one canonical, machine-safe identifier per project — used as the local registry key, the default `project.slug` in `config.yaml`, and the default folder name under the projects home. `slugify()` (`src/videodoc/core/utils/slug.py`) is the single place that turns a human-readable project name into that identifier, and it is now used consistently everywhere a project is created or registered.

## The rule
**The registry key is always the slug, never the raw display name the user typed.**

`videodoc init "Corso Software X"` and `videodoc link <same folder>` (without `--name`) must always resolve to the *same* registry key — otherwise the same project would be reachable under two different identifiers depending on how it was created, which defeats the point of having a registry at all.

Concretely:
- `ProjectService.init(name, ...)` computes `slug = slugify(name)` and registers under `slug`, not under the raw `name`. The human-readable `name` is preserved as `config.project.name`; only the *slug* becomes the registry key, `config.project.slug`, and (when `--path` is omitted) the folder name.
- `ProjectService.link(path, name=None, ...)` already defaulted to `config.project.slug` when no explicit `--name` is given — `init` was the one place that disagreed with this before it was fixed.
- `ProjectInitResult.name` (and therefore the CLI's "Project '<name>' initialized/registered..." messages) always reports the slug, so the user immediately sees the identifier to use in later commands.

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
- `tests/cli/test_cli_project_commands.py::test_init_registers_by_slug_not_raw_display_name`
- `tests/cli/test_cli_project_commands.py::test_init_on_path_with_different_existing_project_fails`
