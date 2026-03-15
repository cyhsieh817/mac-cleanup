"""Desktop app — local web server + browser UI."""

from __future__ import annotations

import json
import socket
import threading
import webbrowser
from functools import partial
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from .core import Cleaner
from .registry import CATEGORIES, ScanItem, ScanReport

WEB_DIR = Path(__file__).parent / "web"


class AppState:
    """Shared state between web server and cleaner thread."""

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.report: ScanReport | None = None
        self.status: str = "idle"  # idle | scanning | cleaning | done
        self.progress: int = 0
        self.total: int = 0
        self.message: str = ""
        self.result: dict[str, Any] = {}
        self.lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    """HTTP request handler with JSON API."""

    state: AppState  # injected via partial

    def log_message(self, format: str, *args: Any) -> None:
        pass  # suppress default access logs

    def _json(self, data: Any, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, filepath: Path):
        if not filepath.exists():
            self.send_error(404)
            return
        body = filepath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._html(WEB_DIR / "index.html")
        elif self.path == "/api/status":
            with self.state.lock:
                self._json({
                    "status": self.state.status,
                    "progress": self.state.progress,
                    "total": self.state.total,
                    "message": self.state.message,
                    "result": self.state.result,
                })
        elif self.path == "/api/categories":
            self._json(CATEGORIES)
        elif self.path == "/api/report":
            with self.state.lock:
                if self.state.report:
                    self._json(self.state.report.to_dict())
                else:
                    self._json(None)
        else:
            self.send_error(404)

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_len)) if content_len else {}

        if self.path == "/api/scan":
            self._handle_scan(body)
        elif self.path == "/api/clean":
            self._handle_clean(body)
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _handle_scan(self, body: dict):
        with self.state.lock:
            if self.state.status not in ("idle", "done"):
                self._json({"error": "busy"}, 409)
                return
            self.state.status = "scanning"
            self.state.message = "Scanning..."

        def do_scan():
            cats = set(body.get("categories", CATEGORIES.keys()))
            cleaner = Cleaner(project_root=self.state.project_root)
            report = cleaner.scan_all(cats)
            with self.state.lock:
                self.state.report = report
                self.state.status = "idle"
                self.state.message = ""

        threading.Thread(target=do_scan, daemon=True).start()
        self._json({"started": True})

    def _handle_clean(self, body: dict):
        paths_to_clean: list[str] = body.get("paths", [])
        dry_run: bool = body.get("dry_run", False)

        with self.state.lock:
            if self.state.status not in ("idle", "done"):
                self._json({"error": "busy"}, 409)
                return
            if not self.state.report:
                self._json({"error": "no scan"}, 400)
                return

            # Match paths to scan items
            items = [i for i in self.state.report.items if i.path in paths_to_clean]
            if not items:
                self._json({"error": "no items"}, 400)
                return

            self.state.status = "cleaning"
            self.state.progress = 0
            self.state.total = len(items)
            self.state.message = "Starting..."

        def do_clean():
            cleaner = Cleaner(
                project_root=self.state.project_root,
                dry_run=dry_run,
            )

            def on_progress(current: int, total: int, msg: str):
                with self.state.lock:
                    self.state.progress = current
                    self.state.total = total
                    self.state.message = msg

            cleaner.on_progress = on_progress
            result = cleaner.clean_items(items)

            with self.state.lock:
                self.state.status = "done"
                self.state.result = result
                self.state.message = "Done!"
                self.state.report = None  # invalidate

        threading.Thread(target=do_clean, daemon=True).start()
        self._json({"started": True, "count": len(items)})


def _find_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def start_app(project_root: str = ".", port: int | None = None):
    """Launch the desktop app (web server + browser)."""
    port = port or _find_port()
    state = AppState(project_root)

    # Inject state into handler
    handler_class = type("BoundHandler", (Handler,), {"state": state})

    server = HTTPServer(("127.0.0.1", port), handler_class)
    url = f"http://127.0.0.1:{port}"

    print(f"mac-cleanup app running at {url}")
    print("Press Ctrl+C to stop.\n")

    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
