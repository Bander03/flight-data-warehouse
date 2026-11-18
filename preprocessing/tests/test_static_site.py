"""Static copy of the website for GitHub Pages (tools/build_static_site.py)."""
import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("build_static_site", REPO / "tools" / "build_static_site.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = tmp_path_factory.mktemp("s") / "site"
    pdf = tmp_path_factory.mktemp("p") / "r.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    return mod.build(out, pdf)


def test_index_is_marked_static_and_uses_relative_paths(site):
    html = (site / "index.html").read_text(encoding="utf-8")
    assert 'data-site="static"' in html
    assert re.search(r'"static/style\.css\?v=[0-9a-f]{10}"', html) and re.search(r'"static/app\.js\?v=[0-9a-f]{10}"', html)
    assert '"/static/' not in html


def test_every_api_answer_is_a_file(site):
    for name in ("overview", "project", "profile", "requirements", "analyses"):
        json.loads((site / "api" / f"{name}.json").read_text(encoding="utf-8"))
    stems = [a["stem"] for a in json.loads((site / "api" / "analyses.json").read_text(encoding="utf-8"))["analyses"]]
    assert len(stems) == 28
    for stem in stems:
        s = json.loads((site / "api" / "analyses" / f"{stem}.json").read_text(encoding="utf-8"))
        assert s["rows"] and s["mdx"]
        assert (site / "screenshots" / f"{stem}.jpg").stat().st_size > 1000


def test_figures_pdf_and_nojekyll(site):
    assert (site / "figures" / "star-schema.png").exists() and (site / "figures" / "ssis.png").exists()
    assert (site / "report.pdf").read_bytes().startswith(b"%PDF")
    assert json.loads((site / "api" / "project.json").read_text(encoding="utf-8"))["report"]["available"] is True
    assert (site / ".nojekyll").exists()


def test_no_student_number_in_the_static_copy(site):
    for f in (site / "api").rglob("*.json"):
        assert not re.search(r"\b20262\d{5}\b", f.read_text(encoding="utf-8")), f.name


def test_app_maps_every_server_path_for_the_static_copy():
    js = (REPO / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert re.findall(r'(?:src|href): "/(?:api|report)', js) == []      # every server path goes through url()
    assert "if (STATIC)" in js and 'dataset.site === "static"' in js
