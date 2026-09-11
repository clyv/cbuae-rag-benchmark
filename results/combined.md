# Two configuration changes are worth more than the architecture comparison

Measured 2026-09-11 with `scripts/run_combined.py`, over the 86 answerable
questions, hybrid + reranker throughout. Raw output in `results/combined.json`.

Two changes were each established separately:

- **not splitting sections** (`results/chunking.md`), +0.041
- **indexing the instrument's title** (`results/doc_title.md`), +0.052

Neither was a new technique. Both were configuration the project had chosen once
and never examined. This runs the 2x2 to see whether they overlap.

## The result

| configuration | recall@10 | full recall@10 | vs shipped | 95% interval |
|---|---:|---:|---:|---|
| shipped (512/64, no title) | 0.750 | 0.593 | — | |
| whole sections | 0.791 | 0.663 | +0.041 | +0.006 to +0.081 |
| doc title | 0.802 | 0.674 | +0.052 | +0.012 to +0.099 |
| **both** | **0.866** | **0.756** | **+0.116** | **+0.070 to +0.169** |

## They do not overlap - they reinforce

The prediction written down before the run was that the two would overlap,
because both plausibly fix the same failures: a whole section is easier to tell
from its siblings, and so is a section carrying its instrument's name. Expected
combination: less than the sum.

| | |
|---|---:|
| If the two were independent | +0.093 |
| Both, measured | **+0.116** |
| Interaction | **+0.023, more than the sum** |

Wrong again, and in the interesting direction. A plausible reading: with whole
sections each chunk is one complete provision, so the instrument's title attaches
to a coherent unit; when a section is fragmented, the same title is smeared
across several partial windows that then compete with each other. The two
changes are not two fixes for one problem - one makes the other work better.

That reading is a hypothesis, not a measurement. It is recorded as such.

**Full recall@10 moves 0.593 to 0.756** - the share of questions where *every*
required section was found rises by more than 16 points, which is a larger
relative move than recall@10 and the harder metric of the two.

## The number that reframes the project

The results table exists to compare four retrieval architectures. That comparison
spans **+0.169** from BM25 to hybrid+reranker, and establishing it was most of
Phase 4.

Two configuration changes - stop splitting, index a field that was already in the
metadata - are worth **+0.116**, about **69%** of the architecture gap. Neither
required a new model, a new dependency, or a new idea. Both were defaults nobody
had questioned.

This does not invalidate the architecture comparison: every system in it was
measured at one identical configuration, so it remains internally fair. What it
says is that a reported RAG number describes a *configuration*, not a technique,
and the configuration was carrying more of the result than the technique was.

It is also the strongest argument yet for the project's founding choice. Without
a benchmark, neither of these changes would have been visible - they produce no
error, no crash, and no symptom a developer would notice. The system just quietly
found less.

## Should the shipped defaults change?

Yes, with the caveat stated in the open.

**The case for.** Neither change is a tuned number. "Whole sections" removes a
step rather than setting a value, and is justified structurally - use the
drafter's own boundaries. "Index the document title" is closer to a bug fix: the
field was in the metadata, available to every system, and omitted by accident
rather than by decision. A configuration that scores 0.866 where the current one
scores 0.750, on the same corpus and the same questions, should not be left in
place out of tidiness.

**The case for caution.** Both gains were measured on the only 100 questions this
project has. Selecting the configuration that scores best on them is fitting to
the test set, which is exactly what the abstention threshold was deliberately
left untuned to avoid. The honest reading of +0.116 is that it is an *upper*
estimate of what a fresh question set would show.

The two changes differ in how much that caution bites. The document title is
information that should always have been indexed, and its omission was not a
choice anyone defended; adopting it is closer to fixing a defect than to picking
a winner. "Whole sections" is a genuine selection among alternatives, even if a
principled one.

## Limits

- One corpus, one embedding model, one reranker. "Whole sections" is only
  available because these sections are short - a median of 142 words.
- The interaction is measured once, at one pair of settings. Whether it holds at
  other chunk sizes is not known.
- Every number here is recall over labelled evidence. None of it says the answers
  a reader would get are better, only that the provisions are more often found.

## Reproducing

```
python scripts/run_combined.py
```

Roughly 15 minutes on CPU. Each cell caches its embeddings under `.cache/`, so
the shipped index is untouched.
