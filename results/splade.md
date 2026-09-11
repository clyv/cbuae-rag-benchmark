# Learned sparse retrieval: a fifth system, and the same answer the graph gave

Measured 2026-09-11 with `scripts/run_splade.py`, over the 86 answerable
questions at the shipped chunking. Raw output in `results/splade.json`.

SPLADE is the retrieval family the four-system table does not cover: sparse like
BM25, so it scores through term matches, but with learned weights that put mass
on terms the passage never uses. On a passage about *deviation from the Risk
Appetite* it weights the words that are there —

> appetite 2.76, deviation 2.34, board 2.34, risk 2.15, approval 1.90

— and expands to ones that are not: **hunger** 1.96, *risks* 1.31, *documenting*
1.18, *approved* 1.17. Encoding the corpus takes 122 seconds and leaves a mean of
**216 non-zero terms per chunk** out of a 30,522-term vocabulary.

It is the one family that could plausibly fix paraphrase without giving up
lexical precision.

## The result

| system | recall@10 | full recall@10 | vs shipped | 95% interval |
|---|---:|---:|---:|---|
| **bm25 + dense + reranker** *(shipped)* | **0.750** | 0.593 | — | |
| bm25 + dense + splade + reranker | **0.750** | 0.593 | **+0.000** | **+0.000 to +0.000** |
| bm25 + dense + splade | 0.709 | 0.558 | −0.041 | −0.099 to +0.017 |
| splade alone | 0.686 | 0.547 | −0.064 | −0.128 to −0.006 |
| bm25 + dense | 0.686 | 0.547 | −0.064 | −0.134 to +0.006 |

Unreranked, adding SPLADE to the fusion is worth +0.023 (0.686 → 0.709).
**Reranked, it is worth nothing at all** — the interval is not merely centred on
zero, it *is* zero, because the reranked top 10 is identical on all 86 questions.

SPLADE alone scoring exactly what bm25+dense scores is a coincidence, and was
checked rather than assumed: the two agree on 59 of 86 questions and disagree on
27, so two genuinely different systems happen to average the same.

## "It added nothing" would be the wrong reading

SPLADE changed the candidate pool substantially:

| | |
|---|---:|
| Candidate-pool overlap at depth 50 | **79%** |
| Sections SPLADE newly introduced, across 100 questions | **1,048** |
| Questions whose reranked top 10 changed | **0** |

About ten of every fifty candidates were different, and the reranker discarded
every one of them. The reason is the third measurement:

| | recall@50 |
|---|---:|
| bm25 + dense | **0.930** |
| bm25 + dense + splade | **0.930** |

**Identical.** The 1,048 sections SPLADE brought in contained no required
evidence that was not already in the pool. It swapped a fifth of the candidates
for different non-evidence.

## The pattern this completes

This is the third candidate-expansion strategy measured here, and all three give
the same answer:

| | what it added | effect on the shipped system |
|---|---|---|
| Cross-reference graph (`graph.md`) | median 3 sections per query | **+0.000**, no question changed |
| Learned sparse fusion (this) | 1,048 sections over 100 queries | **+0.000**, no question changed |
| Query rewriting (`rewrite.md`) | expanded and hypothetical queries | −0.012 and −0.006 |

Against which:

| | what it changed | effect |
|---|---|---|
| Whole-section chunking + document title (`combined.md`) | what a candidate *is* | **+0.116**, interval clears zero |

**Candidate generation is not the bottleneck on this corpus. Representation is.**

The arithmetic behind that: the pool at depth 50 already holds 93% of required
evidence, and the reranked top 10 reaches 0.750. The 0.180 between them is a
*ranking* problem, not a retrieval one — which is exactly what
`results/failures.md` found from the other direction, where 62% of misses are the
right instrument and the wrong article inside it.

Three techniques were tried against the half of the problem that is not the
problem. Two configuration defaults, which change how a section is represented
rather than which sections are fetched, were worth 69% of the architecture gap.

## What this does not say

- **Not that SPLADE is a bad retriever.** Unreranked it improves the fusion, and
  alone it matches a BM25-and-dense hybrid while disagreeing with it on nearly a
  third of questions — it is finding different things, and some of them are
  right. It has nothing left to contribute *after* a cross-encoder has seen 50
  candidates, on a corpus of 954.
- **Not that it would be useless at scale.** A pool of 50 out of 954 chunks is 5%
  of the corpus. At a million documents the pool is a vanishing fraction, the
  reranker cannot see past it, and what puts candidates in it matters enormously.
  This result is about a small corpus with a generous candidate depth.
- **Not a measurement of naver/splade.** The OpenSearch checkpoint was used
  because the naver ones ship only `pytorch_model.bin`, which transformers
  refuses under CVE-2025-32434 unless torch is 2.6 or newer — and this project
  pins 2.5.1 in requirements, in the Dockerfile, and in every number already
  reported. Upgrading torch for one experiment would have meant every prior
  result came from a different stack.

## Reproducing

```
python scripts/run_splade.py
```

Downloads a 440 MB checkpoint, then about four minutes: two to encode the corpus
and two for the reranked cells.
