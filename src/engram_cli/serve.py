"""Local HTTP server for browsing engram analysis output.

Serves the viewer HTML template with data loaded from a local
engram-output directory or engram-analysis.json file.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any

VIEWER_TEMPLATE = Path(__file__).parent / "templates" / "viewer.html"


def _load_analysis_data(data_dir: Path) -> dict[str, Any]:
    """Load and normalize analysis data from an engram output directory.

    Supports both:
    - Direct engram-analysis.json files
    - engram-output/ directories with subdirectories
    """
    # Case 1: data_dir is a directory containing engram-analysis.json
    json_file = data_dir / "engram-analysis.json"
    if json_file.exists():
        with open(json_file) as f:
            data = json.load(f)
        return {
            "skills": data.get("skills", []),
            "memories": data.get("memories", []),
            "analysis": data.get("analysis", {}),
            "generated_at": data.get("generated_at", ""),
            "model_used": data.get("model_used", ""),
        }

    # Case 2: data_dir contains subdirectories (each an analyzed repo)
    all_skills = []
    all_memories = []
    for sub in sorted(data_dir.iterdir()):
        sub_json = sub / "engram-analysis.json"
        if sub.is_dir() and sub_json.exists():
            with open(sub_json) as f:
                data = json.load(f)
            all_skills.extend(data.get("skills", []))
            all_memories.extend(data.get("memories", []))

    if all_skills or all_memories:
        return {
            "skills": all_skills,
            "memories": all_memories,
            "generated_at": "",
        }

    raise FileNotFoundError(
        f"No engram-analysis.json found in {data_dir}. "
        "Run 'engram analyze <repo>' first to generate data."
    )


class EngramHandler(SimpleHTTPRequestHandler):
    """HTTP handler that serves the viewer and API data."""

    def __init__(self, *args, data: dict, viewer_html: str, **kwargs):
        self._data = data
        self._viewer_html = viewer_html
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_viewer()
        elif self.path == "/api/data":
            self._serve_data()
        else:
            self.send_error(404)

    def _serve_viewer(self):
        content = self._viewer_html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_data(self):
        content = json.dumps(self._data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        """Suppress default access logs."""
        pass


def start_server(
    data_dir: Path,
    port: int = 8420,
    open_browser: bool = False,
) -> None:
    """Start the local viewer server.

    Args:
        data_dir: Path to engram output directory
        port: Port to serve on
        open_browser: Whether to auto-open in browser
    """
    data = _load_analysis_data(data_dir)
    viewer_html = VIEWER_TEMPLATE.read_text()

    handler = partial(EngramHandler, data=data, viewer_html=viewer_html)
    HTTPServer.allow_reuse_address = True
    server = HTTPServer(("127.0.0.1", port), handler)

    url = f"http://localhost:{port}"

    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
