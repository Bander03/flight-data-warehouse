"""Static pages of the local website: offline-safe (no external URL), every file served, no unsafe DOM writes."""
import re
import sys
import threading
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from web import server  # noqa: E402

STATIC = REPO / "web" / "static"


def test_index_links_its_assets():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "/static/style.css" in html and "/static/app.js" in html and "<title>" in html


def test_no_external_url_anywhere():
    for f in STATIC.iterdir():
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"""(src|href)=["']https?://|url\(\s*["']?https?://|@import\s+["']?https?://|fetch\(\s*["']https?://""", text), f.name


def test_no_innerhtml_or_eval():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "innerHTML" not in js and "eval(" not in js and "document.write" not in js


def test_every_static_file_is_served():
    httpd = server.make_server(port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        for f in STATIC.iterdir():
            with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_address[1]}/static/{f.name}", timeout=10) as r:
                assert r.status == 200, f.name
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_page_has_phone_viewport_and_dark_mode():
    assert "width=device-width" in (STATIC / "index.html").read_text(encoding="utf-8")
    assert "prefers-color-scheme: dark" in (STATIC / "style.css").read_text(encoding="utf-8")


def test_a_slow_page_cannot_replace_a_newer_one():
    """Data that arrives after the reader moved on is dropped (seen on GitHub Pages: the list rewrote the address)."""
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "routeNo += 1" in js and "if (asked !== routeNo) throw new StalePage()" in js
    assert "if (e instanceof StalePage) return;" in js
