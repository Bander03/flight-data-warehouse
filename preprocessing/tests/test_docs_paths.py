"""Every repository path written in backticks in a Markdown document (README, docs, report sections, sql/mdx guides)
must exist: a renamed or deleted file must not leave a wrong instruction behind."""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DOCS = [p for p in REPO.rglob("*.md")
        if not {".git", "build", "node_modules"} & set(p.relative_to(REPO).parts)]
PATH = re.compile(r"`((?:docs|sql|mdx|tools|preprocessing|report|ssas|ssis)[\\/][^`\s*<>|?]+?)`")
# local-only or generated locations that legitimately are not in git
IGNORE_PREFIX = ("report/build/", "data/", "ssis/FlightDWLoad/bin", "ssis/FlightDWLoad/obj")
IGNORE_MARKERS = ("{", "}", "$", "<", "NN_", "...", "<stem>")


def _paths():
    out = []
    for f in DOCS:
        for m in PATH.finditer(f.read_text(encoding="utf-8", errors="ignore")):
            p = m.group(1).replace("\\", "/").rstrip(".,;:)")
            if p.endswith("/") or any(x in p for x in IGNORE_MARKERS) or p.startswith(IGNORE_PREFIX):
                continue
            out.append((f.relative_to(REPO).as_posix(), p))
    return sorted(set(out))


@pytest.mark.parametrize("doc,path", _paths(), ids=lambda v: v)
def test_documented_path_exists(doc, path):
    assert (REPO / path).exists() or any(REPO.glob(path)), f"{doc} names {path}, which does not exist"
