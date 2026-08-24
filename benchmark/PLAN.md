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
| `temporal` | 0 | Deferred from v1. The Rulebook has revision-history pages but they have not been checked for clean before/after pairs. Add only if that check passes. |

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

## Labelling protocol

Non-negotiable, because violating it silently poisons every metric:

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

## Rough labelling budget

Based on shape, not on any chatbot's self-reported timing:

| category | est. per item | subtotal |
|---|---:|---:|
| `single_hop` | 3 min | 30 min |
| `cross_section` | 8 min | 2 h 24 |
| `cross_document` | 20 min | 2 h 40 |
| `comparative` | 10 min | 50 min |
| `adversarial` | 10 min | 30 min |
| `unanswerable` | 10 min | 1 h |

Roughly **8 hours** of focused reading, and establishing that something is
genuinely *not* covered is slower than it looks. Budget two weekends.
