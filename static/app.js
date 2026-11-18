/* Flight Data Warehouse: local website. Plain JavaScript, no libraries, no external requests.
   All text is added as text nodes (never as markup), so data can never inject HTML. */
"use strict";

const app = document.getElementById("app");
const tip = document.getElementById("tip");
/* The hosted copy (GitHub Pages) has no server: tools/build_static_site.py saves every answer as a file and marks the
   page with data-site="static"; url() then points each request at that file (relative, so any sub-path works). */
const STATIC = document.documentElement.dataset.site === "static";

function url(path) {
  if (!STATIC) return path;
  if (path === "/report.pdf") return "report.pdf";
  if (path.startsWith("/api/screenshot/")) return "screenshots/" + path.slice("/api/screenshot/".length) + ".jpg";
  if (path.startsWith("/api/figure/")) return "figures/" + path.slice("/api/figure/".length) + ".png";
  if (path.startsWith("/api/analyses/")) return "api/analyses/" + path.slice("/api/analyses/".length) + ".json";
  if (path.startsWith("/api/")) return path.slice(1) + ".json";
  return path;
}

/* ---------- small helpers ---------- */
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v === null || v === undefined) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

/* Each navigation gets a new number; data that arrives for an older page is dropped, so a slow page can never
   replace the page the reader has moved on to. */
let routeNo = 0;
class StalePage extends Error {}

async function api(path, options) {
  const asked = routeNo;
  const res = await fetch(url(path), options);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  const body = await res.json();
  if (asked !== routeNo) throw new StalePage();
  return body;
}

const n = v => Number(v).toLocaleString("en-US");

function fmt(value, measure) {
  if (value === null || value === undefined || Number.isNaN(value)) return "";
  if (measure === "Stopover Share") return (value * 100).toFixed(1) + "%";
  const whole = Number.isInteger(value);
  return value.toLocaleString("en-US", { minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: 2 });
}

function setNav(name) {
  document.querySelectorAll("nav a").forEach(a => {
    if (a.dataset.nav === name) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
}

function show(...nodes) { hideTip(); app.replaceChildren(...nodes); window.scrollTo(0, 0); }

function pageHead(eyebrow, title, lead, ...extra) {
  return h("header", { class: "page-head" }, eyebrow ? h("div", { class: "eyebrow" }, eyebrow) : null,
    h("h1", null, title), lead ? h("p", { class: "lead" }, lead) : null, extra.length ? h("div", { class: "row-gap" }, extra) : null);
}

function card(title, aside, ...body) {
  return h("section", { class: "card" },
    title || aside ? h("div", { class: "card-head" }, title ? h("h2", null, title) : null, aside || null) : null, body);
}

function kpi(num, lab, sub, accent) {
  return h("div", { class: "kpi" + (accent ? " accent" : "") }, h("div", { class: "num" }, num),
    h("div", { class: "lab" }, lab), sub ? h("div", { class: "sub" }, sub) : null);
}

function matchBadge(match) {
  if (!match || match.matched === null) return h("span", { class: "badge warn" }, "Cross-check not recorded");
  const ok = match.matched === match.total;
  return h("span", { class: "badge " + (ok ? "good" : "warn") },
    ok ? "✓ " : "! ", `${match.matched} of ${match.total} analyses match the T-SQL answer keys`);
}

function stem(text) { return h("span", { class: "stem" }, text); }

/* ---------- hover / focus tooltip ---------- */
function tipAt(x, y, kids) {
  tip.replaceChildren(...kids.map(k => (k.nodeType ? k : document.createTextNode(String(k)))));
  tip.hidden = false;
  const r = tip.getBoundingClientRect();
  let left = x + 14, top = y - r.height - 10;
  if (left + r.width > innerWidth - 8) left = x - r.width - 14;
  if (top < 8) top = y + 18;
  tip.style.left = Math.max(8, left) + "px";
  tip.style.top = top + "px";
}
function hideTip() { tip.hidden = true; }
function withTip(el, kids) {
  el.addEventListener("pointermove", e => tipAt(e.clientX, e.clientY, kids()));
  el.addEventListener("pointerleave", hideTip);
  el.addEventListener("focus", () => { const r = el.getBoundingClientRect(); tipAt(r.left + r.width / 2, r.top, kids()); });
  el.addEventListener("blur", hideTip);
  return el;
}

/* ---------- charts and tables ---------- */
function columnChart(rows, measure) {
  const max = Math.max(...rows.map(r => r.Value), 0) || 1;
  const hi = rows.reduce((a, b) => (b.Value > a.Value ? b : a), rows[0]);
  const lo = rows.reduce((a, b) => (b.Value < a.Value ? b : a), rows[0]);
  const cols = h("div", { class: "cols", role: "img",
    "aria-label": `Column chart of ${measure} by month, ${rows.length} months. The table view has the same numbers.` });
  for (const r of rows) {
    const pct = (r.Value / max) * 100;
    const labelled = r === hi || r === lo;
    cols.append(withTip(h("div", { class: "col", tabindex: "0", "aria-label": `${r.Member}: ${fmt(r.Value, measure)}` },
      labelled ? h("span", { class: "col-val", style: `bottom:calc(${pct}% + 4px)` }, fmt(r.Value, measure)) : null,
      h("div", { class: "col-bar", style: `height:${pct}%` })),
      () => [r.Member + ": ", h("b", null, fmt(r.Value, measure))]));
  }
  const labels = h("div", { class: "col-labels", "aria-hidden": "true" }, rows.map(r => h("span", null, r.Member.slice(0, 3))));
  return h("div", null, cols, labels);
}

function barChart(statement, altRule) {
  const rows = statement.rows;
  const max = Math.max(...rows.map(r => r.Value), 0) || 1;
  const box = h("div", { class: "bars", role: "img",
    "aria-label": `Bar chart of ${statement.measure}, ${rows.length} rows. The table view has the same numbers.` });
  for (const r of rows) {
    const label = h("div", { class: "bar-label" }, statement.ranked ? h("span", { class: "rank" }, "#" + r.Rank) : null, r.Member);
    const bar = h("div", { class: "bar" + (altRule && altRule(r) ? " alt" : ""), style: `width:${(r.Value / max) * 100}%` });
    box.append(withTip(h("div", { class: "bar-row" }, label, h("div", { class: "bar-track" }, bar),
      h("div", { class: "bar-val" }, fmt(r.Value, statement.measure))),
      () => [statement.ranked ? `#${r.Rank} ` : "", r.Member + ": ", h("b", null, fmt(r.Value, statement.measure))]));
  }
  return box;
}

function resultTable(statement, rows) {
  const head = h("tr", null, statement.ranked ? h("th", { class: "num" }, "Rank") : null,
    h("th", null, "Member"), h("th", { class: "num" }, statement.measure));
  const body = rows.map(r => h("tr", null, statement.ranked ? h("td", { class: "num" }, r.Rank) : null,
    h("td", null, r.Member), h("td", { class: "num" }, fmt(r.Value, statement.measure))));
  return h("div", { class: "table-wrap" }, h("table", null, h("thead", null, head), h("tbody", null, body)));
}

function resultBlock(statement, altRule, legend) {
  return h("div", null, legend || null, barChart(statement, altRule),
    h("details", null, h("summary", null, `Table view (${statement.rows.length} rows)`), resultTable(statement, statement.rows)));
}

/* ---------- Overview ---------- */
async function overviewPage() {
  setNav("overview");
  const [o, p, prof, monthly, list] = await Promise.all([api("/api/overview"), api("/api/project"), api("/api/profile"),
    api("/api/analyses/02_roll_up_1"), api("/api/analyses")]);
  const share = Math.round((o.stopover_segments / o.segments) * 100);
  const groups = new Map();
  for (const a of list.analyses) groups.set(a.group, (groups.get(a.group) || 0) + 1);
  const initials = name => name.split(/\s+/).map(w => w[0]).slice(0, 2).join("");

  show(
    pageHead(`Group ${p.group} · ${p.course.replace(/\s*\(.*\)\s*$/, "")}`, "Flight data warehouse",
      "A star schema of airline ticket segments in SQL Server, an OLAP cube in Analysis Services, and 28 MDX analyses " +
      "of it. Every number on this site is read from the project's saved results, so it also works with the cube switched off.",
      matchBadge(o.match), p.report.available ? h("a", { class: "badge plain", href: "#/report" },
        `Report: ${p.report.pages ? p.report.pages + " pages" : "PDF"}`) : null),
    h("div", { class: "kpis" },
      kpi(n(o.segments), "flight segments (fact rows)", "none removed in preprocessing"),
      kpi(n(o.passengers), "distinct passengers"),
      kpi(n(o.stopover_segments), "segments with a stopover", `${share}% of all segments`),
      kpi(n(o.total_revenue), "total ticket revenue (yuan)", `${n(o.total_mileage)} km flown`),
      kpi(`${o.match.matched}/${o.match.total}`, "MDX results verified", "against independent T-SQL", true)),
    h("div", { class: "grid main-side" },
      card("Ticket revenue by departure month, 2021",
        h("a", { class: "small", href: "#/analysis/02_roll_up_1" }, "Statement 02_roll_up_1 →"),
        columnChart(monthly.rows, monthly.measure),
        h("p", { class: "muted small" }, "Roll up from days to months. Highest and lowest month labelled; hover a column for its value."),
        h("details", null, h("summary", null, "Table view (8 months)"), resultTable(monthly, monthly.rows))),
      card("How it was built", null,
        h("ol", { class: "steps" },
          h("li", null, h("div", null, h("b", null, "Source data"), h("span", null, `${n(o.segments)} ticket segments and 8 dimension tables from the course files`))),
          h("li", null, h("div", null, h("b", null, "Preprocessing"), h("span", null,
            `guide #2 checks: ${prof.passed_before} of ${prof.rules.length} passed before, ${prof.passed_after} of ${prof.rules.length} after`))),
          h("li", null, h("div", null, h("b", null, "Star schema"), h("span", null, "SQL Server: one fact table, eight dimensions"))),
          h("li", null, h("div", null, h("b", null, "Load"), h("span", null, "one SSIS package runs the scripts and checks"))),
          h("li", null, h("div", null, h("b", null, "OLAP cube"), h("span", null, "Analysis Services, role-playing date and airport dimensions"))),
          h("li", null, h("div", null, h("b", null, "Analyses"), h("span", null, `${list.analyses.length} MDX statements over ${groups.size} operations`))),
          h("li", null, h("div", null, h("b", null, "Report"), h("span", null, p.report.pages ? `${p.report.pages} pages, due ${p.date}` : `due ${p.date}`)))),
        h("details", null, h("summary", null, "Show the SSIS package"),
          h("figure", { class: "figure" }, h("img", { src: url("/api/figure/ssis"), alt: "SSIS package LoadFlightDW: its tasks in order", loading: "lazy" }),
            h("figcaption", null, "Control flow of the SSIS package that loads the warehouse."))))),
    h("div", { class: "grid main-side" },
      card("Star schema", h("a", { class: "small", href: "#/data" }, "Data and preprocessing →"),
        h("figure", { class: "figure" },
          h("img", { src: url("/api/figure/star-schema"), alt: "Star schema: Fact_FlightSegment with eight dimension tables" }),
          h("figcaption", null, `One fact table and eight dimensions; ${n(o.airports)} airports (${n(o.airports_used)} used), ` +
            `${n(o.airlines)} airlines, ${n(o.aircraft)} aircraft, ${n(o.dates)} dates.`))),
      card("Team", null,
        h("ul", { class: "team" }, p.members.map(m => h("li", null, h("span", { class: "avatar", "aria-hidden": "true" }, initials(m.name)),
          h("div", null, m.name, h("small", null, m.leader ? "Group leader" : "Group member"))))),
        h("p", { class: "muted small" }, `Group ${p.group} · Teacher: ${p.teacher}`),
        h("div", { class: "row-gap" }, h("a", { class: "btn", href: "#/analyses" }, "Browse the analyses"),
          h("a", { class: "btn ghost", href: "#/report" }, "Report and requirements")))),
    h("section", { class: "block" },
      h("div", { class: "section-title" }, h("h2", null, "Analyses by OLAP operation"), h("span", { class: "muted small" }, `${list.analyses.length} statements`)),
      h("div", { class: "ops" }, [...groups].map(([g, count]) =>
        h("a", { class: "op", href: "#/analyses?op=" + encodeURIComponent(g) }, h("b", null, g), h("span", null, `${count} statements`))))));
}

/* ---------- Data and preprocessing ---------- */
const ruleName = r => r.replace(/_ge_/g, " ≥ ").replace(/_ne_/g, " ≠ ").replace(/_/g, " ");
const passBadge = v => h("span", { class: "badge " + (v === "PASS" ? "good" : "bad") }, v === "PASS" ? "✓ Pass" : "✗ Fail");

async function dataPage() {
  setNav("data");
  const [p, o] = await Promise.all([api("/api/profile"), api("/api/overview")]);
  const count = name => p.counts.find(c => c.measure.toLowerCase().startsWith(name)) || { before: "?", after: "?" };
  const pick = [["distinct departure airports", "departure airports"], ["rows with a stopover", "rows with a stopover"],
    ["distinct airlines", "airlines"], ["distinct planes", "aircraft (PlaneID)"]];
  show(
    pageHead("Requirements analysis and preprocessing", "Data and preprocessing",
      `The course fact table (${n(o.segments)} ticket segments) failed most of the rules of guide #2 as delivered. Preprocessing ` +
      "added airports, stopovers, dates, airlines and aircraft by documented rules until every check passed; no fact row was removed."),
    h("div", { class: "kpis" },
      kpi(`${p.passed_before} / ${p.rules.length}`, "guide #2 checks passed before"),
      kpi(`${p.passed_after} / ${p.rules.length}`, "checks passed after preprocessing", null, true),
      pick.map(([key, lab]) => { const c = count(key); return kpi(`${c.before} → ${c.after}`, lab); })),
    card("Guide #2 checks, before and after", h("span", { class: "muted small" }, p.source === "data" ? "From the preprocessing profile" : "From the saved profile snapshot"),
      h("div", { class: "table-wrap" }, h("table", null,
        h("thead", null, h("tr", null, h("th", null, "Rule"), h("th", null, "Before"), h("th", null, "After"), h("th", null, "Detail after preprocessing"))),
        h("tbody", null, p.rules.map(r => h("tr", null,
          h("td", null, ruleName(r.rule)), h("td", null, passBadge(r.before)), h("td", null, passBadge(r.after)),
          h("td", null, r.detail_after, r.before !== r.after ? h("div", { class: "muted small" }, "before: " + r.detail_before) : null))))))),
    h("div", { class: "grid two" },
      card("Counts before and after", null, h("div", { class: "table-wrap" }, h("table", null,
        h("thead", null, h("tr", null, h("th", null, "Measure"), h("th", { class: "num" }, "Before"), h("th", { class: "num" }, "After"))),
        h("tbody", null, p.counts.map(c => h("tr", null, h("td", null, c.measure), h("td", { class: "num" }, c.before), h("td", { class: "num" }, c.after))))))),
      card("What the warehouse holds", null,
        h("ul", { class: "steps" },
          h("li", null, h("div", null, h("b", null, "Fact_FlightSegment"), h("span", null, `${n(o.segments)} rows: one per flight segment of a ticket`))),
          h("li", null, h("div", null, h("b", null, "Airports"), h("span", null, `${n(o.airports)} airports, ${n(o.airports_used)} used as departure, landing or transit`))),
          h("li", null, h("div", null, h("b", null, "Dates"), h("span", null, `${n(o.dates)} days of 2021; flights span 8 months`))),
          h("li", null, h("div", null, h("b", null, "Passengers"), h("span", null, `${n(o.passengers)} distinct passengers in the fact`))),
          h("li", null, h("div", null, h("b", null, "Airlines and aircraft"), h("span", null, `${n(o.airlines)} airlines, ${n(o.aircraft)} aircraft`)))),
        h("p", { class: "muted small" }, "Stopover landing and take-off times are not modelled, as the course guide asks."))));
}

/* ---------- Analyses list ---------- */
async function analysesPage(query) {
  setNav("analyses");
  const { analyses, match } = await api("/api/analyses");
  const groups = [...new Set(analyses.map(a => a.group))];
  let op = groups.includes(query.get("op")) ? query.get("op") : "";
  const search = h("input", { class: "search", type: "search", placeholder: "Search a question, e.g. airline, price, month",
    "aria-label": "Search analyses", value: query.get("q") || "" });
  const chips = h("div", { class: "chips", role: "group", "aria-label": "Filter by operation" });
  const list = h("div");
  const drawChips = () => chips.replaceChildren(
    ...["", ...groups].map(g => h("button", { class: "chip", type: "button", "aria-pressed": String(g === op),
      onclick: () => { op = g; drawChips(); draw(); } },
      g || "All", h("span", { class: "n" }, String(g ? analyses.filter(a => a.group === g).length : analyses.length)))));
  const draw = () => {
    const q = search.value.trim().toLowerCase();
    const params = new URLSearchParams();
    if (op) params.set("op", op);
    if (q) params.set("q", q);
    history.replaceState(null, "", "#/analyses" + (params.toString() ? "?" + params : ""));
    const byGroup = new Map();
    for (const a of analyses) {
      if (op && a.group !== op) continue;
      if (q && !(a.question + " " + a.operation + " " + a.measure + " " + a.stem).toLowerCase().includes(q)) continue;
      if (!byGroup.has(a.group)) byGroup.set(a.group, []);
      byGroup.get(a.group).push(a);
    }
    if (byGroup.size === 0) { list.replaceChildren(h("p", { class: "muted" }, "No analysis matches your search.")); return; }
    list.replaceChildren(...[...byGroup].map(([group, items]) => h("section", null,
      h("div", { class: "group-head" }, h("h2", null, group), h("span", { class: "muted small" }, `${items.length} statements`)),
      h("div", { class: "cards" }, items.map(a => h("a", { class: "acard", href: "#/analysis/" + a.stem },
        h("div", { class: "top-line" }, stem(a.stem), h("span", null, `${a.row_count} rows`)),
        h("div", { class: "q" }, a.question),
        h("div", { class: "meta" }, `${a.operation} · ${a.measure}`)))))));
  };
  search.addEventListener("input", draw);
  drawChips();
  draw();
  show(pageHead("OLAP analysis with MDX", "Analyses",
    `Eight OLAP operations with three statements each, plus four stopover statements: ${analyses.length} in all. ` +
    "Open one to see its result, its SSMS screenshot and its MDX.", matchBadge(match)), search, chips, list);
}

/* ---------- One analysis ---------- */
function livePanel(stemName) {
  if (STATIC) return card("Run it live", null, h("p", { class: "muted small" },
    "This hosted copy shows the saved results. Re-running a statement on the cube needs the local version of the site " +
    "(python web/server.py) on a computer with the Analysis Services cube."));
  const out = h("div");
  const btn = h("button", { class: "btn ghost", type: "button" }, "Run live on the cube");
  btn.addEventListener("click", async () => {
    btn.disabled = true; btn.textContent = "Running on the cube…";
    out.replaceChildren();
    try {
      const r = await api("/api/live/" + encodeURIComponent(stemName), { method: "POST" });
      if (!r.ok) {
        out.replaceChildren(h("div", { class: "live-msg warn" }, r.error));
      } else {
        const same = r.matches_saved;
        const statement = await api("/api/analyses/" + encodeURIComponent(stemName));
        out.replaceChildren(
          h("div", { class: "live-msg " + (same ? "good" : "warn") },
            same ? `✓ The cube returned the same ${r.rows.length} rows as the saved result (${r.seconds} s).`
                 : "The live result differs from the saved result: " + r.differences.slice(0, 3).join("; ")),
          h("details", { open: true }, h("summary", null, "Live result"), resultTable({ ...statement, rows: r.rows }, r.rows)));
      }
    } catch (e) {
      out.replaceChildren(h("div", { class: "live-msg warn" }, "The website server could not be reached: " + e.message));
    } finally { btn.disabled = false; btn.textContent = "Run live on the cube"; }
  });
  return card("Run it live", null,
    h("p", { class: "muted small" }, "Sends this stored statement to the Analysis Services cube and compares the answer with the saved result. " +
      "It needs the cube to be running; the saved result stays unchanged."), btn, out);
}

function copyButton(text) {
  const btn = h("button", { class: "btn ghost small", type: "button" }, "Copy MDX");
  btn.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(text); btn.textContent = "Copied ✓"; }
    catch { btn.textContent = "Select the text to copy"; }
    setTimeout(() => { btn.textContent = "Copy MDX"; }, 1800);
  });
  return btn;
}

async function analysisPage(stemName) {
  setNav("analyses");
  const [s, { analyses }] = await Promise.all([api("/api/analyses/" + encodeURIComponent(stemName)), api("/api/analyses")]);
  const i = analyses.findIndex(a => a.stem === s.stem);
  const prev = analyses[i - 1], next = analyses[i + 1];
  const ok = s.match && s.match.matched === s.match.total;
  show(
    h("p", { class: "crumbs" }, h("a", { href: "#/analyses" }, "← All analyses"), h("span", { class: "arrow" }, "/"),
      h("a", { href: "#/analyses?op=" + encodeURIComponent(s.group) }, s.group)),
    pageHead(s.group, s.question, null,
      h("span", { class: "badge plain" }, "Operation: ", s.operation), h("span", { class: "badge plain" }, "Measure: ", s.measure),
      h("span", { class: "badge plain" }, stem(s.stem)), ok ? h("span", { class: "badge good" }, "✓ Matches its T-SQL answer key") : null),
    h("div", { class: "grid side-main" },
      card("Result", h("span", { class: "muted small" }, `${s.rows.length} rows`), resultBlock(s)),
      card("Run in SQL Server Management Studio", h("a", { class: "small", href: url("/api/screenshot/" + s.stem), target: "_blank", rel: "noopener" }, "Full size ↗"),
        h("a", { class: "shot", href: url("/api/screenshot/" + s.stem), target: "_blank", rel: "noopener" },
          h("img", { src: url("/api/screenshot/" + s.stem), alt: `SSMS window with the MDX of ${s.stem} and its result`, loading: "lazy" })),
        h("p", { class: "muted small" }, "The statement run on the cube; the same screenshot is in the report, section 3.3. " +
          "SSMS rounds values with the cube's number format; the result on the left is exact."))),
    card("MDX statement", copyButton(s.mdx), h("pre", null, s.mdx),
      h("details", null, h("summary", null, "T-SQL answer key (" + s.answer_key_path + ")"), h("pre", null, s.answer_sql))),
    h("div", { class: "grid" }, livePanel(s.stem)),
    h("nav", { class: "pager", "aria-label": "Previous and next analysis" },
      prev ? h("a", { href: "#/analysis/" + prev.stem }, h("small", null, "← Previous · " + prev.stem), h("span", { class: "pq" }, prev.question)) : null,
      next ? h("a", { class: "next", href: "#/analysis/" + next.stem }, h("small", null, next.stem + " · Next →"), h("span", { class: "pq" }, next.question)) : null));
}

/* ---------- Stopovers ---------- */
async function stopoverPage() {
  setNav("stopover");
  const stems = ["09_stopover_1", "09_stopover_2", "09_stopover_3", "09_stopover_4"];
  const [hubs, price, share, routes] = await Promise.all(stems.map(x => api("/api/analyses/" + x)));
  const panel = (s, altRule, legend) => card(s.question,
    h("a", { class: "small", href: "#/analysis/" + s.stem }, "Open with the MDX →"),
    h("div", { class: "kv" }, h("span", { class: "badge plain" }, "Measure: ", s.measure), h("span", { class: "badge plain" }, stem(s.stem))),
    resultBlock(s, altRule, legend));
  show(
    pageHead("Stopover analysis", "Stopovers", "How segments with a stopover differ from direct ones, using the transit-airport role of the airport dimension."),
    h("div", { class: "note" }, h("b", null, "Read with care. "),
      "Stopovers exist only on routes of at least 900 km, so a higher price on stopover segments mixes the effect of " +
      "distance with the effect of the stopover. The data hold no ground time at the stopover."),
    h("div", { class: "grid two" },
      panel(price, r => r.Member === "With stopover",
        h("div", { class: "legend" }, h("span", null, h("i", { class: "dot" }), "No stopover"),
          h("span", null, h("i", { class: "dot alt" }), "With stopover"))),
      panel(hubs)),
    h("div", { class: "grid two" }, panel(share), panel(routes)));
}

/* ---------- Report and requirements ---------- */
const CONTENTS = [["1", "Cover page"], ["2", "Motivation and purpose"], ["3.1", "Requirements, data set and preprocessing"],
  ["3.2", "Logical and physical design"], ["3.3", "Functions: OLAP analysis with MDX"], ["4", "Problems and solutions (one part per member)"],
  ["5", "Lessons and experience (one part per member)"], ["6", "References"], ["A", "Warehouse creation statements"],
  ["B", "Complete MDX statements"]];

async function reportPage() {
  setNav("report");
  const [p, r] = await Promise.all([api("/api/project"), api("/api/requirements")]);
  show(
    pageHead("Course project report", "Report and requirements",
      "The written report, and every requirement of the course guides with where the project meets it."),
    h("div", { class: "grid side-main" },
      card(p.project, null,
        h("div", { class: "kv" }, h("span", { class: "badge plain" }, `Group ${p.group}`), h("span", { class: "badge plain" }, p.teacher),
          h("span", { class: "badge plain" }, `Due ${p.date}`), p.report.pages ? h("span", { class: "badge plain" }, `${p.report.pages} pages`) : null),
        h("p", { class: "muted small" }, p.course),
        h("p", { class: "small" }, p.members.map(m => m.name + (m.leader ? " (group leader)" : "")).join(" · ")),
        p.report.available
          ? h("div", { class: "row-gap" }, h("a", { class: "btn", href: url("/report.pdf"), target: "_blank", rel: "noopener" }, "Open the report (PDF) ↗"))
          : h("p", { class: "note" }, "The report PDF is not on this computer. Build it with python tools/build_report.py and export it from Word."),
        h("h3", { style: "margin-top:18px" }, "Contents"),
        h("ul", { class: "toc" }, CONTENTS.map(([no, title]) => h("li", null, h("b", null, no), title)))),
      card("The teacher's requirements", h("span", { class: "badge good" }, `✓ ${r.items.length} of ${r.items.length} met`),
        h("ul", { class: "checklist" }, r.items.map(it => h("li", { class: "check" },
          h("span", { class: "tick", "aria-label": "met" }, "✓"),
          h("div", null, h("div", { class: "src" }, it.source), h("div", { class: "req" }, it.requirement), h("div", { class: "ev" }, it.evidence)),
          it.link === "#/report"
            ? (p.report.available ? h("a", { href: url("/report.pdf"), target: "_blank", rel: "noopener" }, "In the report ↗") : null)
            : h("a", { href: it.link }, "See it →")))))));
}

/* ---------- router ---------- */
async function route() {
  routeNo += 1;
  const raw = location.hash.replace(/^#/, "") || "/";
  const [path, qs] = raw.split("?");
  const query = new URLSearchParams(qs || "");
  try {
    if (path === "/") await overviewPage();
    else if (path === "/data") await dataPage();
    else if (path === "/analyses") await analysesPage(query);
    else if (path === "/stopover") await stopoverPage();
    else if (path === "/report") await reportPage();
    else if (path.startsWith("/analysis/")) await analysisPage(decodeURIComponent(path.slice("/analysis/".length)));
    else show(pageHead(null, "Page not found", null), h("p", null, h("a", { href: "#/" }, "Back to the overview")));
  } catch (e) {
    if (e instanceof StalePage) return;
    show(pageHead(null, "Something went wrong", "The page could not load its data (" + e.message + "). Is the server still running?"),
      h("p", null, h("a", { href: "#/" }, "Back to the overview")));
  }
}
window.addEventListener("hashchange", route);
route();
