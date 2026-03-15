"""Cleanup target definitions — paths, categories, project artifact patterns."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Sequence


# ── Data structures ─────────────────────────────────────


@dataclass
class ScanItem:
    """A single scannable/cleanable target."""

    category: str  # "node", "cache", "dev", ...
    name: str  # "npm Cache"
    path: str  # "/Users/x/.npm"
    size_kb: int = 0
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScanReport:
    """Aggregated scan results."""

    items: list[ScanItem] = field(default_factory=list)
    scan_root: str = ""
    timestamp: str = ""

    @property
    def total_kb(self) -> int:
        return sum(i.size_kb for i in self.items)

    def by_category(self) -> dict[str, list[ScanItem]]:
        groups: dict[str, list[ScanItem]] = {}
        for item in self.items:
            groups.setdefault(item.category, []).append(item)
        return groups

    def to_dict(self) -> dict:
        return {
            "scan_root": self.scan_root,
            "timestamp": self.timestamp,
            "total_kb": self.total_kb,
            "items": [i.to_dict() for i in self.items],
        }


# ── Category registry ───────────────────────────────────

CATEGORIES: dict[str, str] = {
    "node": "node_modules",
    "cache": "Package Caches",
    "dev": "Dev Tool Artifacts",
    "project": "Project Build Outputs",
    "docker": "Docker & Homebrew",
    "tm": "Time Machine Snapshots",
    "logs": "Logs & Temp",
    "trash": "Trash",
}


# ── Package manager caches ──────────────────────────────

PACKAGE_CACHES: list[tuple[str, str]] = [
    ("npm", "~/.npm"),
    ("yarn", "~/.yarn/cache"),
    ("pnpm", "~/.pnpm-store"),
    ("Bun", "~/.bun/install/cache"),
    ("CocoaPods", "~/Library/Caches/CocoaPods"),
    ("Composer", "~/.composer/cache"),
    ("Gem", "~/.gem"),
    ("Go Build", "~/Library/Caches/go-build"),
    ("Pip", "~/Library/Caches/pip"),
    ("uv", "~/Library/Caches/uv"),
    ("Cargo", "~/.cargo/registry"),
    ("Turborepo", "~/Library/Caches/turbo"),
]


# ── Dev tool artifacts ──────────────────────────────────

DEV_ARTIFACTS: list[tuple[str, str]] = [
    ("~/Library/Developer/Xcode/DerivedData", "Xcode build cache"),
    ("~/Library/Developer/Xcode/Archives", "Xcode archives"),
    ("~/Library/Developer/Xcode/iOS DeviceSupport", "Old iOS device symbols"),
    ("~/Library/Developer/CoreSimulator/Caches", "iOS Simulator caches"),
    ("~/.gradle/caches", "Gradle caches"),
    ("~/.m2/repository", "Maven repository"),
    ("~/.android/cache", "Android build cache"),
]


# ── Project build artifacts (recursive scan) ────────────
# (dirname, description, must_coexist_with_file)
# The third element ensures we only match genuine project output,
# not user directories that happen to share the name.

PROJECT_ARTIFACTS: list[tuple[str, str, Sequence[str]]] = [
    ("node_modules", "Node.js deps", ["package.json"]),
    (".next", "Next.js build", ["package.json"]),
    (".nuxt", "Nuxt.js build", ["package.json"]),
    (".turbo", "Turborepo cache", ["package.json", "turbo.json"]),
    (".output", "Nitro/Nuxt output", ["package.json"]),
    ("dist", "Build output", ["package.json", "tsconfig.json"]),
    ("build", "Build output", ["package.json", "build.gradle"]),
    ("target", "Rust/Java build", ["Cargo.toml", "pom.xml", "build.gradle"]),
    ("__pycache__", "Python bytecode", []),
    (".pytest_cache", "Pytest cache", []),
    (".mypy_cache", "Mypy cache", []),
    (".ruff_cache", "Ruff cache", []),
    (".venv", "Python venv", []),
    ("vendor", "Go/PHP vendor", ["go.mod", "composer.json"]),
    (".terraform", "Terraform state", ["main.tf"]),
]


# ── Logs / temp targets ────────────────────────────────

LOG_TARGETS: list[tuple[str, str, int]] = [
    # (path, description, threshold_kb)
    ("~/Library/Caches", "App caches", 100 * 1024),
    ("~/Library/Logs", "User logs", 50 * 1024),
]


# ── Protected paths (never delete) ─────────────────────

PROTECTED_PATHS = frozenset([
    "/", "/bin", "/usr", "/etc", "/sbin", "/var",
    "/System", "/Library", "/Applications",
    "/private", "/private/var", "/cores",
])
