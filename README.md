# ReguLens

**A retrieval evaluation over UAE insurance regulatory documents.**

Most RAG projects ship a chatbot and assert that it works. This one ships a
benchmark and measures four retrieval architectures against it. The chatbot is
the demo; the evaluation is the project.

> **Status:** in development. Corpus and benchmark are complete; the results
> tables are empty and no results are claimed until they contain real measured
> numbers.

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

**Complete: 50 of 50 verified.** Counts are regenerated by
`python scripts/validate_benchmark.py`, which also reports drift from the target
mix in `benchmark/PLAN.md`.

| category | n | description |
|---|---:|---|
| single_hop | 10 | answerable from one section |
| cross_section | 18 | two or more sections, same document |
| cross_document | 8 | sections across separate instruments |
| temporal | 0 | requires the currently-in-force version; deferred from v1 |
| comparative | 5 | contrasts obligations across entity types |
| adversarial | 3 | premise is false or unsupported |
| unanswerable | 6 | not covered by the corpus; correct response is abstention |

Verification took 173 minutes in total, median 3 minutes per question.

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
default. Final distribution: **50 high, 0 medium, 0 low**, so all 50 items are
scored and none is excluded.

That uniformity carries no information, and it is recorded here rather than
presented as reassurance: one item was originally marked medium and was raised
to high after the fact. Self-reported confidence is weak evidence in any case,
which is why this project does not rest on it. A blind negative control measures
the verification directly - **5 of 8 planted label errors caught, 1 false alarm
across 8 untouched items** - and that number is the honest calibration. See
`results/label_verification_control.md`.

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

Written before the results, not after.

**Every question was LLM-drafted and human-verified, and verification changed
nothing** — so the verification itself was measured rather than asserted. A
blind negative control planted deliberate errors in 8 of 16 sampled labels:
**5 of 8 were caught, with 1 false alarm on the 8 untouched items**
(`results/label_verification_control.md`).

At a detection rate near 62%, the fact that no correction was made across the
real 50 labels rules out four or more undetected errors at the 5% level, but not
zero to three. **The defensible claim is therefore that the benchmark contains
at most about three label errors, probably fewer** — a measured bound rather
than an assurance, and a weaker claim than the project would like.

The control also showed *which* errors get through. Swapped and superfluous
sections were caught 5 of 6 times; the two misses were a **dropped required
section** and an **unanswerable item given evidence**. Both are errors of
omission — the review reliably judged whether a listed section belonged, and
less reliably noticed what was absent. Those two shapes were re-checked across
the whole benchmark as a result.

Read the ground truth as *checked, with a known detection rate*, not as
*independently established*.

**Ground truth is labelled by one non-expert author.** There is no second
labeller and no inter-rater agreement figure, so a systematic misreading would
not be caught by anything in this repository.

**The benchmark is small: n = 50.** By-category counts are smaller still —
`adversarial` has 3 items, `comparative` 5. One or two questions move a
per-category recall figure by 20 to 33 percentage points, far more than the four
systems are likely to separate by. Report confidence intervals, and where they
overlap say so plainly rather than narrating a ranking the data does not
support.

**The corpus is a subset.** 46 instruments from the Insurance section of the
Rulebook, of which 39 carry substantive text. Four are listed but unpublished;
four more are indexed as distractors but barred from the answer key. Nothing
outside insurance is present, which is why questions about banking, the DIFC or
finance companies are correctly unanswerable *here* and not unanswerable in
general.

**Evidence labels reflect one reading.** Another reader could reasonably include
a section this benchmark treats as merely helpful, or drop one it treats as
required.

**The corpus is a snapshot.** Collected 2026-08-24 from a live site.
`corpus/manifest.json` pins a SHA-256 per document so a result ties to an exact
corpus state, but the published text may since have moved.

### What surprised me

- **The Rulebook publishes structured HTML**, so there is no PDF parsing in this
  project at all — section identity is read from the document's own markup. That
  removed most of the schedule risk the project was scoped around.
- **Instruments are listed In-Force with commencement dates in the future.** Four
  are, one only three weeks after collection. They are indexed as distractors but
  barred from the answer key, because deciding which instrument governs an
  obligation today is a legal judgement this project does not make.
- **Three registry rows initially fetched an entire category** rather than a
  document, which would have indexed the same article under four `doc_id`s and
  quietly destroyed the meaning of evidence recall.
- **Article numbering restarts inside compound instruments.** `Article 3` names
  two different provisions in INS-FIN-001, so labels there carry the document's
  own `Section N,` qualifier.

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
| 3 | 50 labelled benchmark questions | done |
| 4 | Four systems built and measured; results tables filled | |
| 5 | Grounded answering, citation validation, API and UI | |
| 6 | *Optional:* cross-reference graph expansion | |

Phase 6 is optional and should not be started until 1–5 are complete.
