"""CLI entry point for pip-installed usage (mac-cleanup command)."""

from __future__ import annotations

import argparse
import os


def main():
    parser = argparse.ArgumentParser(
        description="mac-cleanup — macOS development environment cleanup tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  mac-cleanup --scan              # Scan only (report)\n"
            "  mac-cleanup --scan --json        # JSON output for scripting\n"
            "  mac-cleanup --dry-run            # Preview, no deletions\n"
            "  mac-cleanup --only node,cache    # Specific categories\n"
            "  mac-cleanup --skip tm,docker     # Skip categories\n"
            "  mac-cleanup --app               # Launch desktop app\n"
            "  mac-cleanup --init-config        # Create default config"
        ),
    )
    parser.add_argument("path", nargs="?", default=os.getcwd(), help="Scan root directory (default: cwd)")
    parser.add_argument("--scan", action="store_true", help="Scan only — show report without cleaning")
    parser.add_argument("--json", action="store_true", help="Output scan results as JSON")
    parser.add_argument("--node", action="store_true", help="Only clean node_modules")
    parser.add_argument("--dry-run", action="store_true", help="Preview mode — no deletions")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-confirm all prompts")
    parser.add_argument("--only", type=str, default="", help="Only run these categories (comma-separated)")
    parser.add_argument("--skip", type=str, default="", help="Skip these categories (comma-separated)")
    parser.add_argument("--app", action="store_true", help="Launch desktop app (web UI)")
    parser.add_argument("--port", type=int, default=None, help="Port for desktop app")
    parser.add_argument("--init-config", action="store_true", help="Create default config file")

    args = parser.parse_args()

    if args.init_config:
        from .config import init_config
        path = init_config()
        print(f"Config created at: {path}")
        return

    if args.app:
        from .app import start_app
        start_app(project_root=args.path, port=args.port)
        return

    from .core import Cleaner

    categories = set(args.only.split(",")) if args.only else None
    skip = set(args.skip.split(",")) if args.skip else None

    cleaner = Cleaner(project_root=args.path, dry_run=args.dry_run, auto_yes=args.yes)
    cleaner.run_interactive(
        scan_only=args.scan,
        node_only=args.node,
        categories=categories,
        skip=skip,
        json_output=args.json,
    )
