"""Spec-pinning tests for the generated cube definition (ssas/FlightCube.xmla).

test_cube_xmla.py checks the headline properties (well-formed, registry names, role-playing,
measure types, named calculations, secrets, generated-and-current). This file pins the rest of
docs/cube-spec.md sections 1 to 3 and the Names registry, so a later edit of the generator that
changes any of these while keeping the suite green is not possible:

  * attribute relationships, OrderBy, key/name column bindings (spec tables 2.2 to 2.8)
  * the four user hierarchies and their levels
  * measure-group dimension granularity (key attribute and fact foreign key per cube dimension)
  * the 11 DSV foreign keys and the DSV columns/primary keys against sql/03_dw_tables.sql
  * All member / unknown member names, MOLAP storage, the MDX script
  * registry kinds (a level name is not satisfied by an attribute of the same name)

Where possible the expectations are parsed from the spec / the DDL text, never taken from
tools/build_cube_xmla.py. Everything is offline. The XMLA under test defaults to
ssas/FlightCube.xmla; set FDW_CUBE_XMLA=<path> to run the same tests against another file
(this is how the mutation checks are run on a scratch copy).

The opt-in live test (FDW_CUBE_TESTS=1) at the end queries the deployed cube read-only.
"""
import base64
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import namedtuple
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
XMLA = Path(os.environ.get("FDW_CUBE_XMLA") or REPO / "ssas" / "FlightCube.xmla")
SPEC = REPO / "docs" / "cube-spec.md"
DDL = REPO / "sql" / "03_dw_tables.sql"

ENG = "{http://schemas.microsoft.com/analysisservices/2003/engine}"
XS = "{http://www.w3.org/2001/XMLSchema}"
MSPROP = "{urn:schemas-microsoft-com:xml-msprop}"
MSDATA = "{urn:schemas-microsoft-com:xml-msdata}"
XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"
FACT = "Fact_FlightSegment"

ROOT = ET.parse(XMLA).getroot()
SPEC_TEXT = SPEC.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------- XMLA helpers
def _text(el, path):
    found = el.find(path)
    return None if found is None else (found.text or "")


def _db():
    db = ROOT.find(f".//{ENG}Database")
    assert db is not None, "no Database element"
    return db


def _db_dims():
    return {_text(d, f"{ENG}Name"): d for d in _db().findall(f"{ENG}Dimensions/{ENG}Dimension")}


def _cube():
    return _db().find(f"{ENG}Cubes/{ENG}Cube")


def _attributes(dim):
    return {_text(a, f"{ENG}Name"): a for a in dim.findall(f"{ENG}Attributes/{ENG}Attribute")}


def _dsv_tables():
    """{DSV table id (e.g. 'dw_DimDate'): xs:element of the table}."""
    return {el.get("name"): el for el in _db().iter(f"{XS}element") if el.get(f"{MSPROP}DbTableName")}


def _table_name(table_id):
    """DSV table id -> the real table name (DbTableName), not by stripping a prefix."""
    return _dsv_tables()[table_id].get(f"{MSPROP}DbTableName")


def _binding(item):
    """(table, column) of a KeyColumn / NameColumn / ValueColumn / Source element."""
    src = item.find(f"{ENG}Source") if item.tag != f"{ENG}Source" else item
    return _table_name(_text(src, f"{ENG}TableID")), _text(src, f"{ENG}ColumnID")


# ----------------------------------------------------------------------------- spec parsers
# Spec headings name cube dimensions, not database dimensions, so the section -> database
# dimension mapping is explicit (it is the spec's own statement in section 2 intro / 2.1).
DIM_SECTIONS = {"2.2": "Date", "2.3": "Passenger", "2.4": "Airport", "2.5": "Flight",
                "2.6": "Plane", "2.7": "Cabin", "2.8": "Price Range"}


def _sections():
    """{'2.2': body text, ...} for the '### 2.x' subsections of the dimension chapter."""
    parts = re.split(r"^### (\d\.\d) .*$", SPEC_TEXT, flags=re.M)
    return {num: re.split(r"\n## ", body, maxsplit=1)[0] for num, body in zip(parts[1::2], parts[2::2])}


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _first_code(cell):
    return re.search(r"`([^`]+)`", cell).group(1)


SpecAttr = namedtuple("SpecAttr", "dim name is_key key_table key_col name_table name_col order")


def _spec_attributes():
    """One SpecAttr per attribute row of the pipe tables in spec sections 2.2 to 2.8.

    Table of an attribute = the section's 'Source `dw.X`' unless the cell names another table in
    parentheses, e.g. '`AirlineKey` (`DimAirline`)'. Order by = first word of the 'Order by' cell.
    """
    out = []
    for num, dim in DIM_SECTIONS.items():
        body = _sections()[num]
        default_table = re.search(r"Source `dw\.(\w+)`", body).group(1)
        for line in body.splitlines():
            cells = _cells(line)
            if not line.startswith("|") or len(cells) < 5 or not cells[0].startswith("`"):
                continue
            attr, key, name, order = cells[0], cells[1], cells[2], cells[3]

            def table_of(cell, fallback=default_table):
                # An unqualified Name cell sits in the key's table (e.g. Airline Code: the key cell
                # says (`DimAirline`), the name cell only repeats `AirlineCode`).
                m = re.search(r"\(`(Dim\w+)`\)", cell)
                return m.group(1) if m else fallback

            out.append(SpecAttr(dim, _first_code(attr), "(dimension key)" in attr,
                                table_of(key), _first_code(key), table_of(name, table_of(key)), _first_code(name),
                                order.split()[0]))
    return out


def _spec_hierarchies():
    """{database dimension: {hierarchy: [levels]}} from the 'Hierarchy `X`: `A` > `B` ...' sentences."""
    out = {dim: {} for dim in DIM_SECTIONS.values()}
    for num, dim in DIM_SECTIONS.items():
        for m in re.finditer(r"Hierarchy `([^`]+)`: ((?:`[^`]+`(?: > )?)+)", _sections()[num]):
            out[dim][m.group(1)] = re.findall(r"`([^`]+)`", m.group(2))
    return out


def _spec_arrows():
    """{database dimension: set of (source, related)} from every '`A` -> `B` -> `C`' chain in 2.x."""
    out = {dim: set() for dim in DIM_SECTIONS.values()}
    for num, dim in DIM_SECTIONS.items():
        for chain in re.finditer(r"`[^`]+`(?: -> `[^`]+`)+", _sections()[num]):
            names = re.findall(r"`([^`]+)`", chain.group(0))
            out[dim].update(zip(names, names[1:]))
    return out


def _spec_role_playing():
    """[(cube dimension, database dimension, fact foreign key)] from the table in spec 2.1."""
    rows = []
    for line in _sections()["2.1"].splitlines():
        cells = _cells(line)
        if line.startswith("|") and len(cells) == 4 and cells[0].startswith("`"):
            rows.append((_first_code(cells[0]), _first_code(cells[1]), _first_code(cells[3])))
    return rows


def _spec_calculated_members():
    """{member: (format string, definition)} from the 'Calculated members' table in spec section 3."""
    block = SPEC_TEXT.split("### Calculated members", 1)[1].split("\n## ", 1)[0]
    out = {}
    for line in block.splitlines():
        cells = _cells(line)
        if line.startswith("|") and len(cells) == 3 and cells[0].startswith("`[Measures]."):
            out[re.match(r"`\[Measures\]\.\[(.+)\]`", cells[0]).group(1)] = (_first_code(cells[1]),
                                                                             _first_code(cells[2]))
    return out


SPEC_ATTRS = _spec_attributes()
SPEC_BY_KEY = {(a.dim, a.name): a for a in SPEC_ATTRS}
SPEC_KEY_ATTR = {a.dim: a.name for a in SPEC_ATTRS if a.is_key}
ATTR_IDS = [f"{a.dim}/{a.name}" for a in SPEC_ATTRS]

# Attribute relationships, transcribed from the spec sentences (section 2.2 line 'Attribute
# relationships: ...', 2.4, 2.5, 2.6 and the Seat -> Cabin Class statement in 2.7). Kept as an
# explicit dict as the task asks; test_relationship_table_matches_spec_text keeps it in step with
# the spec text, so the dict cannot silently diverge from the spec.
SPEC_RELATIONSHIPS = {
    "Date": [("Day", "Month"), ("Month", "Quarter"), ("Quarter", "Year"),
             ("Day", "Day Name"), ("Day", "Is Spring Festival")],
    "Airport": [("Airport", "Province")],
    "Flight": [("Ticket", "Flight No"), ("Flight No", "Airline"), ("Airline", "Airline Code"),
               ("Ticket", "Is Supplemented")],
    "Plane": [("Plane Model", "Size Class")],
    "Cabin": [("Seat", "Cabin Class")],
}
REL_CASES = [(dim, src, rel) for dim, pairs in SPEC_RELATIONSHIPS.items() for src, rel in pairs]

# Anchor expectations for the OrderBy column, stated again by hand so that a parser regression
# cannot turn the table-driven test into a vacuous one.
ORDER_ANCHORS = {("Date", "Month"): "Key", ("Passenger", "Age Band"): "Key", ("Plane", "Size Class"): "Key",
                 ("Passenger", "Workplace"): "Name", ("Airport", "Airport"): "Name",
                 ("Flight", "Airline"): "Name", ("Date", "Day Name"): "Key"}


def _rels_of(dim, attr_name):
    attr = _attributes(_db_dims()[dim])[attr_name]
    return [_text(r, f"{ENG}AttributeID") for r in attr.findall(f"{ENG}AttributeRelationships/{ENG}AttributeRelationship")]


# ----------------------------------------------------------------------------- spec parser sanity
def test_spec_parsers_found_everything():
    """The table-driven tests below follow the spec; make sure the parsers did not lose rows."""
    assert {a.dim for a in SPEC_ATTRS} == set(DIM_SECTIONS.values())
    assert len(SPEC_ATTRS) == 27, "attribute rows in spec tables 2.2 to 2.8"
    assert sorted(SPEC_KEY_ATTR) == sorted(DIM_SECTIONS.values()), "one '(dimension key)' row per dimension"
    assert {a.order for a in SPEC_ATTRS} == {"Key", "Name"}
    assert len(_spec_role_playing()) == 10
    assert sum(len(h) for h in _spec_hierarchies().values()) == 4
    assert len(_spec_calculated_members()) == 3
    for key, order in ORDER_ANCHORS.items():
        assert SPEC_BY_KEY[key].order == order, key


# ----------------------------------------------------------------------------- 1. relationships
@pytest.mark.parametrize("dim,src,rel", REL_CASES, ids=[f"{d}: {s} -> {r}" for d, s, r in REL_CASES])
def test_attribute_relationship_present(dim, src, rel):
    assert rel in _rels_of(dim, src), f"{dim}: attribute '{src}' has no relationship to '{rel}'"


def test_relationship_table_matches_spec_text():
    """SPEC_RELATIONSHIPS above is a faithful transcription of every '->' pair in spec 2.x."""
    parsed = _spec_arrows()
    for dim in DIM_SECTIONS.values():
        assert set(SPEC_RELATIONSHIPS.get(dim, [])) == parsed[dim], dim


@pytest.mark.parametrize("dim", sorted(DIM_SECTIONS.values()))
def test_no_relationship_beyond_spec_except_from_key(dim):
    """Relationships the spec does not state are only allowed as key attribute -> property
    (e.g. Passenger -> Gender, Plane Model -> Seat Count); never between non-key attributes."""
    stated = set(SPEC_RELATIONSHIPS.get(dim, []))
    for attr_name in _attributes(_db_dims()[dim]):
        for rel in _rels_of(dim, attr_name):
            if (attr_name, rel) not in stated:
                assert attr_name == SPEC_KEY_ATTR[dim], f"{dim}: unexpected relationship {attr_name} -> {rel}"


# ----------------------------------------------------------------------------- spec attribute set
@pytest.mark.parametrize("dim", sorted(DIM_SECTIONS.values()))
def test_attributes_equal_spec_tables(dim):
    spec_names = {a.name for a in SPEC_ATTRS if a.dim == dim}
    assert set(_attributes(_db_dims()[dim])) == spec_names


@pytest.mark.parametrize("dim", sorted(DIM_SECTIONS.values()))
def test_key_attribute_is_the_spec_dimension_key(dim):
    keys = [n for n, a in _attributes(_db_dims()[dim]).items() if _text(a, f"{ENG}Usage") == "Key"]
    assert keys == [SPEC_KEY_ATTR[dim]]


# ----------------------------------------------------------------------------- 2. OrderBy
@pytest.mark.parametrize("spec", SPEC_ATTRS, ids=ATTR_IDS)
def test_order_by_matches_spec(spec):
    attr = _attributes(_db_dims()[spec.dim])[spec.name]
    assert _text(attr, f"{ENG}OrderBy") == spec.order


@pytest.mark.parametrize("key,order", sorted(ORDER_ANCHORS.items()), ids=[f"{d}/{a}" for (d, a) in sorted(ORDER_ANCHORS)])
def test_order_by_anchors(key, order):
    dim, name = key
    assert _text(_attributes(_db_dims()[dim])[name], f"{ENG}OrderBy") == order


def test_order_by_key_columns_for_ordered_labels():
    """'Order by Key' only gives the intended order because the key column is the order column."""
    for dim, name, key_col in [("Passenger", "Age Band", "AgeBandOrder"), ("Plane", "Size Class", "SizeClassOrder"),
                               ("Date", "Month", "YearMonth"), ("Date", "Day Name", "DayOfWeek")]:
        attr = _attributes(_db_dims()[dim])[name]
        assert _text(attr, f"{ENG}OrderBy") == "Key"
        assert _binding(attr.find(f"{ENG}KeyColumns/{ENG}KeyColumn"))[1] == key_col


# ----------------------------------------------------------------------------- 3. key/name bindings
@pytest.mark.parametrize("spec", SPEC_ATTRS, ids=ATTR_IDS)
def test_key_column_binding(spec):
    attr = _attributes(_db_dims()[spec.dim])[spec.name]
    keys = attr.findall(f"{ENG}KeyColumns/{ENG}KeyColumn")
    assert len(keys) == 1, "single-column key expected"
    assert _binding(keys[0]) == (spec.key_table, spec.key_col)


@pytest.mark.parametrize("spec", SPEC_ATTRS, ids=ATTR_IDS)
def test_name_column_binding(spec):
    attr = _attributes(_db_dims()[spec.dim])[spec.name]
    name_col = attr.find(f"{ENG}NameColumn")
    assert name_col is not None, "attribute has no NameColumn"
    assert _binding(name_col) == (spec.name_table, spec.name_col)


def test_day_value_column_is_full_date():
    """Spec 2.2: Day key is DateKey, 'source FullDate' (the value column for date functions)."""
    day = _attributes(_db_dims()["Date"])["Day"]
    assert _binding(day.find(f"{ENG}ValueColumn")) == ("DimDate", "FullDate")


# The spec's numbered examples also fix a few concrete column pairs; stated by hand because the
# spec says them in prose/in a Notes cell rather than in a column (explicit dict, deliberately).
@pytest.mark.parametrize("dim,attr,key,name", [
    ("Passenger", "Age Band", ("DimPassenger", "AgeBandOrder"), ("DimPassenger", "AgeBand")),
    ("Plane", "Size Class", ("DimPlane", "SizeClassOrder"), ("DimPlane", "SizeClass")),
    ("Date", "Month", ("DimDate", "YearMonth"), ("DimDate", "MonthName")),
    ("Date", "Is Spring Festival", ("DimDate", "SpringFestivalKey"), ("DimDate", "SpringFestivalLabel")),
    ("Flight", "Airline", ("DimAirline", "AirlineKey"), ("DimAirline", "AirlineName")),
    ("Flight", "Airline Code", ("DimAirline", "AirlineCode"), ("DimAirline", "AirlineCode")),
    ("Flight", "Is Supplemented", ("DimTicket", "SupplementedKey"), ("DimTicket", "SupplementedLabel")),
])
def test_binding_anchors(dim, attr, key, name):
    a = _attributes(_db_dims()[dim])[attr]
    assert _binding(a.find(f"{ENG}KeyColumns/{ENG}KeyColumn")) == key
    assert _binding(a.find(f"{ENG}NameColumn")) == name


# ----------------------------------------------------------------------------- 4. hierarchies
@pytest.mark.parametrize("dim", sorted(DIM_SECTIONS.values()))
def test_hierarchies_match_spec(dim):
    found = {}
    for h in _db_dims()[dim].findall(f"{ENG}Hierarchies/{ENG}Hierarchy"):
        levels = h.findall(f"{ENG}Levels/{ENG}Level")
        found[_text(h, f"{ENG}Name")] = [_text(l, f"{ENG}Name") for l in levels]
        # a level is built on the attribute of the same name (spec registry: level = attribute name)
        assert [_text(l, f"{ENG}SourceAttributeID") for l in levels] == found[_text(h, f"{ENG}Name")]
    assert found == _spec_hierarchies()[dim]


def test_four_user_hierarchies_on_the_right_dimensions():
    assert {d: sorted(h) for d, h in _spec_hierarchies().items() if h} == {
        "Date": ["Calendar"], "Airport": ["Geography"], "Flight": ["Airline Flight"], "Plane": ["Plane Class"]}


# ----------------------------------------------------------------------------- 5. granularity
def _mg_dimensions(mg):
    return {_text(d, f"{ENG}CubeDimensionID"): d for d in mg.findall(f"{ENG}Dimensions/{ENG}Dimension")}


@pytest.mark.parametrize("mg_name", ["Flight Segments", "Segment Passengers"])
def test_measure_group_granularity(mg_name):
    """Every cube dimension is related on its fact key AND at the dimension's key attribute."""
    spec = {cube_dim: (db_dim, fk) for cube_dim, db_dim, fk in _spec_role_playing()}
    mgs = {_text(m, f"{ENG}Name"): m for m in _cube().findall(f"{ENG}MeasureGroups/{ENG}MeasureGroup")}
    dims = _mg_dimensions(mgs[mg_name])
    assert set(dims) == set(spec)
    for cube_dim, (db_dim, fk) in spec.items():
        d = dims[cube_dim]
        attrs = d.findall(f"{ENG}Attributes/{ENG}Attribute")
        assert len(attrs) == 1, f"{cube_dim}: exactly one granularity attribute"
        a = attrs[0]
        assert _text(a, f"{ENG}AttributeID") == SPEC_KEY_ATTR[db_dim], \
            f"{cube_dim}: granularity must be the key attribute {SPEC_KEY_ATTR[db_dim]}"
        assert _text(a, f"{ENG}Type") == "Granularity"
        keys = a.findall(f"{ENG}KeyColumns/{ENG}KeyColumn")
        assert len(keys) == 1 and _binding(keys[0]) == (FACT, fk), f"{cube_dim}: fact key {fk}"


def test_granularity_examples_from_the_task():
    """The three examples that matter most, stated by hand: dates at Day (DateKey), Flight at TicketKey."""
    mg = _cube().find(f"{ENG}MeasureGroups/{ENG}MeasureGroup")
    dims = _mg_dimensions(mg)
    for cube_dim, attr, fk in [("Departure Date", "Day", "DepartureDateKey"), ("Arrival Date", "Day", "ArrivalDateKey"),
                               ("Flight", "Ticket", "TicketKey")]:
        a = dims[cube_dim].find(f"{ENG}Attributes/{ENG}Attribute")
        assert _text(a, f"{ENG}AttributeID") == attr
        assert _binding(a.find(f"{ENG}KeyColumns/{ENG}KeyColumn")) == (FACT, fk)


def test_cube_dimensions_reference_the_spec_database_dimensions():
    cube_dims = {_text(d, f"{ENG}Name"): _text(d, f"{ENG}DimensionID")
                 for d in _cube().findall(f"{ENG}Dimensions/{ENG}Dimension")}
    assert cube_dims == {c: d for c, d, _ in _spec_role_playing()}


# ----------------------------------------------------------------------------- DDL parser
_COLUMN = re.compile(r"^\[?(\w+)\]?\s+(INT|SMALLINT|TINYINT|BIT|DATETIME2\(\d+\)|DATE|DECIMAL\(\d+,\d+\)|"
                     r"(?:N?VARCHAR|N?CHAR)\((\d+)\))\s+(NOT NULL|NULL)\b(.*)$")
_FK = re.compile(r"^CONSTRAINT (\w+)\s+FOREIGN KEY\s+\((\w+)\)\s+REFERENCES dw\.(\w+)\s+\((\w+)\)$")
# Own mapping SQL type -> XSD base type of a DSV column (SSAS stores DATE as xs:dateTime).
SQL_TO_XS = {"INT": "xs:int", "SMALLINT": "xs:short", "TINYINT": "xs:unsignedByte", "BIT": "xs:boolean",
             "DATE": "xs:dateTime", "DATETIME2": "xs:dateTime", "DECIMAL": "xs:decimal",
             "NVARCHAR": "xs:string", "VARCHAR": "xs:string", "NCHAR": "xs:string", "CHAR": "xs:string"}


def _ddl():
    """{table: {'columns': {name: (xs type, max length, nullable)}, 'pk': (name, [cols]), 'fks': [..]}}"""
    text = DDL.read_text(encoding="utf-8")
    tables = {}
    for m in re.finditer(r"CREATE TABLE dw\.(\w+) \((.*?)\n\);", text, re.S):
        name, body = m.groups()
        cols, pk_name, pk_cols, fks = {}, None, [], []
        for raw in body.splitlines():
            line = raw.split("--", 1)[0].strip().rstrip(",").strip()
            if not line:
                continue
            col = _COLUMN.match(line)
            fk = _FK.match(line)
            if fk:
                fks.append((fk.group(1), name, fk.group(2), fk.group(3), fk.group(4)))
            elif col:
                sql = col.group(2).split("(")[0]
                length = int(col.group(3)) if col.group(3) else None
                cols[col.group(1)] = (SQL_TO_XS[sql], length, col.group(4) == "NULL")
                pkm = re.search(r"CONSTRAINT (\w+) PRIMARY KEY", col.group(5))
                if pkm:
                    pk_name, pk_cols = pkm.group(1), pk_cols + [col.group(1)]
            elif not (line.startswith("CONSTRAINT ") and re.search(r"CHECK|DEFAULT", line)):
                raise AssertionError(f"unparsed DDL line in dw.{name}: {raw!r}")
        tables[name] = {"columns": cols, "pk": (pk_name, pk_cols), "fks": fks}
    return tables


DDL_TABLES = _ddl()


def test_ddl_parser_sanity():
    assert set(DDL_TABLES) == {"DimDate", "DimPassenger", "DimAirline", "DimTicket", "DimAirport", "DimPlane",
                               "DimSeat", "DimPriceRange", "Fact_FlightSegment"}
    assert sum(len(t["fks"]) for t in DDL_TABLES.values()) == 11          # spec section 1: 11 foreign keys
    assert all(t["pk"][1] for t in DDL_TABLES.values())


# ----------------------------------------------------------------------------- 6. foreign keys
def _dsv_primary_keys():
    """{table: (constraint name, [columns])} from the xs:unique elements marked PrimaryKey."""
    tables = _dsv_tables()
    out = {}
    for u in _db().iter(f"{XS}unique"):
        if u.get(f"{MSDATA}PrimaryKey") != "true":
            continue
        table = tables[u.find(f"{XS}selector").get("xpath").removeprefix(".//")].get(f"{MSPROP}DbTableName")
        out[table] = (u.get("name"), [f.get("xpath") for f in u.findall(f"{XS}field")])
    return out


def _dsv_foreign_keys():
    """{(constraint name, child table, child column, parent table, parent column)} from xs:keyref."""
    tables = _dsv_tables()
    pks = {name: (tbl, cols) for tbl, (name, cols) in _dsv_primary_keys().items()}
    out = set()
    for k in _db().iter(f"{XS}keyref"):
        child = tables[k.find(f"{XS}selector").get("xpath").removeprefix(".//")].get(f"{MSPROP}DbTableName")
        fields = [f.get("xpath") for f in k.findall(f"{XS}field")]
        parent, parent_cols = pks[k.get("refer")]
        assert len(fields) == 1 and len(parent_cols) == 1
        out.add((k.get("name"), child, fields[0], parent, parent_cols[0]))
    return out


def test_dsv_foreign_keys_equal_ddl():
    expected = {fk for t in DDL_TABLES.values() for fk in t["fks"]}
    assert len(expected) == 11
    assert _dsv_foreign_keys() == expected


def test_dsv_foreign_key_pairs_equal_ddl_without_names():
    """Same check on the bare (child.column -> parent.column) pairs: the names may change, the pairs not."""
    expected = {(c, cc, p, pc) for (_n, c, cc, p, pc) in (fk for t in DDL_TABLES.values() for fk in t["fks"])}
    assert {fk[1:] for fk in _dsv_foreign_keys()} == expected


# ----------------------------------------------------------------------------- 7. DSV vs DDL
# The one documented difference: PassengerName is deliberately not in the DSV (spec 2.3 / rule 1:
# 9,632 duplicate and 610 NULL names; names are never exposed).
ALLOWED_DDL_ONLY = {("DimPassenger", "PassengerName")}


def _dsv_columns(table_el):
    """({column: (xs type, max length, nullable)}, {calculated column: expression}, {column: DbColumnName})"""
    cols, calcs, dbnames = {}, {}, {}
    for el in table_el.findall(f"{XS}complexType/{XS}sequence/{XS}element"):
        name = el.get("name")
        dbnames[name] = el.get(f"{MSPROP}DbColumnName")
        if el.get(f"{MSPROP}ComputedColumnExpression") is not None:
            calcs[name] = el.get(f"{MSPROP}ComputedColumnExpression")
            continue
        restriction = el.find(f"{XS}simpleType/{XS}restriction")
        if restriction is not None:
            base = restriction.get("base")
            length = int(restriction.find(f"{XS}maxLength").get("value"))
        else:
            base, length = el.get("type"), None
        cols[name] = (base, length, el.get("minOccurs") == "0")
    return cols, calcs, dbnames


@pytest.mark.parametrize("table", sorted(DDL_TABLES))
def test_dsv_columns_equal_ddl(table):
    cols, calcs, dbnames = _dsv_columns(_dsv_tables()[f"dw_{table}"])
    expected = {c: spec for c, spec in DDL_TABLES[table]["columns"].items() if (table, c) not in ALLOWED_DDL_ONLY}
    assert cols == expected, "DSV columns (names, base types, lengths, nullability) differ from sql/03_dw_tables.sql"
    assert not set(calcs) & set(DDL_TABLES[table]["columns"]), "named calculation shadows a DDL column"
    assert all(dbnames[c] == c for c in cols), "DbColumnName must equal the column name"


def test_dsv_has_only_the_documented_ddl_difference():
    tables = _dsv_tables()
    missing = {(t, c) for t in DDL_TABLES for c in DDL_TABLES[t]["columns"]
               if c not in _dsv_columns(tables[f"dw_{t}"])[0]}
    assert missing == ALLOWED_DDL_ONLY


@pytest.mark.parametrize("table", sorted(DDL_TABLES))
def test_dsv_primary_key_equals_ddl(table):
    assert _dsv_primary_keys()[table] == DDL_TABLES[table]["pk"]


def test_dsv_primary_keys_cover_only_dw_tables():
    assert set(_dsv_primary_keys()) == set(DDL_TABLES)


def test_named_calculations_are_the_extra_columns():
    spec_named = {}
    block = SPEC_TEXT.split("### DSV named calculations", 1)[1].split("\n## ", 1)[0]
    for line in block.splitlines():
        cells = _cells(line)
        if line.startswith("|") and len(cells) >= 3 and cells[0].startswith("`"):
            spec_named.setdefault(_first_code(cells[0]), set()).add(_first_code(cells[1]))
    for table in DDL_TABLES:
        _cols, calcs, _db = _dsv_columns(_dsv_tables()[f"dw_{table}"])
        assert set(calcs) == spec_named.get(table, set()), table


# ----------------------------------------------------------------------------- 8. misc spec items
@pytest.mark.parametrize("dim", sorted(DIM_SECTIONS.values()))
def test_all_and_unknown_member_names(dim):
    d = _db_dims()[dim]
    assert _text(d, f"{ENG}AttributeAllMemberName") == "All"
    assert _text(d, f"{ENG}UnknownMember") == "None"
    for h in d.findall(f"{ENG}Hierarchies/{ENG}Hierarchy"):
        assert _text(h, f"{ENG}AllMemberName") == "All", _text(h, f"{ENG}Name")
    for name, a in _attributes(d).items():
        # defaults (element absent) mean enabled and aggregatable, i.e. an 'All' member exists
        assert _text(a, f"{ENG}IsAggregatable") in (None, "true"), name
        assert _text(a, f"{ENG}AttributeHierarchyEnabled") in (None, "true"), name


def test_molap_on_cube_measure_groups_and_partitions():
    cube = _cube()
    assert _text(cube, f"{ENG}StorageMode") == "Molap"
    mgs = cube.findall(f"{ENG}MeasureGroups/{ENG}MeasureGroup")
    assert len(mgs) == 2
    for mg in mgs:
        assert _text(mg, f"{ENG}StorageMode") == "Molap"
        parts = mg.findall(f"{ENG}Partitions/{ENG}Partition")
        assert len(parts) == 1
        assert _text(parts[0], f"{ENG}StorageMode") == "Molap"


def _script():
    return "\n".join(_text(c, f"{ENG}Text") for c in _cube().iter(f"{ENG}Command"))


def test_mdx_script_calculates_first():
    statements = [s.strip() for s in _script().split(";") if s.strip()]
    assert statements[0] == "CALCULATE"
    assert len(statements) == 1 + 3


@pytest.mark.parametrize("member", ["Average Price", "Average Rate", "Stopover Share"])
def test_calculated_member_format_visibility_and_definition(member):
    fmt, definition = _spec_calculated_members()[member]
    m = re.search(r"CREATE MEMBER CURRENTCUBE\.\[Measures\]\.\[" + re.escape(member) + r"\] AS (.+?), "
                  r'FORMAT_STRING = "([^"]*)", VISIBLE = (\d);', _script())
    assert m, f"no CREATE MEMBER statement for {member}"
    assert m.group(1) == definition
    assert m.group(2) == fmt
    assert m.group(3) == "1"


def test_calculated_members_are_exactly_the_spec_ones():
    found = re.findall(r"CREATE MEMBER CURRENTCUBE\.\[Measures\]\.\[([^\]]+)\]", _script())
    assert sorted(found) == sorted(_spec_calculated_members())


# ----------------------------------------------------------------------------- 9. registry kinds
def _registry():
    block = SPEC_TEXT.split("## 6. Names registry", 1)[1]
    reg = {}
    for line in block.splitlines():
        m = re.match(r"^([a-z ]+):\s+(.+)$", line.strip())
        if m:
            reg.setdefault(m.group(1), set()).add(m.group(2).strip())
    return reg


def _objects_by_kind():
    """Names of the XMLA objects of each registry kind, looked up in the right place only: levels
    live inside hierarchies, attributes in the dimension's attribute list."""
    db = _db()
    dims = db.findall(f"{ENG}Dimensions/{ENG}Dimension")
    cube = _cube()
    names = lambda els: {_text(e, f"{ENG}Name") for e in els}        # noqa: E731
    return {
        "cube": names(db.findall(f"{ENG}Cubes/{ENG}Cube")),
        "database": {_text(db, f"{ENG}Name")},
        "data source": names(db.findall(f"{ENG}DataSources/{ENG}DataSource")),
        "data source view": names(db.findall(f"{ENG}DataSourceViews/{ENG}DataSourceView")),
        "measure group": names(cube.findall(f"{ENG}MeasureGroups/{ENG}MeasureGroup")),
        "measure": names(cube.findall(f"{ENG}MeasureGroups/{ENG}MeasureGroup/{ENG}Measures/{ENG}Measure")),
        "calculated member": set(re.findall(r"CREATE MEMBER CURRENTCUBE\.\[Measures\]\.\[([^\]]+)\]", _script())),
        "dimension": names(cube.findall(f"{ENG}Dimensions/{ENG}Dimension")),         # cube (role) dimensions
        "database dimension": names(dims),
        "hierarchy": names(h for d in dims for h in d.findall(f"{ENG}Hierarchies/{ENG}Hierarchy")),
        "level": names(l for d in dims for l in d.findall(f"{ENG}Hierarchies/{ENG}Hierarchy/{ENG}Levels/{ENG}Level")),
        "attribute": names(a for d in dims for a in d.findall(f"{ENG}Attributes/{ENG}Attribute")),
    }


# 'member' lines are data values (members of attributes), not metadata: checked live, not here.
_REG_CASES = [(kind, name) for kind, vals in sorted(_registry().items()) if kind != "member" for name in sorted(vals)]


def test_registry_kinds_are_known():
    assert set(_registry()) - {"member"} == set(_objects_by_kind())


@pytest.mark.parametrize("kind,name", _REG_CASES, ids=[f"{k}: {n}" for k, n in _REG_CASES])
def test_registry_name_exists_with_its_kind(kind, name):
    assert name in _objects_by_kind()[kind], f"registry '{kind}: {name}' has no object of that kind in the XMLA"


# ----------------------------------------------------------------------------- live test (opt-in)
_LIVE_PS = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try { Import-Module SqlServer -DisableNameChecking -ErrorAction Stop } catch {
    $m = @(Get-ChildItem (Join-Path $env:USERPROFILE 'Documents\WindowsPowerShell\Modules\SqlServer') -Filter 'SqlServer.psd1' -Recurse |
           Sort-Object { [version]$_.Directory.Name } -Descending)
    if ($m.Count -eq 0) { throw 'SqlServer module not found' }
    Import-Module $m[0].FullName -DisableNameChecking
}
$svc = Get-CimInstance Win32_Service -Filter ("Name='MSOLAP`${0}'" -f '__INSTANCE__')
if (-not $svc -or -not $svc.ProcessId) { throw 'Analysis Services instance __INSTANCE__ is not running' }
$port = @(Get-NetTCPConnection -State Listen -OwningProcess $svc.ProcessId | Select-Object -ExpandProperty LocalPort -Unique)[0]
$mdx = @'
__MDX__
'@
$r = [string](Invoke-ASCmd -Server "localhost:$port" -Database 'FlightCube' -Query $mdx)
if ($r -match '<Error\b|<Exception\b') { throw $r }
$xml = [xml]$r
$ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
$ns.AddNamespace('md', 'urn:schemas-microsoft-com:xml-analysis:mddataset')
$cols = @($xml.SelectNodes("//md:Axes/md:Axis[@name='Axis0']/md:Tuples/md:Tuple", $ns) | ForEach-Object { $_.SelectSingleNode('md:Member/md:Caption', $ns).InnerText })
$vals = @{}
foreach ($c in $xml.SelectNodes('//md:CellData/md:Cell', $ns)) { $v = $c.SelectSingleNode('md:Value', $ns); $vals[[int]$c.CellOrdinal] = if ($v) { $v.InnerText } else { '' } }
for ($i = 0; $i -lt $cols.Count; $i++) { [Console]::Out.WriteLine(('LIVE {0} = {1}' -f $cols[$i], $vals[$i])) }
"""

# One read-only SELECT; the member counts are query-scoped calculated members (nothing is created
# on the server). Rate Sum is the hidden measure: MDX can still address it by name.
_LIVE_MDX = """WITH
MEMBER [Measures].[Airline Members] AS [Flight].[Airline Flight].[Airline].Members.Count
MEMBER [Measures].[Airline Non-Empty] AS Count(NonEmpty([Flight].[Airline Flight].[Airline].Members, [Measures].[Segment Count]))
MEMBER [Measures].[Price Grade Members] AS [Price Range].[Price Grade].[Price Grade].Members.Count
MEMBER [Measures].[Price Grade Non-Empty] AS Count(NonEmpty([Price Range].[Price Grade].[Price Grade].Members, [Measures].[Segment Count]))
MEMBER [Measures].[Age Band Members] AS [Passenger].[Age Band].[Age Band].Members.Count
SELECT { [Measures].[Total Mileage], [Measures].[Rate Sum], [Measures].[Average Rate], [Measures].[Stopover Share],
         [Measures].[Airline Members], [Measures].[Airline Non-Empty],
         [Measures].[Price Grade Members], [Measures].[Price Grade Non-Empty], [Measures].[Age Band Members] } ON 0
FROM [FlightCube]"""


def _run_live_query():
    script = _LIVE_PS.replace("__INSTANCE__", os.environ.get("FDW_CUBE_INSTANCE", "DEV")).replace("__MDX__", _LIVE_MDX)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                         capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert out.returncode == 0, out.stdout + out.stderr
    return {k: float(v) for k, v in re.findall(r"^LIVE\s+(.+?)\s*=\s*(\S+)\s*$", out.stdout, re.MULTILINE)}


@pytest.mark.skipif(os.environ.get("FDW_CUBE_TESTS") != "1", reason="set FDW_CUBE_TESTS=1 to query the live cube")
def test_live_measures_and_member_counts():
    v = _run_live_query()
    assert v["Total Mileage"] == 1001283
    assert v["Rate Sum"] == pytest.approx(470.68, abs=0.005)
    assert v["Average Rate"] == pytest.approx(0.784, abs=0.0005)
    assert v["Stopover Share"] == pytest.approx(0.158, abs=0.0005)
    assert v["Airline Members"] == 18
    assert v["Airline Non-Empty"] == 11
    assert v["Price Grade Members"] == 30
    assert v["Price Grade Non-Empty"] == 28
    assert v["Age Band Members"] == 7
