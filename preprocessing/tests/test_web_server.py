"""HTTP server and JSON API of the local website (web/server.py)."""
import hashlib
import json
import re
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from web import server  # noqa: E402

SAVED = REPO / "mdx" / "results" / "05_rank_1.csv"


@pytest.fixture()
def base():
    calls = []

    def fake_live(stem):
        calls.append(stem)
        return {"ok": True, "rows": [], "matches_saved": True, "differences": [], "seconds": 0.1}
    httpd = server.make_server(port=0, live=fake_live)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", httpd, calls
    httpd.shutdown()
    httpd.server_close()


def get(url, method="GET"):
    req = urllib.request.Request(url, method=method, data=b"" if method == "POST" else None)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def test_index_is_html(base):
    status, headers, body = get(base[0] + "/")
    assert status == 200 and "text/html" in headers["Content-Type"] and b"<title>" in body


def test_bound_to_localhost_only(base):
    assert base[1].server_address[0] == "127.0.0.1"


def test_api_lists_28_analyses(base):
    status, headers, body = get(base[0] + "/api/analyses")
    assert status == 200 and "application/json" in headers["Content-Type"] and headers["Cache-Control"] == "no-store"
    assert len(json.loads(body)["analyses"]) == 28


def test_api_one_analysis_has_chinese_and_match(base):
    status, _, body = get(base[0] + "/api/analyses/05_rank_1")
    d = json.loads(body.decode("utf-8"))
    assert status == 200 and d["rows"][0]["Member"] == "中国东方航空" and d["ranked"] is True
    assert "mdx" in d and "answer_sql" in d


def test_api_overview_and_match(base):
    d = json.loads(get(base[0] + "/api/overview")[2])
    assert d["segments"] == 600 and d["match"]["matched"] == 28 and d["match"]["total"] == 28


@pytest.mark.parametrize("path", ["/api/analyses/nope", "/api/analyses/..%2fREADME", "/api/analyses/%2e%2e",
                                  "/static/..%2f..%2fREADME.md", "/static/../../README.md", "/nothing",
                                  "/static/", "/api/live/x;calc"])
def test_unknown_or_traversal_is_404(base, path):
    method = "POST" if path.startswith("/api/live") else "GET"
    assert get(base[0] + path, method)[0] == 404


def test_live_is_post_only(base):
    assert get(base[0] + "/api/live/05_rank_1")[0] == 405


def test_live_post_calls_runner_once(base):
    url, _, calls = base
    status, _, body = get(url + "/api/live/05_rank_1", "POST")
    assert status == 200 and json.loads(body)["matches_saved"] is True and calls == ["05_rank_1"]


def test_live_unknown_stem_never_reaches_runner(base):
    url, _, calls = base
    assert get(url + "/api/live/not_a_stem", "POST")[0] == 404 and calls == []


def test_static_files_and_figure(base):
    url = base[0]
    for name in ("style.css", "app.js"):
        assert get(f"{url}/static/{name}")[0] == 200, name
    status, headers, body = get(url + "/api/figure/star-schema")
    assert status == 200 and headers["Content-Type"] == "image/png" and body[:4] == b"\x89PNG"


def test_requests_do_not_change_saved_results(base):
    before = hashlib.sha256(SAVED.read_bytes()).hexdigest()
    get(base[0] + "/api/live/05_rank_1", "POST")
    get(base[0] + "/api/analyses/05_rank_1")
    assert hashlib.sha256(SAVED.read_bytes()).hexdigest() == before


def test_foreign_host_header_is_refused(base):
    """DNS-rebinding guard: only requests addressed to this computer are answered."""
    import http.client
    port = base[1].server_address[1]
    for host, expected in (("evil.example.com", 403), (f"127.0.0.1:{port}", 200), (f"localhost:{port}", 200)):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("GET", "/api/analyses", headers={"Host": host})
        assert conn.getresponse().status == expected, host
        conn.close()


def test_api_project_names_the_team_and_teacher(base):
    d = json.loads(get(base[0] + "/api/project")[2])
    assert [m["name"] for m in d["members"]] == ["Bander Sidiq Mahmood", "Yohannes Abate Ejita", "Hina Shamshad"]
    assert d["members"][0]["leader"] and d["teacher"] == "Prof Yan Zhu" and d["group"] == "2"
    assert "Student ID" not in json.dumps(d) and not re.search(r"\b\d{10}\b", json.dumps(d))   # student numbers stay in the report


def test_api_profile_has_the_17_guide_rules(base):
    d = json.loads(get(base[0] + "/api/profile")[2])
    assert len(d["rules"]) == 17 and d["passed_before"] == 9 and d["passed_after"] == 17


def test_api_requirements_link_to_pages_of_the_site(base):
    d = json.loads(get(base[0] + "/api/requirements")[2])
    assert len(d["items"]) >= 10
    assert all(i["source"] and i["requirement"] and i["evidence"] and i["link"].startswith("#/") for i in d["items"])


def test_screenshot_of_a_statement_is_a_jpeg(base):
    status, headers, body = get(base[0] + "/api/screenshot/01_drill_down_1")
    assert status == 200 and headers["Content-Type"] == "image/jpeg" and body[:2] == b"\xff\xd8"


@pytest.mark.parametrize("path", ["/api/screenshot/nope", "/api/screenshot/..%2fM01.1", "/api/screenshot/"])
def test_unknown_screenshot_is_404(base, path):
    assert get(base[0] + path)[0] == 404


def test_report_pdf_is_served_when_built(base):
    from web import data
    status, headers, body = get(base[0] + "/report.pdf")
    if data.REPORT_PDF.exists():
        assert status == 200 and headers["Content-Type"] == "application/pdf" and body[:4] == b"%PDF"
    else:
        assert status == 404


def test_ssis_figure_is_served(base):
    status, headers, _ = get(base[0] + "/api/figure/ssis")
    assert status == 200 and headers["Content-Type"] == "image/png"
