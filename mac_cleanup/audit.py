"""Audit log — records what was cleaned for later review."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

LOG_DIR = Path.home() / ".local" / "share" / "mac-cleanup" / "logs"


class AuditLog:
    """Collects cleanup actions and writes them to a log file."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.entries: list[str] = []
        self.timestamp = datetime.now().astimezone()

    def record(self, action: str, size_kb: int, path: str, reason: str = ""):
        """Record a single action (DELETED, SKIPPED, FAILED)."""
        size_str = _format_size(size_kb)
        line = f"{action:<8} {size_str:>10}  {path}"
        if reason:
            line += f"  ({reason})"
        self.entries.append(line)

    def save(self) -> Path | None:
        """Write log to disk. Returns the log file path, or None if nothing to log."""
        if not self.entries:
            return None

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        filename = self.timestamp.strftime("%Y-%m-%d_%H%M%S") + ".log"
        filepath = LOG_DIR / filename

        header = (
            f"# mac-cleanup audit log\n"
            f"# {self.timestamp.isoformat()}\n"
            f"# dry_run: {self.dry_run}\n"
            f"#\n"
        )
        body = "\n".join(self.entries)

        # Summary
        deleted = sum(1 for e in self.entries if e.startswith("DELETED"))
        skipped = sum(1 for e in self.entries if e.startswith("SKIPPED"))
        failed = sum(1 for e in self.entries if e.startswith("FAILED"))
        summary = f"\n---\nDeleted: {deleted} | Skipped: {skipped} | Failed: {failed}\n"

        filepath.write_text(header + body + summary, encoding="utf-8")
        return filepath


def _format_size(size_kb: int) -> str:
    value = float(size_kb)
    for unit in ("KB", "MB", "GB"):
        if value < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"
