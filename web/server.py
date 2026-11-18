"""Local website for the flight data warehouse: python web/server.py [--port 8000] [--open]

Python standard library only. Listens on 127.0.0.1 (this computer only). Shows the 28 MDX analyses from the
committed files (no cube needed); the "Run live" button re-runs one stored statement on the cube.
Routes: GET / | /static/<file> | /api/overview | /api/project | /api/profile | /api/requirements | /api/analyses
        | /api/analyses/<stem> | /api/screenshot/<stem> | /api/figure/star-schema | /api/figure/ssis | /report.pdf
        POST /api/live/<stem>
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

if __package__ in (None, ""):                      # python web/server.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web import data, live  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
FIGURE = data.REPO / "docs" / "figures" / "star-schema.png"
SSIS_FIGURE = data.REPO / "docs" / "figures" / "ssis-control-flow.png"
REQUIREMENTS = Path(__file__).resolve().parent / "requirements.json"
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
         ".jpg": "image/jpeg", ".pdf": "application/pdf"}


def make_server(host: str = "127.0.0.1", port: int = 8000, live=live.run_live) -> ThreadingHTTPServer:
    live_fn = live

    class Handler(BaseHTTPRequestHandler):
        server_version = "FlightDW"

        def log_message(self, fmt, *args):            # quiet: one short line per request on stderr
            sys.stderr.write("%s %s\n" % (self.command, self.path))

        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status: int = 200) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _not_found(self) -> None:
            self._json({"error": "not found"}, 404)

        def _file(self, path: Path) -> None:
            try:
                resolved = path.resolve()
                if not resolved.is_file():
                    return self._not_found()
                body = resolved.read_bytes()
            except OSError:
                return self._not_found()
            self._send(200, body, TYPES.get(resolved.suffix.lower(), "application/octet-stream"))

        def _host_ok(self) -> bool:
            """Only answer requests addressed to this computer (guards against DNS rebinding from a web page)."""
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
            if host in ("127.0.0.1", "localhost", "::1"):
                return True
            self._json({"error": "forbidden host"}, 403)
            return False

        def do_GET(self):
            if not self._host_ok():
                return
            path = unquote(urlsplit(self.path).path)
            if path == "/":
                return self._file(STATIC / "index.html")
            if path.startswith("/static/"):
                rel = path[len("/static/"):]
                target = (STATIC / rel).resolve()
                if not rel or ".." in rel.replace("\\", "/").split("/") or not target.is_relative_to(STATIC.resolve()):
                    return self._not_found()
                return self._file(target)
            if path == "/api/overview":
                return self._json(data.overview() | {"match": data.match_summary()})
            if path == "/api/analyses":
                return self._json({"analyses": data.list_statements(), "match": data.match_summary()})
            if path.startswith("/api/analyses/"):
                stem = path[len("/api/analyses/"):]
                return self._json(data.load_statement(stem) | {"match": data.match_summary()}) if data.is_stem(stem) else self._not_found()
            if path == "/api/project":
                return self._json(data.project())
            if path == "/api/profile":
                return self._json(data.profile())
            if path == "/api/requirements":
                return self._json(json.loads(REQUIREMENTS.read_text(encoding="utf-8")))
            if path.startswith("/api/screenshot/"):
                shot = data.screenshot_path(path[len("/api/screenshot/"):])
                return self._file(shot) if shot else self._not_found()
            if path == "/api/figure/star-schema":
                return self._file(FIGURE)
            if path == "/api/figure/ssis":
                return self._file(SSIS_FIGURE)
            if path == "/report.pdf":
                return self._file(data.REPORT_PDF)
            if path.startswith("/api/live/") and data.is_stem(path[len("/api/live/"):]):
                return self._json({"error": "use POST"}, 405)
            self._not_found()

        def do_POST(self):
            if not self._host_ok():
                return
            path = unquote(urlsplit(self.path).path)
            if path.startswith("/api/live/"):
                stem = path[len("/api/live/"):]
                if not data.is_stem(stem):
                    return self._not_found()
                return self._json(live_fn(stem))
            self._not_found()

    return ThreadingHTTPServer((host, port), Handler)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--open", action="store_true", help="open the page in the default browser")
    args = ap.parse_args(argv)
    httpd = make_server(port=args.port)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"Flight data warehouse website: {url}   (Ctrl+C to stop)")
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
