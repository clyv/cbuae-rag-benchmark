# Chunk size moves retrieval almost as much as the architecture does

Measured 2026-09-11 with `scripts/run_chunking_ablation.py`, over the 86
answerable questions. Raw output in `results/chunking.json`.

Every number this project has reported was measured at one chunking setting -
512 words with 64 of overlap - chosen in Phase 2 and never compared to anything.
The results table compares four retrievers across a choice that was itself never
tested. This tests it.

## The result

recall@10, hybrid + reranker:

| chunking | chunks | median words | recall@10 | full recall@10 | MRR |
|---|---:|---:|---:|---:|---:|
| **whole sections** | 763 | 142 | **0.791** | **0.663** | 0.665 |
| 1024 / 128 | 812 | 156 | 0.779 | 0.640 | 0.675 |
| 512 / 0 | 932 | 168 | 0.779 | 0.628 | 0.666 |
| 512 / 64 *(shipped)* | 954 | 176 | 0.750 | 0.593 | 0.674 |
| 256 / 32 | 1362 | 198 | 0.744 | 0.616 | 0.686 |
| 512 / 192 | 1010 | 216 | 0.744 | 0.593 | 0.661 |
| 128 / 16 | 2433 | 106 | 0.703 | 0.581 | 0.647 |
| 64 / 8 | 4860 | 50 | 0.669 | 0.523 | 0.603 |

Paired bootstrap against the shipped setting, 10,000 resamples:

| setting | difference | 95% interval | established |
|---|---:|---|---|
| **whole sections** | **+0.041** | +0.006 to +0.081 | **yes** |
| **512 / 0** | **+0.029** | +0.006 to +0.064 | **yes** |
| 1024 / 128 | +0.029 | +0.000 to +0.064 | no |
| 256 / 32 | −0.006 | −0.052 to +0.041 | no |
| 512 / 192 | −0.006 | −0.041 to +0.023 | no |
| 128 / 16 | −0.047 | −0.093 to +0.000 | no |
| **64 / 8** | **−0.081** | −0.145 to −0.017 | **yes** |

## Two things are established, and they point the same way

**Not splitting at all is better than the shipped setting.** +0.041 recall@10 and
+0.070 full recall@10, with an interval clearing zero. The hypothesis written
down before the run was that regulatory sections are already semantic units - one
article is one obligation, bounded by the drafter rather than by a token budget -
and that splitting them would cut an obligation away from the condition
governing it. The degradation is monotonic in chunk size, which is what that
prediction looks like when it holds.

**Overlap hurts.** Holding size at 512 and varying only overlap: 0.779 with none,
0.750 with 64 words, 0.744 with 192. The no-overlap gain clears zero. Overlap is
usually treated as free insurance against splitting mid-thought; here it is a
cost, because every overlapped window is a near-duplicate competing for the same
retrieval budget. `metrics._top_k` was deliberately written so duplicate sections
consume budget rather than being collapsed for free - this is that decision
showing up in a result.

## The number that should be uncomfortable

**The spread across chunking settings is 0.122. The spread across the four
architectures the project is built around is 0.169.**

A parameter chosen once in Phase 2 and never examined accounts for nearly as much
movement as the entire BM25-to-hybrid-plus-reranker comparison that the whole
benchmark exists to measure. That does not invalidate the architecture
comparison - every system in it was measured at the same setting, so the
comparison is internally fair. It does mean any single reported number is a
statement about a configuration, not about a technique, and the project had been
presenting one without saying so.

## It agrees with the failure taxonomy

`results/failures.md` classified every missed section and found that **62% are
the right instrument, the wrong article inside it**. Fragmenting an article into
windows is precisely what would cause that: each window competes with its own
siblings, all of which share the document's vocabulary and much of its phrasing,
and none of which is a whole provision. Two measurements arrived at the same
place from different directions.

## Should the default change?

The finding says yes and the method says be careful, because this is the same
trap the abstention threshold was left untuned to avoid: **the +0.041 was
measured on the only questions the project has.** Picking the setting that scores
best on the test set is fitting a parameter to it.

The argument for changing anyway is that "whole sections" is not a tuned value.
It is the removal of a step - use the drafter's own boundaries and do not split -
and it is justified structurally rather than numerically. It also happens to be
the simplest configuration available, with no size or overlap to defend.

The argument against is that whole sections is only viable because this corpus
has short sections: a median of 142 words and a maximum that still fits an
embedding model's context. On a corpus of 40-page chapters it would not be an
option, so the result does not generalise as advice.

Recorded as a finding, with the decision flagged rather than made quietly.

## Limits of this measurement

- One embedding model and one reranker. Chunk size interacts with context
  length, and a model with a longer window might tolerate large chunks better.
- Word-count budgets, not model tokens. `chunk.py` counts whitespace words; the
  tokenizer produces roughly 1.2-1.5x that, so "512" is about 600-750 real tokens.
- Retrieval only. Larger chunks mean more text per answer, which costs a
  generator more context and may dilute a citation - not measured here.
- The ground truth is section-level, which structurally favours not splitting:
  a whole-section chunk maps one-to-one onto the unit being scored. This is
  stated rather than corrected for, because sections are also what a citation
  has to name.

## Reproducing

```
python scripts/run_chunking_ablation.py --fast   # hybrid only, a few minutes
python scripts/run_chunking_ablation.py          # with the reranker, ~30 minutes
```

Each configuration caches its embeddings separately under `.cache/`, so the
shipped index is left untouched.
