# ReguLens

**A retrieval evaluation over UAE insurance regulatory documents.**

Most RAG projects ship a chatbot and assert that it works. This one ships a
benchmark and measures four retrieval architectures against it. The chatbot is
the demo; the evaluation is the project.

> **Status:** in development. Sections marked TODO are not yet populated. No
> results are claimed until the tables below contain real measured numbers.

---

## The question

Regulatory answers are rarely contained in a single passage. A question about a
broker's risk-management obligations may depend on one article establishing the
duty, another defining an exception, and a third in a separate instrument
setting the reporting requirement. Keyword search retrieves documents; it does
not reliably assemble the complete evidence needed to answer.

**Does hybrid retrieval with reranking improve evidence recall on multi-hop
regulatory questions, compared with lexical or dense retrieval alone?**

## What is measured, and what is not

This project measures **retrieval quality**: given a question, did the system
surface the document sections a human labelled as necessary to answer it?

This project does **not** claim legal accuracy. Determining whether an answer
is legally correct requires qualified compliance expertise, which the author
does not have and does not claim. The benchmark's ground truth is *which
sections are required*, not *what the law says*. Every metric below follows
from that choice.

This is a deliberate design decision, not a hedge. Evidence recall is
objectively checkable by anyone with the corpus open. Legal correctness is not.

**This repository is a technical portfolio project. Nothing in it is legal,
regulatory, or compliance advice.**

---

## Corpus

| | |
|---|---|
| Source | CBUAE Rulebook, Insurance section |
| Documents | 46 |
| Sections after parsing | 763 |
| Chunks indexed | 954 (512-word budget, 64-word overlap) |
| Words | 206,705 |
| Date collected | 2026-08-24 |

Every document is an instrument in its own right - regulations, standards, board
decisions and resolutions - covering licensing, governance and risk management,
financial and solvency regulation, reporting, Takaful, conduct, sanctions, motor
insurance and reinsurance.

Source documents are **not committed to this repository**. `corpus/registry.csv`
lists every document with its URL and metadata, and the pipeline rebuilds the
corpus from scratch:

```bash
pip install -r requirements.txt
python scripts/enrich_registry.py
python scripts/download_corpus.py
python scripts/build_corpus.py
```

`download_corpus.py` writes `corpus/manifest.json` with a SHA-256 for every
file, so a run can be tied to an exact corpus state. `build_corpus.py` writes
`corpus/processed/sections.jsonl`, `chunks.jsonl` and an `ingest_report.json`
recording the chunking parameters and every parser warning.

### How the documents are parsed

Worth stating plainly, because it is the decision that removed most of the
project's schedule risk: **there is no PDF parsing here.**

The Rulebook publishes every instrument as HTML in which each section is an
`h2.page-title` followed by a `div.field--name-body`, and each instrument has an
`/en/entiresection/<node_id>` view returning all of its articles in one request.
Section structure is therefore read from the document's own markup rather than
inferred from font sizes or heading regexes over extracted text. Official PDFs
exist and their URLs are recorded in the registry for provenance, but nothing in
the pipeline reads them.

Every chunk carries `doc_id` and the section identifier as printed, which
together form the `evidence_id` that benchmark labels are scored against. Three
things about that mapping are worth knowing before labelling questions:

- **Labels are normalised, not invented.** `Article (3): Effective Risk
  Management System` becomes `Article 3`; `Schedule No. (1)` becomes
  `Schedule 1`. The full heading survives in chunk metadata.
- **Compound instruments are qualified by their own addressing.** INS-FIN-001
  restarts its article numbering in each part, so its sections are
  `Section 1, Article 3` and `Section 2, Article 3` rather than a bare
  `Article 3` that would name two different provisions.
- **Sections without a printed identifier keep their heading as the label** -
  `Definitions`, `General Provisions`. 113 of the 763 sections are labelled this
  way; the other 650 carry a number.

One genuine ambiguity survives: INS-CON-001 prints `Article (14)` twice. It is
stored as `Article 14` and `Article 14 (2)` and flagged in the ingest report,
rather than silently collapsed.

### In the index, not in the ground truth

Four instruments are retrievable but may never be cited as required evidence.
`corpus/registry.csv` marks them `labelling_eligible=false`, and
`scripts/validate_benchmark.py` rejects any question whose `required_evidence`
names one.

They are the three Takaful standards commencing 2027-07-15 and the Takaful
Insurance Regulation commencing 2026-09-14 - all four listed by the Rulebook as
In-Force while carrying a commencement date after the corpus was collected.

**What that pairing means is not stated on the page, and this project does not
assert an interpretation.** It may be that an instrument is validly issued and
part of the current Rulebook with obligations phased in later; that is a
plausible reading, not a documented fact, so only the observation and the
handling are recorded here.

The handling follows from what this project already declines to claim.
Determining which instrument governs a given obligation *today* is a legal
judgement about commencement and transition. This benchmark measures retrieval.
So:

- **They stay in the index.** Three Takaful standards on adjacent subject matter
  are precisely the near-miss distractors that separate a good retriever from a
  bad one. Removing the hardest negatives would make every system look better
  than it is.
- **They stay out of the answer key**, because a label naming one would be an
  assertion about which instrument currently governs.
- They are the natural material for the `temporal` category if it is ever built.

`helpful_evidence` may still reference them: it is not scored for recall.

### Documents the Rulebook lists but has not published

Four entries - INS-GOV-005, INS-GOV-007, INS-GOV-009 and INS-TAK-007 - parse to
a title and nothing else. Three have no PDF in the Rulebook file store either.
They are kept in the registry and reported by `build_corpus.py` so the gap reads
as a finding about the source rather than a parser failure, but they contain no
citable text.

A separate observation, recorded because it is a limitation rather than a bug:
INS-GOV-008 publishes no effective date on its page, and its 17-page PDF
contains no date anywhere either. `effective_date_source` is `not_published` for
it and for three others. A missing effective date has no bearing on whether an
article is the right retrieval target, so those documents remain fully
labelling-eligible.

### Licensing and attribution

Corpus documents are © Central Bank of the UAE, retrieved from the CBUAE
Rulebook and reproduced locally for non-commercial research use only under the
CBUAE website [Terms and Conditions](https://www.centralbank.ae/en/footer/terms-and-conditions/)
(clause 2.3). This project is not affiliated with, endorsed by, or connected to
the Central Bank of the UAE.

Those terms permit download for non-commercial use with attribution, but **not
redistribution** — which is why no source document is committed here and why the
Phase 5 demo links to the Rulebook rather than mirroring it. The CBUAE Open Data
policy is more permissive but its stated scope is reports and studies, not the
Rulebook's regulatory text, so the more restrictive reading is the one applied.

Full record, including what was checked and when: `SOURCES.md`.

---

## Benchmark

**In progress: 7 of 50 verified.** The counts below are regenerated by
`python scripts/validate_benchmark.py`, which also reports drift from the target
mix. No results are computed until the set is complete, because a category with
two items cannot support a column in the by-category recall table - and that
table is the one this project's question turns on.

| category | verified | target | description |
|---|---:|---:|---|
| single_hop | 5 | 10 | answerable from one section |
| cross_section | 1 | 18 | two or more sections, same document |
| cross_document | 1 | 8 | sections across separate instruments |
| temporal | 0 | 0 | requires the currently-in-force version; deferred from v1 |
| comparative | 0 | 5 | contrasts obligations across entity types |
| adversarial | 0 | 3 | premise is false or unsupported |
| unanswerable | 0 | 6 | not covered by the corpus; correct response is abstention |

Each question records the sections that must be retrieved, why each one is
required, how long labelling took, and the labeller's confidence. Format is
defined in `benchmark/schema.json`; the target mix, the construction rule for
cross-document items, and the labelling protocol are in `benchmark/PLAN.md`.

### How a question gets into the benchmark

Questions are drafted into `benchmark/drafts.jsonl` and only enter
`benchmark/questions.jsonl` once a person has opened the cited sections and
checked them. `scripts/promote_drafts.py` enforces this: it refuses any item
without a recorded verification time and confidence level, the two fields only a
human can honestly supply.

This matters because the drafts were LLM-written. Every one resolves to a real
section and passes every automated check, which is not the same as being
correct - whether a section is genuinely *required* is a judgement about the
regulation. A benchmark drafted and approved by the same model would measure the
model's reading rather than the regulation, and every number downstream would
inherit that. `provenance.source` records `llm_drafted_human_verified` on each
item so the split is visible rather than implied.

**Labelling honesty.** Low-confidence items are excluded from headline metrics by
default. Current distribution: 6 high, 1 medium, 0 low - so 7 of 7 verified items
would be scored. The final count is reported here when the set is complete.

---

## Systems compared

| # | System | Description |
|---|---|---|
| 1 | BM25 | Lexical baseline |
| 2 | Dense | Local embedding model, TODO which |
| 3 | Hybrid | Reciprocal rank fusion of 1 and 2 |
| 4 | Hybrid + reranker | Local cross-encoder over a wide candidate set |

Everything runs locally with no paid API keys.

---

## Results

TODO after Phase 4. **Do not populate these tables with anything but measured
output from `scripts/run_eval.py`.**

### Overall

| System | recall@5 | recall@10 | full_recall@10 | nDCG@10 | MRR | median latency |
|---|---|---|---|---|---|---|
| BM25 | | | | | | |
| Dense | | | | | | |
| Hybrid | | | | | | |
| Hybrid + reranker | | | | | | |

### By question category — recall@10

| System | single_hop | cross_section | cross_document | temporal | comparative |
|---|---|---|---|---|---|
| BM25 | | | | | |
| Dense | | | | | |
| Hybrid | | | | | |
| Hybrid + reranker | | | | | |

This second table is the interesting one. If the systems separate anywhere, it
will be on the multi-hop categories.

### Abstention

| System | correctly declined on unanswerable items |
|---|---|
| | |

---

## Limitations

Write these before the results, not after.

- Ground truth is labelled by one non-expert author. TODO: describe any
  verification done.
- Benchmark size is small (TODO n). Differences between systems may not be
  statistically meaningful; report confidence intervals or say plainly that
  you cannot.
- The corpus is a subset, not the complete regulatory framework.
- Evidence labels reflect one reading of each question. Another reader might
  label a different section set.
- TODO: anything that surprised you. This section is more persuasive when it
  is specific.

---

## Repository layout

```
corpus/
  registry.csv          documents to collect - the source of truth
  registry.example.csv  shape reference (all values fake)
  raw/                  downloaded sources (gitignored)
  processed/            parsed sections (gitignored)
benchmark/
  schema.json           question format
  questions.jsonl       the benchmark
  questions.example.jsonl
scripts/
  download_corpus.py    fetch the corpus
src/regulens/
  ingest/               parsing and chunking
  retrieval/            the four systems, one interface
  evaluation/           metrics and harness
  generation/           grounded answering, citation validation
tests/
results/                measured output, committed
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest
```

## Build order

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Calibration: difficulty and question mix decided (`benchmark/PLAN.md`) | done |
| 1 | Registry populated, corpus downloading, licensing recorded | done |
| 2 | Parsing and chunking; sections carry citable identifiers | done |
| 3 | 50 labelled benchmark questions | in progress: 7 in the benchmark, 43 drafted |
| 4 | Four systems built and measured; results tables filled | |
| 5 | Grounded answering, citation validation, API and UI | |
| 6 | *Optional:* cross-reference graph expansion | |

Phase 6 is optional and should not be started until 1–5 are complete.
