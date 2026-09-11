# Swapping models is the lever everyone reaches for first, and it moved least

Measured 2026-09-11 with `scripts/run_model_sweep.py`, over the 86 answerable
questions. Raw output in `results/model_sweep.json`.

Three embedding models against three reranker conditions, everything else held
at the shipped configuration. `rerank.py` has carried a note since Phase 4 saying
a larger reranker was "the obvious next experiment if the reranker earns its
place". It earned it. This is that experiment.

## The result

recall@10, with a paired bootstrap against the shipped pair:

| embedding | reranker | dim | recall@10 | vs shipped | 95% interval | established |
|---|---|---:|---:|---:|---|---|
| bge-base | MiniLM-L6 | 768 | **0.773** | +0.023 | +0.000 to +0.052 | no |
| e5-base | MiniLM-L6 | 768 | 0.756 | +0.006 | −0.023 to +0.041 | no |
| **bge-small** | **MiniLM-L6** | 384 | **0.750** | *shipped* | | |
| bge-base | none | 768 | 0.715 | −0.035 | −0.099 to +0.029 | no |
| bge-base | bge-reranker | 768 | 0.709 | −0.041 | −0.099 to +0.017 | no |
| bge-small | bge-reranker | 384 | 0.698 | −0.052 | −0.105 to +0.000 | no |
| bge-small | none | 384 | 0.686 | −0.064 | −0.140 to +0.006 | no |
| e5-base | none | 768 | 0.680 | −0.070 | −0.145 to +0.006 | no |
| e5-base | bge-reranker | 768 | 0.680 | **−0.070** | −0.122 to −0.017 | **yes** |

**Exactly one row clears zero, and it is the worst one.** Every improvement, and
almost every degradation, sits inside an interval that contains no difference at
all. The best configuration found - doubling the embedding dimension from 384 to
768 - is +0.023 with a lower bound of exactly +0.000.

## What that means next to the configuration findings

| change | difference | established |
|---|---:|---|
| Chunking + document title (`results/combined.md`) | **+0.116** | **yes** |
| Best model swap in this sweep | +0.023 | no |

Swapping the embedding model is the first thing most RAG projects try, and on
this corpus it cannot be distinguished from noise at n=100. Two configuration
defaults nobody had questioned produced five times the point estimate and an
interval that clears zero comfortably.

This is the same lesson the benchmark taught about itself at 50 questions -
*the measuring instrument was the limit, not the system* - arriving from the
other direction. The instrument is now good enough to establish a +0.116 effect
and still not good enough to resolve a +0.023 one.

## The bigger reranker is worse, and the integration was checked

`bge-reranker-base` is 1.1 GB against MiniLM-L6's 90 MB and generally ranks
higher on public leaderboards. Here it is worse in every pairing, by 0.041 to
0.076 against the same embeddings with MiniLM.

That was surprising enough to verify rather than report. On a spot-check query
it produces well-spread scores (0.955 down to 0.207), genuinely reorders the
hybrid candidate list, and its top two results match MiniLM's exactly. It is
working; it is just not better here.

A plausible reason, offered as a hypothesis and not a measurement: MS MARCO is
web question-answering, and this benchmark's questions are natural
question-shaped paraphrases. A reranker trained on that distribution may simply
fit these questions better than a multilingual retrieval-oriented one does.
Whatever the cause, "newer and larger" did not transfer.

## The reranker still matters more than the embedding

Holding the embedding fixed and adding MiniLM-L6:

| embedding | no reranker | + MiniLM-L6 | gain |
|---|---:|---:|---:|
| bge-small | 0.686 | 0.750 | +0.064 |
| bge-base | 0.715 | 0.773 | +0.058 |
| e5-base | 0.680 | 0.756 | +0.076 |

Consistently around +0.06 to +0.08, on every embedding model. That is a larger
and steadier effect than any embedding swap, and it reproduces Phase 4's finding
about reranking three more times on models Phase 4 never used.

## Fairness note

Each embedding model was given its own prefixes: BGE instructs the query only,
E5 prefixes both query and passage, GTE neither. Running E5 with BGE's
instruction - or with none - would have measured the prefix rather than the
model, and would have quietly understated the alternative while flattering the
incumbent. `instructions_for` keeps that pairing with the model name.

## Limits

- **Three embedding models and two rerankers**, all small enough to run on CPU.
  A 7B-parameter reranker is not represented and might behave differently.
- **n=100 is the binding constraint**, not the models. Every non-established row
  here would need a larger benchmark to resolve, and that is the actionable
  conclusion: expand the question set before swapping models again.
- One chunking setting (the shipped one) and no document title, so these numbers
  do not compose with `results/combined.md` - the interaction between model
  choice and those two changes is unmeasured.
- Latency was not recorded per configuration. bge-reranker-base is
  substantially slower as well as worse, which makes it an easy exclusion, but
  the number is not here.

## Reproducing

```
python scripts/run_model_sweep.py --embeddings-only   # skips the rerankers
python scripts/run_model_sweep.py                     # ~20 minutes plus 1.9 GB of downloads
```
