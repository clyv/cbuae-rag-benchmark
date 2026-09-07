#!/usr/bin/env python3
"""Build the shareable demo page from results/demo.json.

    python scripts/build_demo_page.py [output.html]
    python scripts/build_demo_page.py --public       # -> docs/index.html

## Two builds, because the licence is not the same for both

The default build quotes short excerpts of each cited article. That is fine for
a private link and for a container running on one machine, and it is what makes
the page immediately legible.

`--public` builds the version that goes on a public website. It carries no
CBUAE text at all. SOURCES.md records that the terms permit download for
non-commercial use and prohibit onward publication (clause 2.5), while direct
links to pages are expressly permitted (disclaimer 1.2). A public page of
excerpts would be republication; a public page of identifiers and links is not.

What replaces the excerpt is better for the demo's actual purpose anyway: the
labeller's own note on *why* that article answers the question. That is original
commentary, it is the part a reader cannot get by clicking through, and showing
it turns each answer into a visible piece of the benchmark rather than a snippet
of regulation.

The page carries the system's recorded output for all 100 benchmark questions:
real citations, real scores, and each question's labelled evidence so a reader
can see whether the system found what a human said was required.

The abstention threshold is computed in the browser from each question's stored
score, rather than baked in. That matters: the interesting result is the
trade-off, and a page that fixes one threshold shows a verdict where the honest
answer is a curve. Moving the control shows what refusing more costs.

## Theme

Palette and typefaces are direction D, Oxblood, from the HireHouse theme
directions - muted oxblood on parchment set in Literata, described there as
institutional in the old sense: universities, law firms, records that matter.
Both light and dark values are taken from that source rather than derived.

Theme resolution has three states, and a manual toggle sits on top of them.
Bare :root carries the light palette; the prefers-color-scheme block applies the
dark one only when the reader has not explicitly chosen light; and .dark applies
it when they have chosen dark. With no stored choice the page follows the host,
including when the host changes it mid-session.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "results" / "demo.json"
BENCHMARK = REPO_ROOT / "benchmark" / "questions.jsonl"

# Direction D - Oxblood. Light and dark values both from the theme source.
LIGHT = """
  --primary:#7b2e36; --on-primary:#ffffff;
  --ink:#1f1416; --body:#4e4143; --muted:#8b7e80;
  --canvas:#faf6f2; --surface:#ffffff; --raise:#fcf9f6; --hairline:#ede4de;
  --pi-bg:#f3eaea; --pi-fg:#7b2e36;
  --po-bg:#e8efe6; --po-fg:#3f5f42;
  --pw-bg:#f8eede; --pw-fg:#8a6015;
"""

DARK = """
  --primary:#dd9195; --on-primary:#2a1214;
  --ink:#f3eae7; --body:#c8b9b6; --muted:#8e7f7d;
  --canvas:#16100f; --surface:#20181a; --raise:#271e20; --hairline:rgba(255,255,255,.09);
  --pi-bg:rgba(221,145,149,.16); --pi-fg:#e5aaad;
  --po-bg:rgba(143,180,144,.16); --po-fg:#a6c4a7;
  --pw-bg:rgba(219,176,105,.16); --pw-fg:#e2c088;
"""

HEAD = """<title>ReguLens</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Literata:opsz,wght@7..72,400;7..72,500;7..72,600&family=Work+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{__LIGHT__
  --f-display:Literata,Georgia,"Times New Roman",serif;
  --f-ui:"Work Sans",ui-sans-serif,system-ui,-apple-system,sans-serif;
  --f-mono:"IBM Plex Mono",ui-monospace,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root:not(.light){__DARK__}}
:root.dark{__DARK__}

*{box-sizing:border-box}
body{margin:0;background:var(--canvas);color:var(--body);font-family:var(--f-ui);
  font-size:16px;line-height:1.62;-webkit-font-smoothing:antialiased}
.wrap{max-width:70rem;margin:0 auto;padding:clamp(1.5rem,4vw,3.25rem) clamp(1rem,3vw,2.5rem) 4rem;
  display:grid;gap:2.5rem}

.top{display:flex;justify-content:space-between;align-items:flex-start;gap:1.5rem;flex-wrap:wrap}
.eyebrow{font-family:var(--f-mono);font-size:.68rem;letter-spacing:.14em;
  text-transform:uppercase;color:var(--primary)}
h1{font-family:var(--f-display);font-weight:500;letter-spacing:-.015em;
  font-size:clamp(2rem,5vw,2.9rem);line-height:1.06;margin:.45rem 0 .6rem;color:var(--ink)}
h2{font-family:var(--f-display);font-weight:500;letter-spacing:-.015em;
  font-size:1.4rem;line-height:1.22;margin:0 0 .35rem;color:var(--ink);text-wrap:balance}
.lede{font-family:var(--f-display);font-weight:400;font-size:1.1rem;line-height:1.5;
  color:var(--body);margin:0;max-width:56ch}
p{margin:0 0 .85rem}p:last-child{margin-bottom:0}
.note{font-size:.86rem;color:var(--muted);max-width:64ch}
a{color:var(--primary);text-underline-offset:2px}
:focus-visible{outline:2px solid var(--primary);outline-offset:2px}

/* theme toggle */
.themebtn{display:inline-flex;align-items:center;gap:.45rem;flex:0 0 auto;
  font-family:var(--f-mono);font-size:.7rem;letter-spacing:.08em;text-transform:uppercase;
  padding:.4rem .7rem;border:1px solid var(--hairline);border-radius:2px;
  background:var(--surface);color:var(--muted);cursor:pointer}
.themebtn:hover{color:var(--ink);border-color:var(--primary)}
.themebtn svg{width:13px;height:13px;display:block}

/* demo */
.demo{display:grid;grid-template-columns:minmax(0,20rem) minmax(0,1fr);gap:1px;
  background:var(--hairline);border:1px solid var(--hairline);border-radius:3px;overflow:hidden}
@media(max-width:52rem){.demo{grid-template-columns:1fr}}
.pane{background:var(--surface);min-width:0}
.picker{display:flex;flex-direction:column;max-height:34rem}
.filters{padding:.7rem;border-bottom:1px solid var(--hairline);display:flex;gap:.3rem;flex-wrap:wrap}
.chip{font-family:var(--f-mono);font-size:.67rem;padding:.22rem .5rem;border-radius:2px;
  border:1px solid var(--hairline);background:transparent;color:var(--muted);cursor:pointer}
.chip:hover{color:var(--ink)}
.chip[aria-pressed="true"]{background:var(--primary);border-color:var(--primary);color:var(--on-primary)}
.qlist{overflow-y:auto;flex:1}
.q{display:block;width:100%;text-align:left;border:0;border-bottom:1px solid var(--hairline);
  background:transparent;color:var(--body);font:inherit;font-size:.85rem;line-height:1.4;
  padding:.7rem .85rem;cursor:pointer}
.q:hover{background:var(--raise);color:var(--ink)}
.q[aria-current="true"]{background:var(--pi-bg);color:var(--ink);box-shadow:inset 2px 0 0 var(--primary)}
.q .qid{font-family:var(--f-mono);font-size:.67rem;color:var(--muted);display:block}
.answer{padding:1.25rem}
.qtext{font-family:var(--f-display);font-size:1.15rem;line-height:1.4;margin:0 0 .3rem;color:var(--ink)}
.meta{font-family:var(--f-mono);font-size:.71rem;color:var(--muted);
  display:flex;gap:.9rem;flex-wrap:wrap;margin-bottom:1rem}
.verdict{font-family:var(--f-mono);font-size:.7rem;padding:.16rem .5rem;border-radius:2px}
.v-yes{background:var(--po-bg);color:var(--po-fg)}
.v-no{background:var(--pw-bg);color:var(--pw-fg)}
.cite{border:1px solid var(--hairline);border-left:2px solid var(--hairline);
  border-radius:0 3px 3px 0;padding:.7rem .85rem;margin-bottom:.6rem;background:var(--raise)}
.cite.req{border-left-color:var(--primary)}
.cite h4{font-family:var(--f-mono);font-size:.77rem;margin:0 0 .1rem;font-weight:500;color:var(--ink)}
.cite .doc{font-size:.75rem;color:var(--muted);margin:0 0 .45rem}
.cite .ex{font-size:.85rem;margin:0 0 .5rem;color:var(--body)}
.cite .why{font-size:.85rem;margin:0 0 .5rem;color:var(--body);border-left:2px solid var(--primary);
  padding-left:.6rem}
.cite .why b{color:var(--primary);font-weight:600}
.cite .nolink{font-size:.8rem;margin:0 0 .5rem;color:var(--muted);font-style:italic}
.cite .foot{display:flex;justify-content:space-between;align-items:center;gap:.75rem;
  font-family:var(--f-mono);font-size:.69rem;flex-wrap:wrap}
.cite .sc{color:var(--muted)}
.declined{background:var(--pw-bg);border:1px solid var(--hairline);border-radius:3px;
  padding:.9rem 1rem;font-size:.9rem;color:var(--pw-fg)}

/* threshold */
.control{background:var(--surface);border:1px solid var(--hairline);border-radius:3px;
  padding:1rem 1.15rem;display:grid;gap:.6rem}
.control .row{display:flex;align-items:center;gap:.9rem;flex-wrap:wrap}
.control input[type=range]{flex:1 1 14rem;accent-color:var(--primary);min-width:10rem}
.tally{font-family:var(--f-mono);font-size:.78rem;color:var(--body);
  display:flex;gap:1.25rem;flex-wrap:wrap;font-variant-numeric:tabular-nums}
.tally b{font-weight:500;color:var(--ink)}
label{font-family:var(--f-mono);font-size:.71rem;letter-spacing:.06em;
  text-transform:uppercase;color:var(--muted)}

/* stats */
.scroll{overflow-x:auto;border:1px solid var(--hairline);border-radius:3px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:.85rem}
th,td{padding:.55rem .95rem;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
thead th{font-weight:500;font-size:.69rem;letter-spacing:.06em;text-transform:uppercase;
  color:var(--muted);border-bottom:1px solid var(--hairline)}
tbody td{color:var(--body)}
tbody tr+tr td{border-top:1px solid var(--hairline)}
td.n{font-family:var(--f-mono);font-variant-numeric:tabular-nums}
tr.lead td{font-weight:600;color:var(--ink)}
tr.lead td:first-child{box-shadow:inset 2px 0 0 var(--primary)}
footer{border-top:1px solid var(--hairline);padding-top:1.25rem;font-size:.8rem;
  color:var(--muted);max-width:64ch}
footer strong{color:var(--body)}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>
"""

BODY_TOP = """<div class="wrap">
<header>
  <div class="top">
    <div>
      <div class="eyebrow">Retrieval over CBUAE insurance regulation</div>
      <h1>ReguLens</h1>
    </div>
    <button class="themebtn" id="themebtn" type="button" aria-live="polite">
      <span id="themeicon"></span><span id="themelabel">Theme</span>
    </button>
  </div>
  <p class="lede">__LEDE__</p>
</header>

<section>
  <h2>Try it</h2>
  <p class="note">These are the 100 benchmark questions. Everything below is what the system
  actually returned when run over the corpus &mdash; real citations, real relevance scores,
  nothing mocked up. Because each question has labelled evidence, you can also see whether
  it found what a human said was required.</p>
  <div class="demo">
    <div class="pane picker">
      <div class="filters" id="filters"></div>
      <div class="qlist" id="qlist"></div>
    </div>
    <div class="pane answer" id="answer"></div>
  </div>
  <p class="note"><strong>Why quotes and not prose?</strong> Because a quote cannot say
  something its source does not. The same pipeline was run through a local generative model
  to measure what paraphrasing costs: it declined 69 of the 100 questions, and of the claims
  it did write, only <strong>0.557</strong> could be traced back to the section it cited,
  against <strong>0.972</strong> when it quotes instead. That is a small model and the
  figure is a floor, not a verdict on generation &mdash; but it is why the default here
  quotes.</p>
__EXCERPT_NOTE__
</section>

<section>
  <h2>When should it refuse to answer?</h2>
  <p class="note">Fourteen questions have no answer in this corpus. A system that answers them
  anyway is confidently wrong. Declining below a relevance score is the obvious fix &mdash;
  move the control and watch what it costs.</p>
  <div class="control">
    <div class="row">
      <label for="thr">Decline below</label>
      <input id="thr" type="range" min="-10" max="7" step="0.25" value="-10">
      <span id="thrval" style="font-family:var(--f-mono);font-variant-numeric:tabular-nums;color:var(--ink)">off</span>
    </div>
    <div class="tally" id="tally"></div>
  </div>
  <p class="note" id="thrnote"></p>
</section>
"""

BODY_BOTTOM = """
<section>
  <h2>How the four systems compare</h2>
  <div class="scroll"><table>
    <thead><tr><th>System</th><th>recall@10</th><th>full recall@10</th><th>MRR</th><th>median latency</th></tr></thead>
    <tbody>
      <tr><td>BM25</td><td class="n">0.581</td><td class="n">0.465</td><td class="n">0.448</td><td class="n">4 ms</td></tr>
      <tr><td>Dense</td><td class="n">0.680</td><td class="n">0.523</td><td class="n">0.579</td><td class="n">44 ms</td></tr>
      <tr><td>Hybrid</td><td class="n">0.686</td><td class="n">0.547</td><td class="n">0.558</td><td class="n">56 ms</td></tr>
      <tr class="lead"><td>Hybrid + reranker</td><td class="n">0.750</td><td class="n">0.593</td><td class="n">0.674</td><td class="n">1042 ms</td></tr>
    </tbody>
  </table></div>
  <p class="note">Measured over the 86 answerable questions, on CPU. The demo above uses the
  last row. <strong>Hybrid with reranking beats BM25 by +0.169</strong> (95% interval +0.087
  to +0.250) and dense by +0.070 &mdash; both clear zero. At 50 questions neither did: the
  systems and the code were identical, only the benchmark grew. On
  <strong>cross-document</strong> questions, where evidence spans two instruments, hybrid
  reaches 0.853 against BM25's 0.618.</p>
</section>

<footer>
  <p>__NOTICE__</p>
  <p>Corpus <strong>&copy; Central Bank of the UAE</strong>, used for non-commercial research
  under the CBUAE website terms. <strong>Not affiliated with, endorsed by, or connected to the
  Central Bank of the UAE.</strong> Nothing here is legal, regulatory or compliance advice.</p>
</footer>
</div>
"""

SCRIPT = """<script>
const DATA = __DATA__;
const Q = DATA.questions;
const CATS = [...new Set(Q.map(q => q.category))];
let cat = "all", current = Q[0], threshold = null;

const el = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

/* ---- theme ------------------------------------------------------------ */
const KEY = "regulens-theme";
const SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4.2"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4"/></svg>';
const MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.8 6.8 0 0 0 10.5 10.5z"/></svg>';

function stored() {
  try { return localStorage.getItem(KEY); } catch (e) { return null; }
}
function remember(v) {
  try { v ? localStorage.setItem(KEY, v) : localStorage.removeItem(KEY); } catch (e) {}
}
function hostPrefersDark() {
  const stamped = document.documentElement.getAttribute("data-theme");
  if (stamped === "dark") return true;
  if (stamped === "light") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}
function isDark() {
  const s = stored();
  return s ? s === "dark" : hostPrefersDark();
}
function paint() {
  const dark = isDark();
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.classList.toggle("light", !dark);
  el("themeicon").innerHTML = dark ? MOON : SUN;
  el("themelabel").textContent = dark ? "Dark" : "Light";
  el("themebtn").setAttribute("aria-label",
    dark ? "Switch to light mode" : "Switch to dark mode");
}
el("themebtn").addEventListener("click", () => {
  remember(isDark() ? "light" : "dark");
  paint();
});
// With no explicit choice, keep following the host if it changes mid-session.
window.matchMedia("(prefers-color-scheme: dark)")
  .addEventListener("change", () => { if (!stored()) paint(); });
new MutationObserver(() => { if (!stored()) paint(); })
  .observe(document.documentElement, {attributes: true, attributeFilter: ["data-theme"]});

/* ---- demo ------------------------------------------------------------- */
function renderFilters() {
  el("filters").innerHTML = ["all", ...CATS].map(c =>
    `<button class="chip" data-c="${esc(c)}" aria-pressed="${c === cat}">${esc(c.replace(/_/g, " "))}</button>`
  ).join("");
  el("filters").querySelectorAll(".chip").forEach(b =>
    b.onclick = () => { cat = b.dataset.c; renderFilters(); renderList(); });
}

function renderList() {
  const rows = Q.filter(q => cat === "all" || q.category === cat);
  el("qlist").innerHTML = rows.map(q =>
    `<button class="q" data-id="${q.id}" aria-current="${q.id === current.id}">
       <span class="qid">${q.id} &middot; ${esc(q.category.replace(/_/g, " "))}</span>
       ${esc(q.question)}
     </button>`).join("");
  el("qlist").querySelectorAll(".q").forEach(b =>
    b.onclick = () => { current = Q.find(x => x.id === b.dataset.id); renderList(); renderAnswer(); });
}

function declines(q) {
  return threshold !== null && q.top_score !== null && q.top_score <= threshold;
}

function renderAnswer() {
  const q = current;
  const unanswerable = q.required.length === 0;
  let head = `<p class="qtext">${esc(q.question)}</p><div class="meta">
    <span>${q.id}</span><span>${esc(q.category.replace(/_/g, " "))}</span>
    <span>top relevance ${q.top_score ?? "&mdash;"}</span></div>`;

  if (declines(q)) {
    el("answer").innerHTML = head + `<div class="declined"><strong>Declined.</strong>
      Nothing retrieved scored above ${threshold}, so the system does not answer.
      ${unanswerable
        ? "That is correct here &mdash; this question has no answer in the corpus."
        : "That is a mistake here &mdash; this question <em>is</em> answerable."}</div>`;
    return;
  }

  if (unanswerable) {
    head += `<div class="declined" style="margin-bottom:.9rem">This question has no answer in
      the corpus. With no threshold set the system answers anyway &mdash; the sections below
      are the closest it found, and none of them is right.</div>`;
  } else {
    const v = q.complete
      ? `<span class="verdict v-yes">found all ${q.required.length} required</span>`
      : `<span class="verdict v-no">found ${q.found.length} of ${q.required.length} required</span>`;
    head += `<div style="margin-bottom:.9rem">${v}</div>`;
  }

  el("answer").innerHTML = head + q.citations.map(c => `
    <div class="cite ${c.required ? "req" : ""}">
      <h4>${esc(c.doc_id)} &middot; ${esc(c.section)}</h4>
      <p class="doc">${esc(c.document)}</p>
      ${c.excerpt ? `<p class="ex">${esc(c.excerpt)}&hellip;</p>`
        : c.why ? `<p class="why"><b>Why this answers it:</b> ${esc(c.why)}</p>`
        : `<p class="nolink">Article text not reproduced here &mdash; open it at the source.</p>`}
      <div class="foot">
        <a href="${esc(c.url)}" target="_blank" rel="noopener noreferrer">Read at the CBUAE Rulebook &rarr;</a>
        <span class="sc">${c.required ? "required evidence &middot; " : ""}score ${c.score}</span>
      </div>
    </div>`).join("");
}

function renderTally() {
  const answerable = Q.filter(q => q.required.length > 0);
  const un = Q.filter(q => q.required.length === 0);
  const good = un.filter(declines).length;
  const bad = answerable.filter(declines).length;
  el("tally").innerHTML =
    `<span>unanswerable correctly declined <b>${good} / ${un.length}</b></span>
     <span>answerable wrongly declined <b>${bad} / ${answerable.length}</b></span>`;
  el("thrnote").textContent = threshold === null
    ? "With no threshold the system always answers, so it never refuses a question it could have answered — and never refuses one it should."
    : (bad === 0
        ? "No answerable question is refused yet, but most unanswerable ones still get an answer."
        : `Refusing ${good} of ${un.length} unanswerable questions costs ${bad} answerable ones. The distributions overlap, which is the finding: relevance alone cannot tell a question the corpus cannot answer from one it can.`);
}

el("thr").addEventListener("input", (e) => {
  const v = Number(e.target.value);
  threshold = v <= -10 ? null : v;
  el("thrval").textContent = threshold === null ? "off" : threshold.toFixed(2);
  renderTally(); renderAnswer();
});

paint(); renderFilters(); renderList(); renderAnswer(); renderTally();
</script>"""


PRIVATE_LEDE = (
    "Ask a regulatory question, get the exact articles that answer it &mdash; each one "
    "quoted, attributed and linked back to the source."
)

PUBLIC_LEDE = (
    "Ask a regulatory question, get the exact articles that answer it &mdash; each one "
    "identified, scored against a human-labelled answer key, and linked back to the source."
)

PRIVATE_NOTICE = (
    "Runs locally on CPU, no paid API keys. Source documents are not redistributed: the "
    "corpus is fetched at clone time, and this page shows short excerpts with links to the "
    "source rather than article text."
)

PUBLIC_NOTICE = (
    "Runs locally on CPU, no paid API keys. <strong>No CBUAE text is reproduced on this "
    "page.</strong> The corpus is fetched from the Rulebook at clone time and never "
    "redistributed; every citation here is an identifier and a direct link, which the CBUAE "
    "terms expressly permit."
)

PUBLIC_EXCERPT_NOTE = """  <p class="note"><strong>Why you cannot read the article text here.</strong>
  The CBUAE website terms permit downloading regulation for non-commercial use but not
  republishing it, and expressly permit direct links instead. So this public page shows which
  provision answers each question, how confident the system was, and whether it matched the
  labelled answer &mdash; then links you to the Central Bank's own page for the words. In place
  of the article text each required citation carries the labeller's note on <em>why</em> that
  provision answers the question, which is the part you cannot get by clicking through.</p>"""


def why_notes() -> dict[str, dict[str, str]]:
    """Each question's own note on why a required provision answers it.

    Written by the labeller, so it is this project's text and not the Rulebook's -
    which is exactly what makes it publishable where an excerpt is not.
    """
    notes: dict[str, dict[str, str]] = {}
    for line in BENCHMARK.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        notes[row["id"]] = {
            f"{e['doc_id']}::{e['section']}": e.get("why", "") for e in row["required_evidence"]
        }
    return notes


def make_public(data: dict) -> dict:
    """Strip every excerpt, and attach the labeller's notes in their place."""
    notes = why_notes()
    for question in data["questions"]:
        for citation in question["citations"]:
            citation.pop("excerpt", None)
            note = notes.get(question["id"], {}).get(citation["id"], "")
            if note:
                citation["why"] = note
    data["excerpt_cap"] = 0
    return data


def main() -> int:
    public = "--public" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--public"]

    if not DATA.exists():
        sys.exit(f"{DATA} not found. Run scripts/export_demo.py first.")
    data = json.loads(DATA.read_text(encoding="utf-8"))
    if public:
        data = make_public(data)
    payload = json.dumps(data, ensure_ascii=False)
    # A literal </script> inside the data would close the tag early.
    payload = payload.replace("</", "<\\/")

    head = HEAD.replace("__LIGHT__", LIGHT).replace("__DARK__", DARK)
    body = BODY_TOP.replace("__EXCERPT_NOTE__", PUBLIC_EXCERPT_NOTE if public else "")
    body = body.replace("__LEDE__", PUBLIC_LEDE if public else PRIVATE_LEDE)
    bottom = BODY_BOTTOM.replace("__NOTICE__", PUBLIC_NOTICE if public else PRIVATE_NOTICE)

    if args:
        out = Path(args[0])
    elif public:
        out = REPO_ROOT / "docs" / "index.html"
    else:
        out = REPO_ROOT / "results" / "demo.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        head + body + bottom + SCRIPT.replace("__DATA__", payload),
        encoding="utf-8",
    )
    # A public build that still carries article text would be the exact thing
    # SOURCES.md says is not permitted, so it is checked rather than trusted.
    if public and '"excerpt"' in out.read_text(encoding="utf-8"):
        sys.exit("refusing to ship: the public build still contains an excerpt field")

    label = "  [public: no CBUAE text]" if public else ""
    print(f"wrote {out}  ({out.stat().st_size / 1024:.0f} KB){label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
