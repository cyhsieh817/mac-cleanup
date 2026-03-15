"""Core engine — scanning and cleaning logic."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .audit import AuditLog
from .config import load_config
from .registry import (
    CATEGORIES,
    DEV_ARTIFACTS,
    LOG_TARGETS,
    PACKAGE_CACHES,
    PROJECT_ARTIFACTS,
    PROTECTED_PATHS,
    ScanItem,
    ScanReport,
)


# ── Terminal colors ─────────────────────────────────────


class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    WARN = "\033[93m"
    FAIL = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    END = "\033[0m"


# ── Cleaner ─────────────────────────────────────────────


class Cleaner:
    def __init__(
        self,
        project_root: str | None = None,
        dry_run: bool = False,
        auto_yes: bool = False,
    ):
        self.project_root = Path(project_root).resolve() if project_root else Path.cwd()
        self.dry_run = dry_run
        self.auto_yes = auto_yes
        self.config: dict[str, Any] = load_config()
        self.audit = AuditLog(dry_run=dry_run)
        self.stats = {"cleaned": 0, "freed_kb": 0}
        self.min_size_kb = self.config.get("thresholds", {}).get("min_size_mb", 1) * 1024

        # Progress callback for web UI: fn(current, total, message)
        self.on_progress: Any = None

    # ── Helpers ──────────────────────────────────────────

    def log(self, msg: str, level: str = "info"):
        icons = {
            "info": f"{Colors.BLUE}i",
            "success": f"{Colors.GREEN}v",
            "warning": f"{Colors.WARN}!",
            "error": f"{Colors.FAIL}x",
            "step": f"{Colors.HEADER}#",
            "dry": f"{Colors.CYAN}~",
        }
        prefix = icons.get(level, f"{Colors.BLUE}i")
        print(f"{prefix} {msg}{Colors.END}")

    @staticmethod
    def _run(cmd: str, *, capture: bool = False) -> str | bool:
        try:
            r = subprocess.run(
                cmd, shell=True,
                stdout=subprocess.PIPE if capture else None,
                stderr=subprocess.PIPE if capture else None,
                text=True,
            )
            return r.stdout.strip() if capture else (r.returncode == 0)
        except Exception:
            return "" if capture else False

    def get_size_kb(self, path: Path | str) -> int:
        p = Path(path)
        if not p.exists():
            return 0
        try:
            res = self._run(f"du -sk '{p}'", capture=True)
            return int(res.split()[0]) if res else 0
        except (ValueError, IndexError):
            return 0

    @staticmethod
    def fmt(size_kb: int) -> str:
        v = float(size_kb)
        for u in ("KB", "MB", "GB"):
            if v < 1024.0:
                return f"{v:.1f} {u}"
            v /= 1024.0
        return f"{v:.1f} TB"

    def ask(self, question: str) -> bool:
        if self.dry_run or self.auto_yes:
            return True
        while True:
            ans = input(f"{Colors.BOLD}{Colors.WARN}{question} [y/N]: {Colors.END}").lower().strip()
            if ans in ("y", "yes"):
                return True
            if ans in ("n", "no", ""):
                return False

    def safe_delete(self, path: str) -> bool:
        resolved = str(Path(path).resolve())
        if resolved in PROTECTED_PATHS or resolved == str(Path.home()):
            self.log(f"Refused to delete protected path: {resolved}", "error")
            return False
        if self.dry_run:
            self.log(f"Would delete: {resolved}", "dry")
            return True
        return bool(self._run(f"rm -rf '{resolved}'"))

    # ── Scanning ─────────────────────────────────────────

    def scan_all(self, categories: set[str] | None = None) -> ScanReport:
        cats = categories or set(CATEGORIES.keys())
        skip = set(self.config.get("skip", {}).get("categories", []))
        cats -= skip

        report = ScanReport(
            scan_root=str(self.project_root),
            timestamp=datetime.now().astimezone().isoformat(),
        )

        scanners = {
            "node": self._scan_node_modules,
            "cache": self._scan_package_caches,
            "dev": self._scan_dev_artifacts,
            "project": self._scan_project_artifacts,
            "docker": self._scan_docker,
            "tm": self._scan_time_machine,
            "logs": self._scan_logs,
            "trash": self._scan_trash,
        }

        for cat in cats:
            fn = scanners.get(cat)
            if fn:
                report.items.extend(fn())

        # Custom paths from config
        for target in self.config.get("custom_paths", {}).get("targets", []):
            name = target.get("name", "Custom")
            path = target.get("path", "")
            if path:
                p = Path(path).expanduser()
                if p.exists():
                    size = self.get_size_kb(p)
                    if size >= self.min_size_kb:
                        report.items.append(ScanItem("custom", name, str(p), size))

        return report

    def _scan_node_modules(self) -> list[ScanItem]:
        cmd = f"find '{self.project_root}' -name node_modules -type d -prune 2>/dev/null"
        out = self._run(cmd, capture=True)
        if not out:
            return []
        items = []
        for line in str(out).split("\n"):
            if not line:
                continue
            p = Path(line)
            size = self.get_size_kb(p)
            if size >= self.min_size_kb:
                try:
                    rel = str(p.relative_to(self.project_root))
                except ValueError:
                    rel = str(p)
                items.append(ScanItem("node", f"node_modules ({rel})", str(p), size))
        return items

    def _scan_package_caches(self) -> list[ScanItem]:
        items = []
        for name, path in PACKAGE_CACHES:
            p = Path(path).expanduser()
            if p.exists():
                size = self.get_size_kb(p)
                if size >= self.min_size_kb:
                    items.append(ScanItem("cache", f"{name} Cache", str(p), size))
        return items

    def _scan_dev_artifacts(self) -> list[ScanItem]:
        items = []
        for path, desc in DEV_ARTIFACTS:
            p = Path(path).expanduser()
            if p.exists():
                size = self.get_size_kb(p)
                if size >= self.min_size_kb:
                    items.append(ScanItem("dev", Path(path).name, str(p), size, desc))
        return items

    def _scan_project_artifacts(self) -> list[ScanItem]:
        items = []
        for dirname, desc, coexist_files in PROJECT_ARTIFACTS:
            if dirname == "node_modules":
                continue  # handled by _scan_node_modules
            cmd = f"find '{self.project_root}' -name '{dirname}' -type d -prune 2>/dev/null"
            out = self._run(cmd, capture=True)
            if not out:
                continue
            for line in str(out).split("\n"):
                if not line:
                    continue
                p = Path(line)
                # Smart check: if coexist_files specified, verify parent has one
                if coexist_files:
                    parent = p.parent
                    if not any((parent / f).exists() for f in coexist_files):
                        continue
                size = self.get_size_kb(p)
                if size >= self.min_size_kb:
                    try:
                        rel = str(p.relative_to(self.project_root))
                    except ValueError:
                        rel = str(p)
                    items.append(ScanItem("project", f"{dirname} ({rel})", str(p), size, desc))
        return items

    def _scan_docker(self) -> list[ScanItem]:
        items = []
        if shutil.which("docker"):
            usage = self._run("docker system df --format '{{.Size}}' 2>/dev/null", capture=True)
            if usage:
                items.append(ScanItem("docker", "Docker System", "", 0, "Use docker system prune"))
        if shutil.which("brew"):
            cache_dir = Path("~/Library/Caches/Homebrew").expanduser()
            if cache_dir.exists():
                size = self.get_size_kb(cache_dir)
                if size >= self.min_size_kb:
                    items.append(ScanItem("docker", "Homebrew Cache", str(cache_dir), size))
        return items

    def _scan_time_machine(self) -> list[ScanItem]:
        if not shutil.which("tmutil"):
            return []
        out = self._run("tmutil listlocalsnapshots / 2>/dev/null", capture=True)
        if out and "com.apple.TimeMachine" in str(out):
            count = str(out).count("com.apple.TimeMachine")
            return [ScanItem("tm", f"TM Snapshots ({count})", "/", 0, "Requires sudo")]
        return []

    def _scan_logs(self) -> list[ScanItem]:
        items = []
        for path, desc, threshold in LOG_TARGETS:
            p = Path(path).expanduser()
            if p.exists():
                size = self.get_size_kb(p)
                if size >= threshold:
                    items.append(ScanItem("logs", desc, str(p), size))
        return items

    def _scan_trash(self) -> list[ScanItem]:
        trash = Path.home() / ".Trash"
        size = self.get_size_kb(trash)
        if size > 0:
            return [ScanItem("trash", "Trash", str(trash), size)]
        return []

    # ── Cleaning ─────────────────────────────────────────

    def clean_items(self, items: list[ScanItem]) -> dict:
        """Clean a list of scan items. Returns stats."""
        total = len(items)
        for i, item in enumerate(items, 1):
            if self.on_progress:
                self.on_progress(i, total, f"Cleaning {item.name}...")

            if item.category == "docker":
                self._clean_docker_item(item)
            elif item.category == "tm":
                self._clean_tm_item(item)
            elif item.category == "logs":
                self._clean_logs_item(item)
            elif item.category == "trash":
                self._clean_trash()
            else:
                if self.safe_delete(item.path):
                    self.stats["cleaned"] += 1
                    self.stats["freed_kb"] += item.size_kb
                    self.audit.record("DELETED", item.size_kb, item.path)
                else:
                    self.audit.record("FAILED", item.size_kb, item.path)

        log_path = self.audit.save()
        return {**self.stats, "log_path": str(log_path) if log_path else None}

    def _clean_docker_item(self, item: ScanItem):
        if "Docker" in item.name:
            if self._run("docker system prune -f"):
                self.audit.record("DELETED", 0, "docker system prune")
        elif "Homebrew" in item.name:
            self._run("brew cleanup")
            self._run("brew autoremove")
            self.stats["cleaned"] += 1
            self.stats["freed_kb"] += item.size_kb
            self.audit.record("DELETED", item.size_kb, item.path)

    def _clean_tm_item(self, item: ScanItem):
        cmd = (
            "tmutil listlocalsnapshots / "
            "| grep 'com.apple.TimeMachine' "
            "| awk -F'.' '{print $4}' "
            "| xargs -I {} sudo tmutil deletelocalsnapshots {}"
        )
        if self.dry_run:
            self.log(f"Would run: {cmd}", "dry")
        else:
            self._run(cmd)
        self.audit.record("DELETED", 0, "Time Machine snapshots")

    def _clean_logs_item(self, item: ScanItem):
        p = Path(item.path)
        try:
            for child in p.iterdir():
                if child.name.startswith("."):
                    continue
                self.safe_delete(str(child))
            self.stats["cleaned"] += 1
            self.stats["freed_kb"] += item.size_kb
            self.audit.record("DELETED", item.size_kb, item.path)
        except PermissionError:
            self.audit.record("FAILED", item.size_kb, item.path, "permission denied")

    def _clean_trash(self):
        size = self.get_size_kb(Path.home() / ".Trash")
        if self.dry_run:
            self.log("Would empty trash", "dry")
        else:
            self._run('osascript -e \'tell application "Finder" to empty trash\'')
        self.stats["freed_kb"] += size
        self.audit.record("DELETED", size, "~/.Trash")

    # ── Interactive CLI flow ─────────────────────────────

    def run_interactive(
        self,
        *,
        scan_only: bool = False,
        node_only: bool = False,
        categories: set[str] | None = None,
        skip: set[str] | None = None,
        json_output: bool = False,
    ):
        try:
            cats = categories or set(CATEGORIES.keys())
            if skip:
                cats -= skip
            if node_only:
                cats = {"node"}

            # Header
            if not json_output:
                print(f"\n{Colors.BOLD}{Colors.HEADER}mac-cleanup{Colors.END}")
                if self.dry_run:
                    print(f"{Colors.CYAN}[DRY RUN] Preview mode{Colors.END}")
                print(f"Scan root: {self.project_root}")
                print("-" * 50)

            # Scan
            if not json_output:
                self.log("Scanning...", "step")
            report = self.scan_all(cats)

            if json_output:
                import json
                print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
                return

            if not report.items:
                self.log("Nothing to clean!", "success")
                return

            # Display scan results
            if scan_only:
                self._print_scan_report(report)
                return

            # Interactive clean
            to_clean: list[ScanItem] = []
            for cat, items in report.by_category().items():
                cat_name = CATEGORIES.get(cat, cat)
                cat_total = sum(i.size_kb for i in items)
                self.log(f"{cat_name} ({self.fmt(cat_total)})", "step")
                for item in items:
                    size_str = self.fmt(item.size_kb) if item.size_kb else "N/A"
                    desc = f" — {item.description}" if item.description else ""
                    self.log(f"  {item.name} ({size_str}){desc}", "info")
                if self.ask(f"Clean {cat_name}?"):
                    to_clean.extend(items)
                else:
                    for item in items:
                        self.audit.record("SKIPPED", item.size_kb, item.path, "user declined")

            if to_clean:
                result = self.clean_items(to_clean)
                print("-" * 50)
                self.log("Done!", "success")
                self.log(f"Items cleaned: {result['cleaned']}", "info")
                self.log(f"Space freed: {self.fmt(result['freed_kb'])}", "success")
                if result.get("log_path"):
                    self.log(f"Audit log: {result['log_path']}", "info")
            else:
                self.log("Nothing selected.", "info")

        except KeyboardInterrupt:
            print()
            self.log("Cancelled.", "error")
            sys.exit(130)

    def _print_scan_report(self, report: ScanReport):
        print(f"\n{Colors.BOLD}{'Category':<22} {'Items':>6} {'Size':>10}{Colors.END}")
        print("-" * 42)
        for cat, items in report.by_category().items():
            cat_name = CATEGORIES.get(cat, cat)
            cat_total = sum(i.size_kb for i in items)
            count = len(items)
            print(f"  {cat_name:<20} {count:>6} {self.fmt(cat_total):>10}")
        print("-" * 42)
        print(f"  {Colors.BOLD}{'Total reclaimable':<20} {'':>6} {self.fmt(report.total_kb):>10}{Colors.END}")
        print()
