# VoidSweep

A native macOS GUI for reviewing and reclaiming disk space, built on top of the
`mac-cleanup` registry. Designed around the **`_DELETE_` convention**: agents
that are forbidden from issuing `rm` directly rename targets to
`_DELETE_<name>` and leave the actual deletion to a human review pass — this
tool is that review pass.

## What it does

Two tabs in one window:

### 🪦 _DELETE_ Sweep
- Recursively scans selected roots for entries whose name starts with `_DELETE_`.
- Skips descent into matched `_DELETE_` directories (records as one unit, faster).
- Skips noise dirs (`node_modules`, `.git`, `target`, `Photos Library`, …).
- Live progress every ~1500 entries so you can see it's actually working.
- Quick-add preset roots: Documents / Downloads / Desktop / Library / Projects /
  $HOME, plus user-defined presets via `VOIDSWEEP_PRESETS`.

### 🧹 Cache Cleanup
Ports the original `mac-cleanup` Python registry to Rust — scans well-known
dev caches in $HOME:

- npm · yarn · pnpm · Bun · CocoaPods · Composer · Gem · Go build · Pip · uv ·
  Cargo registry · Turborepo · Homebrew
- Xcode DerivedData / Archives / iOS DeviceSupport / Simulator caches
- Gradle / Maven / Android caches
- `~/Library/Caches` / `~/Library/Logs` (with size threshold)

### Common
- Per-row checkbox · sort by Size / Age / Path · filter by substring.
- Hover a row's name to see the full absolute path + note.
- Two delete modes:
  - **Trash** (default, reversible — uses macOS Trash via the `trash` crate)
  - **Permanent** (irreversible — `fs::remove_dir_all` / `remove_file`)
- "Reveal in Finder" per row to inspect anything suspicious first.
- Collapsible scan log at the bottom for diagnostics.

## Safety

- Refuses to delete `/`, `$HOME`, and the standard system directories.
- Skips well-known noise dirs (`node_modules`, `.git`, `target`, …) when
  walking — speeds up scans and avoids descending into deps that happen to
  contain `_DELETE_` artefacts.
- Confirmation modal before every destructive action.
- Default delete mode is Trash, not permanent.

## Build / run

```bash
cd voidsweep
cargo run --release
```

Release build produces a single static binary at
`voidsweep/target/release/voidsweep`.

### Personal preset roots

Define a colon-separated `Label=path` list to expose your own quick-add buttons:

```bash
export VOIDSWEEP_PRESETS="Workspace=~/Documents/work:Notes=~/Documents/notes"
```

`~` is expanded to `$HOME`. Non-existent paths are silently dropped.

## Stack

- `eframe` / `egui` 0.29 — pure-Rust native GUI
- `walkdir` — directory traversal
- `trash` — Trash integration
- `rfd` — native folder picker

## License

MIT — same as the parent `mac-cleanup` repo.
