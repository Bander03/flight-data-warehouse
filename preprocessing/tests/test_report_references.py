"""References of the report: numbered in order of first citation, every listed reference is cited, every citation is listed."""
import re
from pathlib import Path

SECTIONS = Path(__file__).resolve().parents[2] / "report" / "sections"
CITE = re.compile(r"\[(\d+)\]")


def _body_text():
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(SECTIONS.glob("0*.md"))
                     if p.name[:2] not in ("06", "07"))


def _references():
    text = (SECTIONS / "06_references.md").read_text(encoding="utf-8")
    return [int(m.group(1)) for m in re.finditer(r"^\[(\d+)\]\s+\S", text, re.M)]


def test_references_are_numbered_consecutively():
    refs = _references()
    assert refs == list(range(1, len(refs) + 1)) and refs


def test_citations_follow_order_of_first_appearance():
    body = re.sub(r"```.*?```", "", _body_text(), flags=re.S)            # MDX code contains [Measures] style brackets
    first = []
    for m in CITE.finditer(body):
        n = int(m.group(1))
        if n not in first:
            first.append(n)
    assert first == sorted(first), f"citations first appear in the order {first}"


def test_every_reference_is_cited_and_every_citation_is_listed():
    body = re.sub(r"```.*?```", "", _body_text(), flags=re.S)
    cited = {int(m.group(1)) for m in CITE.finditer(body)}
    assert cited == set(_references())
