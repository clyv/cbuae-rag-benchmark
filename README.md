# ReguLens

**A retrieval evaluation over UAE insurance regulatory documents.**

Most RAG projects ship a chatbot and assert that it works. This one ships a
benchmark and measures four retrieval architectures against it. The chatbot is
the demo; the evaluation is the project.

> **Status:** Phases 1-4 complete. Corpus, benchmark and the four-system
> comparison are measured and reported below. Phase 5 (grounded answering,
> citation validation, API and UI) is not built.

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
| 2 | Dense | `BAAI/bge-small-en-v1.5`, 384 dimensions, normalised, CPU |
| 3 | Hybrid | Reciprocal rank fusion of 1 and 2, untuned k=60 |
| 4 | Hybrid + reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` over 50 candidates |

Everything runs locally with no paid API keys.

---

## Results

Measured by `scripts/run_eval.py` over the 44 answerable questions, on CPU.
Regenerate the tables with `scripts/report_results.py`; raw per-question output
is in `results/`.

### Overall

| System | recall@5 | recall@10 | full_recall@10 | nDCG@10 | MRR | median latency |
|---|---|---|---|---|---|---|
| BM25 | 0.545 | 0.659 | 0.545 | 0.498 | 0.493 | 4 ms |
| Dense | 0.477 | 0.625 | 0.432 | 0.500 | 0.575 | 28 ms |
| Hybrid (RRF) | 0.614 | 0.705 | 0.568 | 0.562 | 0.593 | 39 ms |
| Hybrid + reranker | 0.625 | **0.727** | 0.568 | **0.599** | **0.653** | 1996 ms |

### The honest answer to the question this project asks

The ordering matches the hypothesis. **The statistics mostly do not support it.**

| Comparison | difference in recall@10 | 95% interval | separates? |
|---|---|---|---|
| Dense vs BM25 | −0.034 | −0.159 – +0.091 | no |
| Hybrid vs BM25 | +0.045 | −0.045 – +0.125 | no |
| Hybrid vs Dense | +0.080 | +0.000 – +0.170 | no |
| Hybrid + reranker vs Hybrid | +0.023 | −0.057 – +0.102 | no |
| Hybrid + reranker vs BM25 | +0.068 | −0.034 – +0.170 | no |
| Hybrid + reranker vs Dense | +0.102 | +0.023 – +0.193 | **yes** |

Paired bootstrap, 10,000 resamples, seeded per comparison so the intervals are
reproducible. Pairing matters here: both systems answer the same questions, so
the interval on the difference is much tighter than the overlap between two
per-system intervals would suggest.

**Only one comparison clears zero.** Hybrid retrieval with reranking beats dense
retrieval alone. Everything else — including hybrid against BM25, the comparison
the project was built to make — is inside the range this benchmark could produce
by chance at n = 44. The point estimates all move in the expected direction and
never once do so by enough to be sure.

That is the result. Forty-four questions cannot resolve a four-point recall
difference, and saying so is the finding rather than a failure to find one.

### By question category — recall@10

| System | single_hop | cross_section | cross_document | comparative | adversarial |
|---|---|---|---|---|---|
| BM25 | 0.700 | 0.583 | 0.688 | 0.700 | 0.833 |
| Dense | 0.600 | 0.639 | 0.812 | 0.400 | 0.500 |
| Hybrid (RRF) | 0.600 | 0.694 | **0.938** | 0.600 | 0.667 |
| Hybrid + reranker | 0.700 | **0.778** | 0.875 | 0.400 | 0.667 |

n: single_hop 10, cross_section 18, cross_document 8, comparative 5,
adversarial 3.

This is the interesting table, and it says what the overall numbers hide.

**On `cross_document` questions, BM25 reaches 0.688 and hybrid reaches 0.938.**
That is the project's hypothesis on its home ground: questions whose evidence
spans two instruments are exactly where combining lexical and dense retrieval
helps, and single-hop questions are where it does not — BM25 is as good there or
better. Eight questions cannot establish it, but the effect is large and lands
precisely where the argument predicted.

The reverse also shows: **dense retrieval is the weakest system on `comparative`
and `adversarial` questions** and the strongest single system on
`cross_document`. Regulatory text is full of exact terms — "Solvency Capital
Requirement", "Minimum Guarantee Fund" — that lexical search matches perfectly
and embeddings blur.

### What the reranker actually buys

**+0.023 recall@10 for 51× the latency**, and `full_recall@10` does not move at
all: 0.568 with and without it. The reranker reorders what hybrid retrieval
already found and does not find more complete evidence sets, which is the
ceiling its own design implies — a second stage cannot recover a section the
first stage never retrieved.

Where it does earn its cost is ranking quality: MRR rises 0.593 → 0.653 and
nDCG@10 0.562 → 0.599. It is better at putting the right section first, which
matters for a reader, and close to useless for finding sections that were
missed.

At two seconds per query on CPU, a system that is two points better and fifty
times slower is a trade-off, not an improvement.

### Questions no system could answer

**4 of the 44 answerable questions scored recall@10 = 0 on all four systems**:
Q001, Q003, Q028, Q042. A further **9 were never answered completely** by any
system — at least one required section always missing: Q006, Q009, Q016, Q019,
Q037, Q039, Q040, Q041, Q044.

Those 13 were re-checked against their cited articles after the results came in,
on the theory that a question no system can answer is either genuinely hard or
mislabelled. No label changed.

### Why the absolute numbers are lower than they look

The questions are **paraphrases, not quotations**. `benchmark/schema.json`
requires it — "avoid quoting the regulation verbatim, that turns the task into
string matching" — so a question asks about "exposure beyond the level its board
signed off on" where the regulation says "deviation from the Risk Appetite".

That choice costs a great deal of measured recall, and it is worth seeing how
much. Taking the four questions no system could answer, and re-querying BM25
with the regulation's own vocabulary instead of the question as written:

| Question | rank of the required section, as written | with keywords |
|---|---|---|
| Q001 | not in top 50 | **2** |
| Q003 | 46 | **1** |
| Q028 | 26 | **2** |
| Q042 | not in top 50 | **2** |

Every one of them is trivially retrievable by keyword. The systems are not
failing to find these sections; they are failing to connect a paraphrase to
them.

This matters when comparing these figures to published benchmarks. A recall@10
of 0.659 for BM25 looks weak next to numbers from datasets where questions were
generated from the passage they answer, and those are not measuring the same
thing. It also explains why the dense system was expected to win and did not:
paraphrase is where embeddings should help, and on this corpus the gain did not
outweigh what was lost on exact regulatory terminology.

### Abstention

Not a retrieval property. Retrieval always returns its top k, so on an item with
no required evidence recall is 1.0 because nothing can be missed and precision is
0.0 because nothing retrieved can be required — neither varies between systems.
Abstention belongs to the answering stage and is measured there. See below.

---

## Answering: citations and abstention

Measured by `scripts/run_answering.py` over hybrid+reranker at k=5. Full write-up
in `results/abstention.md`.

### Citation validity

| | |
|---|---|
| Citations grounded — the cited section was in the retrieved context | **1.000** |
| Citations supported — the quoted text appears in that section | **1.000** |

**Both are 1.0 by construction, not by achievement.** The default answerer is
extractive: it quotes retrieved sections and attributes each quote, so it cannot
cite a section it did not retrieve or attribute words that are not there. It
cannot hallucinate, which is the right default for a regulatory tool.

The figure is reported because it is the bar an abstractive generator must
clear. A model that paraphrases is more readable and can score below 1.0 on
either row, and that gap is the price of fluency. It is only visible if the
extractive number is on the page.

### Abstention does not work reliably, and the reason is the interesting part

| | min | median | max |
|---|---|---|---|
| Answerable (n=44) | −2.92 | 2.17 | 6.44 |
| Unanswerable (n=6) | −9.96 | −1.14 | 4.21 |

**AUC = 0.761, 95% interval 0.492 – 0.962.** The interval includes 0.5 — the
value meaning no separation at all. Six negatives cannot establish that the
relevance score distinguishes an unanswerable question from an answerable one.

Declining 5 of the 6 unanswerable costs **14 of 44 answerable questions wrongly
refused**. For a compliance tool that may still be the right trade, since a
refusal is recoverable and a confident wrong answer is not. `answer_question`
ships with no default threshold, because choosing the value that looks best on
these six questions would be fitting a parameter to the test set.

**Why it fails is diagnosable.** The worst case scores 4.21 — higher than most
answerable questions:

> *"What are the capital adequacy requirements for a finance company?"*
> → top hit `INS-FIN-001::Section 2, Article 3`, titled **Group Capital Adequacy**

A cross-encoder trained on topical relevance is *right* that the passage is
about capital adequacy. What it cannot see is that the passage governs a
different kind of entity. **That is a scope question, not a relevance question**,
and no threshold on a relevance score will answer it. Every document in this
corpus has a Scope of Application section, so the material for a real check
exists — that is the obvious next experiment.

The two hardest unanswerable questions are the two closest to the corpus subject
matter, which is exactly what the category was designed to produce.

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

A second review pass ran after the results, targeted at the two shapes the
control showed slipping through and at the 13 questions no system answered
completely. It changed nothing either. That does not prove the labels are
correct — it is the same reviewer, and the control measured what this reviewer
catches — but it is the second independent opportunity the errors had to
surface.

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

**Questions are paraphrases, so absolute recall is not comparable to benchmarks
built from quoted text.** The schema requires it, and the cost is measurable:
the four questions no system answered all have their required section in BM25's
top 2 when queried with the regulation's own words. See "Why the absolute
numbers are lower than they look".

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
| 4 | Four systems built and measured; results tables filled | done |
| 5 | Grounded answering, citation validation, API and UI | next |
| 6 | *Optional:* cross-reference graph expansion | |

Phase 6 is optional and should not be started until 1–5 are complete.
