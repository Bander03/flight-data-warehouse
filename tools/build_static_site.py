"""Builds a static copy of the local website (for GitHub Pages): every API answer saved as a JSON file.

    python tools/build_static_site.py [--out site] [--pdf path/to/report.pdf]

The copy needs no server: index.html carries data-site="static", and web/static/app.js then reads api/*.json,
screenshots/*.jpg, figures/*.png and report.pdf next to it, by relative paths. "Run live on the cube" is not offered.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from web import data, server  # noqa: E402

STATIC = ROOT / "web" / "static"


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def build(out: Path, pdf: Path | None = None) -> Path:
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    (out / "static").mkdir(parents=True)
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    html = html.replace('<html lang="en">', '<html lang="en" data-site="static">', 1).replace('"/static/', '"static/')
    # GitHub Pages lets browsers keep files for 10 minutes: a version in the link makes a changed file load anew
    for name in ("app.js", "style.css"):
        version = hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:10]
        html = html.replace(f'"static/{name}"', f'"static/{name}?v={version}"')
    (out / "index.html").write_text(html, encoding="utf-8")
    for f in STATIC.iterdir():
        if f.name != "index.html":
            shutil.copy2(f, out / "static" / f.name)
    (out / ".nojekyll").write_text("", encoding="utf-8")          # serve files as they are

    match = data.match_summary()
    pdf = Path(pdf) if pdf else (data.REPORT_PDF if data.REPORT_PDF.exists() else None)
    project = data.project()
    if pdf:
        shutil.copy2(pdf, out / "report.pdf")
        project["report"] = {"available": True, "pages": data._pdf_pages(pdf)}
    else:
        project["report"] = {"available": False, "pages": None}
    _write_json(out / "api" / "overview.json", data.overview() | {"match": match})
    _write_json(out / "api" / "project.json", project)
    _write_json(out / "api" / "profile.json", data.profile())
    _write_json(out / "api" / "requirements.json", json.loads(server.REQUIREMENTS.read_text(encoding="utf-8")))
    _write_json(out / "api" / "analyses.json", {"analyses": data.list_statements(), "match": match})
    (out / "screenshots").mkdir()
    for stem in data.list_stems():
        _write_json(out / "api" / "analyses" / f"{stem}.json", data.load_statement(stem) | {"match": match})
        shot = data.screenshot_path(stem)
        if shot:
            shutil.copy2(shot, out / "screenshots" / f"{stem}.jpg")
    (out / "figures").mkdir()
    shutil.copy2(server.FIGURE, out / "figures" / "star-schema.png")
    shutil.copy2(server.SSIS_FIGURE, out / "figures" / "ssis.png")
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "site"))
    ap.add_argument("--pdf", help="report PDF to publish (default: report/build/ when it exists)")
    args = ap.parse_args(argv)
    out = build(Path(args.out), Path(args.pdf) if args.pdf else None)
    files = sum(1 for p in out.rglob("*") if p.is_file())
    print(f"wrote {out} ({files} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
