# Query rewriting does not help here, and the failure taxonomy said so first

Measured 2026-09-11 with `scripts/run_rewrite.py`, over the 86 answerable
questions, hybrid + reranker throughout. Raw output in `results/rewrite.json`.

## The prediction, made before the run

Recorded in `src/regulens/retrieval/rewrite.py` and committed before this
executed:

> Query rewriting attacks vocabulary mismatch. `results/failures.md` measured
> vocabulary mismatch at **one** of 39 missed sections. 62% of misses are the
> right instrument and the wrong article inside it, where the question already
> shares the document's vocabulary and rewriting adds nothing that
> discriminates.

## The result

| system | recall@10 | full recall@10 | vs baseline | 95% interval | latency |
|---|---:|---:|---:|---|---:|
| baseline | **0.750** | 0.593 | — | | 159s |
| PRF | 0.738 | 0.581 | −0.012 | −0.047 to +0.017 | 150s |
| HyDE | 0.744 | 0.593 | −0.006 | −0.041 to +0.023 | **706s** |

Both are slightly negative. Neither difference is established. **HyDE costs 4.4x
the wall-clock time to arrive at no improvement.**

This is the first prediction in this project that was right about both the
direction and the reason. The document-title prediction was right about
direction and wrong about mechanism; the graph prediction was wrong about the
premise entirely. Here the taxonomy said vocabulary was not the bottleneck, and
attacking vocabulary did nothing.

## Why expansion is flat rather than merely useless

Pseudo-relevance feedback assumes the top few results are roughly right and
sharpens the query toward them. That assumption is the problem, and it splits
the benchmark in two:

- On questions retrieval already answers, the top results *are* right, so
  expansion adds terms the query did not need. No gain available.
- On questions retrieval misses, the top results are wrong, so expansion
  harvests terms from the wrong sections and pulls the query further from the
  answer. Actively harmful.

That is a mechanism for flat-to-negative rather than for "no effect", and the
sampled expansions show it. For the first benchmark question, the terms
harvested were *classes, prescribe, market, system, marketing, location,
reconciliation* - drawn from a first pass that had not found the right article,
and describing nothing the question asked about.

## A near miss worth recording

The first version of this measured PRF at exactly 0.000 and would have been
written up as a clean null result. It was wrong. The expansion filter excluded
corpus-specific noise but not English function words, because `tokenize` does not
strip them - BM25's inverse document frequency discounts them to nothing, so the
indexing path never needed to. Pseudo-relevance feedback counts raw occurrences
and has no such protection, so every query was being expanded with:

> *into related effective subject from this legal between*

A null result produced by a broken implementation looks exactly like a null
result produced by a technique that does not work. The only thing that
distinguished them was printing what the rewriter actually did, which is why
`RewrittenRetriever` records every rewrite and this script prints samples.

The fixed version expands the same query to *policy, details, limits,
counterparties, management, corporate, managing, transactions* - and still does
not help, which is now a finding rather than a bug.

## What HyDE produced

The hypothetical passages are fluent and plausible, which is what HyDE is for -
they are used as a query and never shown to anyone. For the first question the
0.5B model wrote:

> *"An insurer seeking to expand its coverage beyond the limits ap..."*

Right register, right topic, and it still did not move retrieval. Against a
corpus where the question and the answering article already share vocabulary,
making the query look more like regulation adds signal that was not missing.

## Limits

- **One generator for HyDE**, and a 0.5B one. A larger model writes better
  hypothetical passages, and the technique's published gains are usually
  reported with much larger models. This says HyDE-with-a-small-model does not
  help here, not that HyDE cannot.
- **One PRF configuration**: 3 feedback documents, 8 terms. The parameters were
  not swept, and a sweep is hard to justify given the mechanism above.
- Both rewriters were measured with the shipped chunking and no document title.
  Whether rewriting interacts with the configuration from `results/combined.md`
  is unmeasured.
- n=100. As with `results/model_sweep.md`, a −0.012 effect is not resolvable at
  this sample size either way.

## Reproducing

```
python scripts/run_rewrite.py --prf-only   # no model, a few minutes
python scripts/run_rewrite.py              # adds HyDE, ~15 minutes
```
