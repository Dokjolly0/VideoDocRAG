# Changelog

## Step 1 — Project management foundation
- Added project initialization and a validated `config.yaml` schema — see [features/project-initialization.md](features/project-initialization.md)
- Added the local project registry and portable project paths (`--path`, `list`/`link`/`unlink`/`path`) — see [features/project-registry.md](features/project-registry.md)
- Fixed: `init` now registers projects under their canonical slug instead of the raw display name, matching `link`'s existing behavior — see [features/slugify.md](features/slugify.md)
- Fixed: `init` on a path that already holds a *different* project now fails with a clear error instead of silently registering an unintended alias — see [features/slugify.md](features/slugify.md)
- Hardened: a single malformed entry in the local registry can no longer crash `list`/`resolve`, and can always be removed via `unlink` — see [features/project-registry.md](features/project-registry.md)
