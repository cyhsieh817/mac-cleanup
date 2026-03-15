# mac-cleanup

A fast, zero-dependency macOS cleanup tool for developers. Scans and removes development artifacts, package caches, build outputs, and system junk — via CLI or a desktop web UI.

## Features

- **Scan mode** — see what's eating your disk before cleaning anything
- **Category selection** — `--only node,cache` or `--skip tm,docker`
- **Desktop app** — local web UI for visual cleanup (`--app`)
- **Smart project scanning** — finds `node_modules`, `.next`, `target`, `__pycache__`, `.venv`, etc. with project-file validation
- **Config file** — custom targets, skip rules, thresholds
- **Audit log** — every deletion recorded to `~/.local/share/mac-cleanup/logs/`
- **Dry run** — preview everything before deleting
- **JSON output** — pipe scan results into scripts or CI

## Cleanup Targets

| Category | Targets |
|----------|---------|
| `node` | `node_modules` (recursive) |
| `cache` | npm, yarn, pnpm, Bun, CocoaPods, Composer, Gem, Go, Pip, uv, Cargo, Turborepo |
| `dev` | Xcode DerivedData/Archives, iOS Simulator, Gradle, Maven, Android |
| `project` | `.next`, `.nuxt`, `dist`, `build`, `target`, `__pycache__`, `.venv`, `.terraform`, ... |
| `docker` | Docker prune, Homebrew cleanup |
| `tm` | Time Machine local snapshots |
| `logs` | `~/Library/Caches`, `~/Library/Logs` |
| `trash` | Trash |

## Quick Start

```bash
# No installation needed
python3 cleanup.py --scan          # See what can be cleaned
python3 cleanup.py                 # Interactive cleanup
python3 cleanup.py --app           # Launch desktop app

# Or install as a command
pip install .
mac-cleanup --scan
mac-cleanup --app
```

## Usage

```bash
# Scan only (report)
python3 cleanup.py --scan

# JSON output (for scripting/CI)
python3 cleanup.py --scan --json

# Preview mode — no deletions
python3 cleanup.py --dry-run

# Only specific categories
python3 cleanup.py --only node,cache,project

# Skip categories
python3 cleanup.py --skip tm,docker

# Auto-confirm (use with care)
python3 cleanup.py -y

# Scan a specific directory
python3 cleanup.py ~/Projects --only node,project

# Desktop app (web UI)
python3 cleanup.py --app
python3 cleanup.py --app --port 8080

# Create default config
python3 cleanup.py --init-config
```

## Desktop App

Run `python3 cleanup.py --app` to launch a local web UI:

1. Select categories to scan
2. Click **Scan** to discover reclaimable space
3. Check/uncheck individual items
4. Click **Clean Selected** to free space
5. View audit log for what was removed

The app runs locally on `127.0.0.1` — no data leaves your machine.

## Configuration

Create a config file at `~/.config/mac-cleanup/config.toml`:

```bash
python3 cleanup.py --init-config
```

```toml
[thresholds]
min_size_mb = 1          # Skip targets smaller than this

[skip]
categories = ["tm"]      # Always skip these categories

# Custom cleanup targets
[[custom_paths.targets]]
name = "Turborepo Cache"
path = "~/.turbo"

[[custom_paths.targets]]
name = "Bun Cache"
path = "~/.bun/install/cache"
```

## Safety

- Protected path whitelist (`/`, `/usr`, `/bin`, `$HOME`, etc.)
- Interactive confirmation for every action by default
- `--dry-run` for safe previewing
- Audit log for every session
- Project artifact detection requires matching project files (e.g., `Cargo.toml` for `target/`)
- Targets under 1 MB automatically skipped

## Requirements

- macOS
- Python 3.10+
- Zero third-party dependencies

## License

MIT
