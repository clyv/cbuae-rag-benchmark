# Benchmark construction plan

Decided after the Phase 0 calibration (2026-08-24). This file records *why* the
question mix is what it is, so the choice can be defended rather than asserted.

## The constraint that sets the mix

The benchmark exists to **separate four retrieval systems**. That is its only
job. A question BM25 answers correctly contributes nothing to the comparison,
however sound it is as a compliance question.

This rules out the advice to weight toward `single_hop` in order to reduce
labelling effort. Labelling cost is a budget constraint, and the correct
response to a budget constraint is **fewer questions, not easier ones**. Forty
discriminating items beat fifty where thirty are free wins for every system.

## Target mix (n = 50)

| category | n | why this many |
|---|---:|---|
| `single_hop` | 10 | Floor check. If a system misses these it is broken. Not expected to separate anything. |
| `cross_section` | 18 | The workhorse. Genuinely hard to retrieve, cheap to label because one document stays open. |
| `cross_document` | 8 | Expensive to label and expensive to construct — see the construction rule below. Capped deliberately. |
| `comparative` | 5 | Contrasts obligations across entity types. Cheap, because both sides sit in parallel instruments. |
| `adversarial` | 3 | False or unsupported premise. |
| `unanswerable` | 6 | Not covered by the corpus. Fills the abstention table in the README, which cannot be populated without these. |
| `temporal` | 0 | Deferred from v1. The Rulebook has revision-history pages but they have not been checked for clean before/after pairs. If this category is ever built, the four future-commencement Takaful instruments below are its natural material. |

## Construction rule for `cross_document`

The calibration found that insurance regulations are **largely self-contained** —
each restates the Board's role internally instead of deferring to the corporate
governance instrument. A question built by picking two thematic peers therefore
collapses into a single document and is silently mislabelled.

Genuine cross-document links are one of two shapes:

1. **General instrument → specific instrument.** A general rule sets a ceiling
   and a product- or entity-specific rule tightens it. Both must be retrieved
   because the binding constraint is whichever is more restrictive.
2. **Definitional deference.** Document A uses a term or limit that is defined
   in document B, so A alone is not answerable.

Build all 8 from these two shapes. Do not build any by picking two
related-sounding regulations and hoping the evidence spans them.

## Numerical reasoning is not scored

A question may require arithmetic to answer in real life while costing nothing
extra to label here, because the graded ground truth is *which sections were
required*, not *what number comes out*. Questions where several limits must be
reconciled are therefore good value: hard to retrieve, cheap to label.

## Where section labels come from

Added after Phase 2, because a label that does not match the corpus scores zero
no matter how good the retriever is.

`corpus/processed/sections.jsonl` is the authoritative vocabulary. Every record
has a `doc_id` and a `section`, and `doc_id::section` is exactly the string
`required_evidence` is scored against. **Cite from that file, not from memory of
the web page.** The conventions it follows:

| printed heading | label to use |
|---|---|
| `Article (3): Effective Risk Management System` | `Article 3` |
| `Article 2 Scope of Application` | `Article 2` |
| `Schedule No. (1)` | `Schedule 1` |
| `1. Definitions` | `1` |
| `Definitions` (no number printed) | `Definitions` |
| an article inside a numbered Part | `Section 2, Article 3` |

That last row matters for INS-FIN-001 and INS-FIN-002, which restart article
numbering in each part. A bare `Article 3` names two different provisions in
those instruments and will not match anything.

## Four documents you may not cite

`INS-TAK-001`, `INS-TAK-006`, `INS-TAK-007` and `INS-TAK-008` are in the
retrieval index but marked `labelling_eligible=false` in the registry. They are
listed In-Force while commencing after the corpus was collected, and deciding
which instrument governs an obligation today is a legal judgement this project
does not make. Keeping them indexed is deliberate - they are hard negatives on
adjacent subject matter, and deleting the best distractors flatters every
system.

`scripts/validate_benchmark.py` rejects any question naming one in
`required_evidence`. `helpful_evidence` may reference them, since it is not
scored for recall.

Four further documents - `INS-GOV-005`, `INS-GOV-007`, `INS-GOV-009`,
`INS-TAK-007` - parse to a title and no body: the Rulebook lists them but has
not published their text. There is nothing in them to cite.

That leaves **39 documents** with substantive, citable text.

## How Phase 3 runs

Two files. `benchmark/drafts.jsonl` holds candidates; `benchmark/questions.jsonl`
is the benchmark. `scripts/promote_drafts.py` is the only thing that moves an
item between them, and it refuses anything a person has not checked.

```bash
python scripts/promote_drafts.py --list          # what is still unverified
python scripts/browse_corpus.py --verify D001    # the whole item, ready to check
# edit benchmark/drafts.jsonl: set minutes_to_label and add confidence
python scripts/promote_drafts.py                 # move the verified ones
python scripts/validate_benchmark.py
```

`--verify` prints the question, the full text of every section it cites, and a
direct Rulebook link for checking against the published source. That is the
whole verification packet in one command, so the answer to "what is D001?" never
requires reconstructing it from an id.

A draft carries `minutes_to_label: 0` and no `confidence`. Those are the two
fields only a person can honestly supply, so they are the gate. Verifying means
opening each cited section and checking that it genuinely supports the question,
that nothing required is missing, and that the set is minimal - then recording
the real time and a confidence level.

**Drafted evidence is not verified evidence.** Every draft in the file resolves
to a real section, which is not the same as being right. Whether a section is
*required* is a judgement about the regulation, and the project's one
substantive claim is that a human made it. A benchmark drafted and approved by
the same model measures the model's reading, not the regulation.

## Do not write questions by searching

`browse_corpus.py --find` exists for looking things up, not for choosing what to
ask. Questions discovered by typing a phrase and taking what comes back produce
evidence sets that are exactly the passages containing that phrase, and BM25
then scores well on the benchmark because the benchmark was built through a
lexical lens - not because it is good.

That failure is invisible in the results table. It shows up as "hybrid retrieval
adds little", which is precisely the finding this project exists to test. Browse
by document structure to choose the question; read the article to label it.

## Labelling protocol

Non-negotiable, because violating it silently poisons every metric:

- **Run `python scripts/validate_benchmark.py` as you go.** It now checks three
  things that would otherwise fail silently: the schema, that every
  `doc_id::section` actually exists in `corpus/processed/sections.jsonl`, and
  that no answer key names a labelling-ineligible instrument. A mistyped section
  label is indistinguishable from a retrieval failure once results are being
  measured - the question just scores zero forever and the system gets blamed.
- **Read the article. Do not label from a summary** — not from an LLM's, not
  from this file's, not from a secondary source. Every specific figure produced
  during calibration by chatbots (retention periods, tenor caps, stress-test
  bands, clause numbers) was unverified, and two of the five models involved
  admitted they never opened a document.
- Keep `required_evidence` **minimal and bounded**. The calibration's first
  attempt — "what are its risk management obligations" — had no determinate
  evidence set; seven articles were arguably required. Narrow questions with a
  small evidence set can still be hard to retrieve. Broad ones are simply
  unlabellable.
- Record `minutes_to_label` honestly. An item over ~20 minutes is a signal the
  question is too ambiguous, not a signal to persevere.
- Set `confidence` low without embarrassment. Low-confidence items are excluded
  from headline metrics and the count is reported.

## Labelling budget, measured rather than guessed

The original estimate here was about four times too pessimistic. It is kept
alongside the measured figures because being wrong about your own process in a
recorded way is worth more than a tidy table.

| category | first estimate | measured | source |
|---|---:|---:|---|
| `single_hop` | 3 min | **2.4 min** | 5 items: 3, 2, 3, 2, 2 |
| `cross_section` | 8 min | **3 min** | 1 item |
| `cross_document` | 20 min | **5 min** | 1 item |
| `comparative` | 10 min | not yet measured | |
| `adversarial` | 10 min | not yet measured | |
| `unanswerable` | 10 min | not yet measured | |

Estimated total fell from **8 hours to roughly 3**. Two reasons, both worth
knowing: verifying a draft is faster than authoring a label from nothing, and
reading document-by-document rather than question-by-question means each
instrument is opened once instead of once per question.

The unanswerable items are the exception and may still run long. Establishing
that something is genuinely *not* covered means proving a negative, and an
unanswerable item that turns out to be answerable penalises every system for
retrieving correctly.
