#!/usr/bin/env python3
"""Build the shareable demo page from results/demo.json.

    python scripts/build_demo_page.py [output.html]

The page carries the system's recorded output for all 50 benchmark questions:
real citations, real scores, and each question's labelled evidence so a reader
can see whether the system found what a human said was required.

The abstention threshold is computed in the browser from each question's stored
score, rather than baked in. That matters: the interesting result is the
trade-off, and a page that fixes one threshold shows a verdict where the honest
answer is a curve. Moving the control shows what refusing more costs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "results" / "demo.json"

HEAD = """<title>ReguLens</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Spectral:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{
  --paper:#f6f7f9; --surface:#fff; --raise:#fbfcfd;
  --ink:#111820; --soft:#4a5561; --faint:#78838f; --rule:#dfe3e8;
  --accent:#1f6b66; --accent-dim:#e3efee; --on-accent:#ffffff;
  --yes:#2c6349; --yes-bg:#e6f0ea; --no:#8a6a1c; --no-bg:#f6eedb;
  --f-display:Spectral,"Iowan Old Style",Georgia,serif;
  --f-body:"IBM Plex Sans",ui-sans-serif,system-ui,-apple-system,sans-serif;
  --f-mono:"IBM Plex Mono",ui-monospace,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#0f141a; --surface:#161d25; --raise:#1b232c;
  --ink:#e6eaee; --soft:#a4b0bb; --faint:#74808c; --rule:#27313b;
  --accent:#5fb3ab; --accent-dim:#15292a; --on-accent:#0f141a;
  --yes:#74c49b; --yes-bg:#14251d; --no:#d5aa5c; --no-bg:#262015;
}}
:root[data-theme="dark"]{
  --paper:#0f141a; --surface:#161d25; --raise:#1b232c;
  --ink:#e6eaee; --soft:#a4b0bb; --faint:#74808c; --rule:#27313b;
  --accent:#5fb3ab; --accent-dim:#15292a; --on-accent:#0f141a;
  --yes:#74c49b; --yes-bg:#14251d; --no:#d5aa5c; --no-bg:#262015;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--f-body);
  font-size:16px;line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:70rem;margin:0 auto;padding:clamp(1.75rem,4vw,3.5rem) clamp(1rem,3vw,2.5rem) 4rem;
  display:grid;gap:2.5rem}
.eyebrow{font-family:var(--f-mono);font-size:.68rem;letter-spacing:.14em;
  text-transform:uppercase;color:var(--accent)}
h1{font-family:var(--f-display);font-weight:600;font-size:clamp(2rem,5vw,2.9rem);
  line-height:1.05;letter-spacing:-.02em;margin:.5rem 0 .6rem}
h2{font-family:var(--f-display);font-weight:600;font-size:1.4rem;line-height:1.2;
  margin:0 0 .35rem;text-wrap:balance}
.lede{font-family:var(--f-display);font-size:1.1rem;line-height:1.5;color:var(--soft);
  margin:0;max-width:56ch}
p{margin:0 0 .85rem}p:last-child{margin-bottom:0}
.note{font-size:.86rem;color:var(--faint);max-width:64ch}
a{color:var(--accent);text-underline-offset:2px}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* demo */
.demo{display:grid;grid-template-columns:minmax(0,20rem) minmax(0,1fr);gap:1px;
  background:var(--rule);border:1px solid var(--rule);border-radius:4px;overflow:hidden}
@media(max-width:52rem){.demo{grid-template-columns:1fr}}
.pane{background:var(--surface);min-width:0}
.picker{display:flex;flex-direction:column;max-height:34rem}
.filters{padding:.75rem;border-bottom:1px solid var(--rule);display:flex;gap:.3rem;flex-wrap:wrap}
.chip{font-family:var(--f-mono);font-size:.68rem;padding:.22rem .5rem;border-radius:2px;
  border:1px solid var(--rule);background:transparent;color:var(--faint);cursor:pointer}
.chip[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
.qlist{overflow-y:auto;flex:1}
.q{display:block;width:100%;text-align:left;border:0;border-bottom:1px solid var(--rule);
  background:transparent;color:var(--ink);font:inherit;font-size:.85rem;line-height:1.4;
  padding:.7rem .85rem;cursor:pointer}
.q:hover{background:var(--raise)}
.q[aria-current="true"]{background:var(--accent-dim);box-shadow:inset 2px 0 0 var(--accent)}
.q .qid{font-family:var(--f-mono);font-size:.68rem;color:var(--faint);display:block}
.answer{padding:1.25rem}
.qtext{font-family:var(--f-display);font-size:1.15rem;line-height:1.4;margin:0 0 .3rem}
.meta{font-family:var(--f-mono);font-size:.72rem;color:var(--faint);
  display:flex;gap:.9rem;flex-wrap:wrap;margin-bottom:1rem}
.verdict{font-family:var(--f-mono);font-size:.7rem;padding:.14rem .45rem;border-radius:2px}
.v-yes{background:var(--yes-bg);color:var(--yes)}
.v-no{background:var(--no-bg);color:var(--no)}
.cite{border:1px solid var(--rule);border-left:2px solid var(--rule);border-radius:0 3px 3px 0;
  padding:.7rem .85rem;margin-bottom:.6rem;background:var(--raise)}
.cite.req{border-left-color:var(--accent)}
.cite h4{font-family:var(--f-mono);font-size:.78rem;margin:0 0 .1rem;font-weight:500}
.cite .doc{font-size:.75rem;color:var(--faint);margin:0 0 .45rem}
.cite .ex{font-size:.85rem;margin:0 0 .5rem;color:var(--soft)}
.cite .foot{display:flex;justify-content:space-between;align-items:center;gap:.75rem;
  font-family:var(--f-mono);font-size:.7rem;flex-wrap:wrap}
.cite .sc{color:var(--faint)}
.declined{background:var(--no-bg);border:1px solid var(--rule);border-radius:3px;
  padding:.9rem 1rem;font-size:.9rem;color:var(--no)}

/* threshold */
.control{background:var(--surface);border:1px solid var(--rule);border-radius:4px;padding:1rem 1.15rem;
  display:grid;gap:.6rem}
.control .row{display:flex;align-items:center;gap:.9rem;flex-wrap:wrap}
.control input[type=range]{flex:1 1 14rem;accent-color:var(--accent);min-width:10rem}
.tally{font-family:var(--f-mono);font-size:.78rem;color:var(--soft);
  display:flex;gap:1.25rem;flex-wrap:wrap;font-variant-numeric:tabular-nums}
.tally b{font-weight:500;color:var(--ink)}
label{font-family:var(--f-mono);font-size:.72rem;letter-spacing:.06em;
  text-transform:uppercase;color:var(--faint)}

/* stats */
.scroll{overflow-x:auto;border:1px solid var(--rule);border-radius:4px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:.85rem}
th,td{padding:.55rem .95rem;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
thead th{font-weight:500;font-size:.7rem;letter-spacing:.06em;text-transform:uppercase;
  color:var(--faint);border-bottom:1px solid var(--rule)}
tbody tr+tr td{border-top:1px solid var(--rule)}
td.n{font-family:var(--f-mono);font-variant-numeric:tabular-nums}
tr.lead td{font-weight:600}
tr.lead td:first-child{box-shadow:inset 2px 0 0 var(--accent)}
footer{border-top:1px solid var(--rule);padding-top:1.25rem;font-size:.8rem;
  color:var(--faint);max-width:64ch}
footer strong{color:var(--soft)}
</style>
"""

BODY_TOP = """<div class="wrap">
<header>
  <div class="eyebrow">Retrieval over CBUAE insurance regulation</div>
  <h1>ReguLens</h1>
  <p class="lede">Ask a regulatory question, get the exact articles that answer it &mdash; each one quoted, attributed and linked back to the source.</p>
</header>

<section>
  <h2>Try it</h2>
  <p class="note">These are the 50 benchmark questions. Everything below is what the system
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
</section>

<section>
  <h2>When should it refuse to answer?</h2>
  <p class="note">Six questions have no answer in this corpus. A system that answers them
  anyway is confidently wrong. Declining below a relevance score is the obvious fix &mdash;
  move the control and watch what it costs.</p>
  <div class="control">
    <div class="row">
      <label for="thr">Decline below</label>
      <input id="thr" type="range" min="-10" max="7" step="0.25" value="-10">
      <span class="mono" id="thrval" style="font-family:var(--f-mono);font-variant-numeric:tabular-nums">off</span>
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
      <tr><td>BM25</td><td class="n">0.659</td><td class="n">0.545</td><td class="n">0.493</td><td class="n">4 ms</td></tr>
      <tr><td>Dense</td><td class="n">0.625</td><td class="n">0.432</td><td class="n">0.575</td><td class="n">28 ms</td></tr>
      <tr><td>Hybrid</td><td class="n">0.705</td><td class="n">0.568</td><td class="n">0.593</td><td class="n">39 ms</td></tr>
      <tr class="lead"><td>Hybrid + reranker</td><td class="n">0.727</td><td class="n">0.568</td><td class="n">0.653</td><td class="n">1996 ms</td></tr>
    </tbody>
  </table></div>
  <p class="note">Measured over the 44 answerable questions, on CPU. The demo above uses the
  last row. On <strong>cross-document</strong> questions &mdash; evidence spanning two
  instruments &mdash; hybrid beats BM25 by <strong>+0.250</strong> (95% interval +0.062 to
  +0.438), which is the one comparison the project predicted in advance. Most other
  differences are inside what 44 questions can resolve, and are reported as such.</p>
</section>

<footer>
  <p>Runs locally on CPU, no paid API keys. Source documents are not redistributed: the corpus
  is fetched at clone time, and this page shows short excerpts with links to the source rather
  than article text.</p>
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
      <p class="ex">${esc(c.excerpt)}&hellip;</p>
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

renderFilters(); renderList(); renderAnswer(); renderTally();
</script>"""


def main() -> int:
    if not DATA.exists():
        sys.exit(f"{DATA} not found. Run scripts/export_demo.py first.")
    payload = json.dumps(json.loads(DATA.read_text(encoding="utf-8")), ensure_ascii=False)
    # A literal </script> inside the data would close the tag early.
    payload = payload.replace("</", "<\\/")

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "results" / "demo.html"
    out.write_text(
        HEAD + BODY_TOP + BODY_BOTTOM + SCRIPT.replace("__DATA__", payload),
        encoding="utf-8",
    )
    print(f"wrote {out}  ({out.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
