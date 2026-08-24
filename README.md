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

TODO after Phase 1.

| | |
|---|---|
| Source | TODO |
| Documents | TODO |
| Sections after parsing | TODO |
| Chunks indexed | TODO |
| Date collected | TODO |

Source documents are **not committed to this repository**. `corpus/registry.csv`
lists every document with its URL and metadata, and
`scripts/download_corpus.py` fetches them:

```bash
pip install -r requirements.txt
python scripts/download_corpus.py
```

The script writes `corpus/manifest.json` with a SHA-256 for every file, so a
run can be tied to an exact corpus state.

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

TODO after Phase 3.

| category | n | description |
|---|---|---|
| single_hop | TODO | answerable from one section |
| cross_section | TODO | two or more sections, same document |
| cross_document | TODO | sections across separate instruments |
| temporal | TODO | requires the currently-in-force version |
| comparative | TODO | contrasts obligations across entity types |
| adversarial | TODO | premise is false or unsupported |
| unanswerable | TODO | not covered by the corpus; correct response is abstention |

Each question records the sections that must be retrieved, why each one is
required, how long labelling took, and the labeller's confidence. Format is
defined in `benchmark/schema.json`; the target mix, the construction rule for
cross-document items, and the labelling protocol are in `benchmark/PLAN.md`.

**Labelling honesty.** Low-confidence items are excluded from headline metrics
by default. The count of excluded items is reported here: TODO.

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

| Phase | Deliverable |
|---|---|
| 0 | Calibration: difficulty and question mix decided (`benchmark/PLAN.md`) |
| 1 | Registry populated, corpus downloading, licensing recorded |
| 2 | Parsing and chunking; sections carry citable identifiers |
| 3 | 50 labelled benchmark questions |
| 4 | Four systems built and measured; results tables filled |
| 5 | Grounded answering, citation validation, API and UI |
| 6 | *Optional:* cross-reference graph expansion |

Phase 6 is optional and should not be started until 1–5 are complete.
