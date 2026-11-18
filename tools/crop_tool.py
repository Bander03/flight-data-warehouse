"""Manual screenshot-cropping helper: python tools/crop_tool.py [--port 8010] [--open]

Local-only tool (not part of the report build or the website) so a person can crop the
28 MDX screenshots in report/figures by hand: drag two boxes (the query-pane code, the
results grid) on each image, trimming the unused Object Explorer panel and the blank
space above/below the real content, then save. Each box is pre-filled with an automatic
guess (tools/_screenshot_suggest.py) that can be dragged/resized before saving.

Saving crops and vertically stacks the two boxes, overwriting the file in report/figures.
Figures are tracked in git, so "git checkout -- report/figures/<name>" (or the Restore
button here, which reads the file back from HEAD) undoes a bad crop.

Routes: GET / | /figures/<name> | /api/list
        POST /api/crop | /api/restore
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _screenshot_suggest as suggest  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
FIGURES = REPO / "report" / "figures"
NAMES = sorted(p.name for p in FIGURES.glob("M*.jpg"))

ORIGINAL_DIMS: dict[str, tuple[int, int]] = {}
for _n in NAMES:
    with Image.open(FIGURES / _n) as _im:
        ORIGINAL_DIMS[_n] = _im.size


def _height_cm(w: int, h: int, max_h: float = 11.0, max_w: float = 15.5) -> float:
    width = min(max_w, max_h * w / h)
    return width * h / w


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Crop screenshots</title>
<style>
  body { font-family: Segoe UI, Arial, sans-serif; margin: 0; background: #f4f4f6; color: #222; }
  header { padding: 10px 16px; background: #1f2d3d; color: #fff; display: flex; align-items: center; gap: 16px; }
  header h1 { font-size: 16px; margin: 0; font-weight: 600; }
  #nav button { margin-right: 4px; }
  main { padding: 16px; display: flex; gap: 16px; align-items: flex-start; }
  #stage { position: relative; display: inline-block; background: #fff; border: 1px solid #ccc; }
  #stage img { display: block; max-width: 1100px; }
  .box { position: absolute; border: 2px solid; box-sizing: border-box; cursor: move; background: rgba(0,0,0,0.03); }
  .box.query { border-color: #2a6fdb; }
  .box.results { border-color: #2aa85a; }
  .handle { position: absolute; width: 12px; height: 12px; background: #fff; border: 2px solid #333; border-radius: 50%; }
  .handle.nw { left: -7px; top: -7px; cursor: nwse-resize; }
  .handle.ne { right: -7px; top: -7px; cursor: nesw-resize; }
  .handle.sw { left: -7px; bottom: -7px; cursor: nesw-resize; }
  .handle.se { right: -7px; bottom: -7px; cursor: nwse-resize; }
  #side { width: 300px; font-size: 14px; }
  #side h2 { font-size: 14px; }
  .legend span { display: inline-block; width: 12px; height: 12px; margin-right: 6px; vertical-align: -1px; }
  #progress { white-space: pre-line; background: #fff; border: 1px solid #ddd; padding: 10px; border-radius: 6px; }
  button { padding: 6px 10px; border-radius: 5px; border: 1px solid #99a; background: #fff; cursor: pointer; }
  button.primary { background: #2a6fdb; color: #fff; border-color: #2a6fdb; }
  button.danger { background: #c0392b; color: #fff; border-color: #c0392b; }
  #list { max-height: 260px; overflow: auto; border: 1px solid #ddd; border-radius: 6px; background: #fff; }
  #list div { padding: 4px 8px; cursor: pointer; font-size: 13px; }
  #list div.current { background: #2a6fdb; color: #fff; }
  #list div.done::after { content: " \\2713"; color: #2aa85a; }
</style></head>
<body>
<header>
  <h1>Crop MDX screenshots</h1>
  <div id="nav">
    <button id="prev">&larr; Prev</button>
    <button id="next">Next &rarr;</button>
  </div>
  <div id="counter"></div>
</header>
<main>
  <div>
    <div id="stage"><img id="img"><div id="boxQuery" class="box query"></div><div id="boxResults" class="box results"></div></div>
    <p class="legend"><span style="background:#2a6fdb"></span>query/code box
       &nbsp; <span style="background:#2aa85a"></span>results-grid box</p>
    <button id="reset">Reset to suggestion</button>
    <button id="restore" class="danger">Restore original (undo crop)</button>
    <button id="save" class="primary">Save crop</button>
  </div>
  <div id="side">
    <h2>Progress</h2>
    <div id="progress">loading...</div>
    <h2>All 28</h2>
    <div id="list"></div>
  </div>
</main>
<script>
let state = { names: [], idx: 0, data: {} };

async function loadList() {
  const r = await fetch('/api/list');
  state.data = await r.json();
  state.names = Object.keys(state.data).sort();
  renderList();
  showImage(0);
}

function cmFor(w, h) {
  const width = Math.min(15.5, 11.0 * w / h);
  return width * h / w;
}

function renderList() {
  const el = document.getElementById('list');
  el.innerHTML = '';
  state.names.forEach((n, i) => {
    const d = document.createElement('div');
    d.textContent = n;
    d.className = (i === state.idx ? 'current ' : '') + (state.data[n].cropped ? 'done' : '');
    d.onclick = () => showImage(i);
    el.appendChild(d);
  });
}

function renderProgress() {
  let totalOrig = 0, totalNow = 0, done = 0;
  for (const n of state.names) {
    const d = state.data[n];
    totalOrig += cmFor(d.original.width, d.original.height);
    totalNow += cmFor(d.width, d.height);
    if (d.cropped) done++;
  }
  document.getElementById('progress').textContent =
    `${done} of ${state.names.length} cropped\\n` +
    `Estimated total screenshot height:\\n` +
    `  before: ${totalOrig.toFixed(1)} cm\\n` +
    `  now:    ${totalNow.toFixed(1)} cm\\n` +
    `  saved:  ${(totalOrig - totalNow).toFixed(1)} cm (~${((totalOrig - totalNow) / 25).toFixed(1)} A4 pages)`;
}

let box = { query: null, results: null };
let scale = 1;

function showImage(i) {
  state.idx = i;
  const name = state.names[i];
  const d = state.data[name];
  document.getElementById('counter').textContent = `${i + 1} / ${state.names.length}  —  ${name}`;
  const img = document.getElementById('img');
  img.onload = () => {
    scale = img.clientWidth / d.width;
    box.query = { ...d.suggestion.query };
    box.results = { ...d.suggestion.results };
    if (d.saved_boxes) { box.query = { ...d.saved_boxes.query }; box.results = { ...d.saved_boxes.results }; }
    drawBoxes();
  };
  img.src = `/figures/${name}?t=${Date.now()}`;
  renderList();
}

function drawBoxes() {
  for (const kind of ['query', 'results']) {
    const el = document.getElementById(kind === 'query' ? 'boxQuery' : 'boxResults');
    const b = box[kind];
    el.style.left = (b.left * scale) + 'px';
    el.style.top = (b.top * scale) + 'px';
    el.style.width = ((b.right - b.left) * scale) + 'px';
    el.style.height = ((b.bottom - b.top) * scale) + 'px';
  }
}

function attachInteraction(elId, kind) {
  const el = document.getElementById(elId);
  ['nw', 'ne', 'sw', 'se'].forEach(corner => {
    const h = document.createElement('div');
    h.className = 'handle ' + corner;
    el.appendChild(h);
    h.addEventListener('pointerdown', (e) => startDrag(e, kind, corner));
  });
  el.addEventListener('pointerdown', (e) => {
    if (e.target.classList.contains('handle')) return;
    startDrag(e, kind, 'move');
  });
}

function startDrag(e, kind, mode) {
  e.preventDefault();
  e.stopPropagation();
  const startX = e.clientX, startY = e.clientY;
  const orig = { ...box[kind] };
  const onMove = (ev) => {
    const dx = (ev.clientX - startX) / scale, dy = (ev.clientY - startY) / scale;
    const b = { ...orig };
    if (mode === 'move') { b.left += dx; b.right += dx; b.top += dy; b.bottom += dy; }
    if (mode === 'nw') { b.left += dx; b.top += dy; }
    if (mode === 'ne') { b.right += dx; b.top += dy; }
    if (mode === 'sw') { b.left += dx; b.bottom += dy; }
    if (mode === 'se') { b.right += dx; b.bottom += dy; }
    box[kind] = b;
    drawBoxes();
  };
  const onUp = () => {
    window.removeEventListener('pointermove', onMove);
    window.removeEventListener('pointerup', onUp);
  };
  window.addEventListener('pointermove', onMove);
  window.addEventListener('pointerup', onUp);
}

attachInteraction('boxQuery', 'query');
attachInteraction('boxResults', 'results');

document.getElementById('prev').onclick = () => showImage((state.idx - 1 + state.names.length) % state.names.length);
document.getElementById('next').onclick = () => showImage((state.idx + 1) % state.names.length);
document.getElementById('reset').onclick = () => {
  const name = state.names[state.idx];
  box.query = { ...state.data[name].suggestion.query };
  box.results = { ...state.data[name].suggestion.results };
  drawBoxes();
};
document.getElementById('restore').onclick = async () => {
  const name = state.names[state.idx];
  if (!confirm('Restore ' + name + ' to its original, uncropped version?')) return;
  await fetch('/api/restore', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
  await loadList();
};
document.getElementById('save').onclick = async () => {
  const name = state.names[state.idx];
  const body = { name, query: round(box.query), results: round(box.results) };
  const r = await fetch('/api/crop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!r.ok) { alert('Save failed: ' + await r.text()); return; }
  await loadList();
  showImage(Math.min(state.idx + 1, state.names.length - 1));
};

function round(b) { return { left: Math.round(b.left), top: Math.round(b.top), right: Math.round(b.right), bottom: Math.round(b.bottom) }; }

loadList().then(renderProgress);
setInterval(renderProgress, 1000);
</script>
</body></html>
"""


def make_server(host: str = "127.0.0.1", port: int = 8010) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "CropTool"

        def log_message(self, fmt, *args):
            sys.stderr.write("%s %s\n" % (self.command, self.path))

        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status: int = 200) -> None:
            self._send(status, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

        def _host_ok(self) -> bool:
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
                return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            if path == "/api/list":
                out = {}
                for name in NAMES:
                    fp = FIGURES / name
                    with Image.open(fp) as im:
                        w, h = im.size
                    ow, oh = ORIGINAL_DIMS[name]
                    out[name] = {
                        "width": w, "height": h,
                        "original": {"width": ow, "height": oh},
                        "cropped": (w, h) != (ow, oh),
                        "suggestion": suggest.suggest(fp),
                    }
                return self._json(out)
            if path.startswith("/figures/"):
                name = path[len("/figures/"):]
                fp = (FIGURES / name).resolve()
                if name not in NAMES or not fp.is_file():
                    return self._json({"error": "not found"}, 404)
                return self._send(200, fp.read_bytes(), "image/jpeg")
            self._json({"error": "not found"}, 404)

        def do_POST(self):
            if not self._host_ok():
                return
            path = unquote(urlsplit(self.path).path)
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._json({"error": "bad json"}, 400)

            name = body.get("name")
            if name not in NAMES:
                return self._json({"error": "unknown image"}, 404)
            fp = FIGURES / name

            if path == "/api/crop":
                q, r = body.get("query"), body.get("results")
                if not q or not r:
                    return self._json({"error": "missing query/results box"}, 400)
                try:
                    im = Image.open(fp).convert("RGB")
                    qband = im.crop((q["left"], q["top"], q["right"], q["bottom"]))
                    rband = im.crop((r["left"], r["top"], r["right"], r["bottom"]))
                except Exception as exc:
                    return self._json({"error": str(exc)}, 400)
                out_w = max(qband.width, rband.width)
                out_h = qband.height + rband.height
                out = Image.new("RGB", (out_w, out_h), (255, 255, 255))
                out.paste(qband, (0, 0))
                out.paste(rband, (0, qband.height))
                out.save(fp, quality=92)
                return self._json({"width": out.width, "height": out.height})

            if path == "/api/restore":
                rel = fp.relative_to(REPO).as_posix()
                try:
                    data = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=REPO,
                                           capture_output=True, check=True).stdout
                except subprocess.CalledProcessError as exc:
                    return self._json({"error": exc.stderr.decode(errors="replace")}, 500)
                fp.write_bytes(data)
                return self._json({"ok": True})

            self._json({"error": "not found"}, 404)

    return ThreadingHTTPServer((host, port), Handler)


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8010)
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args(argv)
    httpd = make_server(port=args.port)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"Screenshot crop tool: {url}   (Ctrl+C to stop)")
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
