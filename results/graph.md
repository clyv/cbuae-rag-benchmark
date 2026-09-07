# Does the corpus's cross-reference graph help retrieval? No.

Phase 6. Measured 2026-09-07 with `scripts/build_graph.py` and
`scripts/run_graph_eval.py`, over the same 100 benchmark questions. Raw output in
`results/graph.json` and `results/graph_eval.json`.

## The idea

Regulation names the provisions it depends on. "The limits are as directed in
Article (3)" tells you exactly where the answer continues, and no retriever can
see it: BM25 and embeddings both score a passage on its own words, so a section
that *points at* the answer scores badly for the question the answer belongs to.
Extract those pointers, follow them after retrieval, and you should recover
evidence the ranker missed.

That is the standard graph-RAG argument. On this corpus it does not work, and
the reason is more interesting than the result.

## The graph

193 Article and Clause references across 763 sections, resolving to **102 edges**.

| | |
|---|---|
| resolved within a document | 97 |
| resolved across documents | 5 |
| self-references, dropped | 27 |
| point outside the corpus (Federal law, Cabinet resolutions), dropped | 12 |
| name an instrument not recognised | 4 |
| target ambiguous or absent | 21 |
| **sections with any edge** | **122 of 763 (16%)** |

Resolution is checked against the corpus, so an edge exists only if the section
it points at is real - a rule that guesses wrong produces no edge rather than a
wrong one. Three defects found by auditing the output rather than by reading the
code are worth naming, because each produced confident nonsense:

- One instrument numbers its articles continuously across chapters, so
  inheriting the citing chapter's prefix built labels that do not exist. Now a
  unique article number anywhere in the document resolves; an ambiguous one
  resolves to nothing.
- `"of the Standards"` said from *inside* the Standards means that document, not
  its companion Regulation. Reading it as a pointer invented a cross-document
  edge.
- `Sub-Article (11) of Article (13)` names article 13. Matching the first number
  took a paragraph for a provision, and produced six wrong edges.

## The premise fails

Phase 6 assumes that when a question needs two provisions, the regulation links
them. That is checkable directly. 59 of the benchmark's questions require exactly
two sections, giving 59 co-required pairs:

> **2 of 59 co-required pairs are joined by an explicit reference — 3.4%.**

The two that are: `Q026`, which spans a Regulation and its paired Standards, and
`Q065`, two articles of one instrument. 28 of the 59 pairs sit inside a single
document and 31 span two, and the corpus links almost none of them.

Only **16 of the 62 distinct required sections** have any edge at all.

## The ceiling

Before building anything, how many questions *could* a perfect expansion rescue -
where a required section the system missed sits within reach of one it found?
This bounds any expansion policy, not just the one implemented here.

| system | questions missing evidence | 1 hop | 2 hops | 3 hops |
|---|---:|---:|---:|---:|
| BM25 | 46 | 2 | 4 | 4 |
| Dense | 41 | 2 | 5 | 5 |
| Hybrid RRF | 39 | 3 | 4 | 4 |
| **Hybrid + reranker** | **35** | **1** | **1** | **1** |

For the system this project actually ships, a flawless graph expansion could fix
**one question out of 35**. More hops do not help: past one hop the graph runs
out of edges rather than reaching further.

## The measurement

Built anyway, because "cannot help" and "actively hurts" are different claims and
only the second needs a retriever to establish. Expansion sits between hybrid
retrieval and the cross-encoder, so the graph adds candidates and the reranker
decides whether any deserve a place.

Expansion adds a **median of 3 sections per query** (8 of 100 queries get none),
and the reranker sees 64 candidates where the baseline gives it 50 - a wider
budget than the baseline has, which biases in the graph's favour.

| | recall@10 |
|---|---|
| hybrid + reranker | 0.750 |
| graph-expanded + reranker | 0.750 |
| difference | **+0.000**, 95% interval +0.000 to +0.000 |

**Not one question changed.** Every section the graph contributed was scored by
the cross-encoder and ranked below the tenth result, on all 86 answerable
questions. The graph neither helps nor hurts: the second stage discards what it
adds, which is at least evidence that a reranked pipeline is robust to a noisy
candidate source.

## Why it fails, which is the part worth keeping

The graph is real, correctly built and useless here, and the reason is that it
encodes the wrong relation.

Regulatory cross-references are **procedural dependencies**: do this thing in
accordance with that provision, calculate this figure by the method set out
there. What a question needs is **topical completeness** - the two provisions
that together answer it. "What is the minimum capital, and what fund floor
applies alongside it?" needs two rules about capital adequacy. Those rules sit
next to each other in subject matter and have no reason to cite one another,
because neither is a step in the other's procedure.

So the structure the corpus writes down is not the structure the questions need.
A graph built from explicit references is a map of how the drafters organised
obligations, and retrieval is asking a different question about the same text.

That also says what a graph *would* have to be built from to help: co-citation
(provisions that supervisors cite together), shared defined terms, or the
Rulebook's own topical hierarchy. All three are latent structures rather than
stated ones, and none is a regular expression away.

## Limits of this measurement

- One corpus, 46 insurance instruments. Statute and case law cross-reference far
  more densely, and a corpus with an order of magnitude more edges could give a
  different answer. Nothing here says graph expansion never works.
- Explicit references only. The premise test measures whether *stated* references
  connect co-required provisions, not whether any relation does.
- 21 references were dropped as ambiguous or absent. Even if every one of them
  were recovered the edge count rises by a fifth, and the ceiling of 1 in 35 does
  not move meaningfully.
- The benchmark caps required evidence at two sections per question, so questions
  needing a chain of three provisions - where a graph would plausibly do best -
  are not represented.

## Reproducing

```
python scripts/build_graph.py --audit 10
python scripts/run_graph_eval.py --ceiling-only
python scripts/run_graph_eval.py
```

The first two need no models and run in seconds. The third builds the index and
takes a few minutes on CPU.
