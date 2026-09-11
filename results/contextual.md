# Contextual retrieval loses to a field that was already in the metadata

Measured 2026-09-11 with `scripts/run_contextual.py`, over the 86 answerable
questions, hybrid + reranker at whole-section chunking. Raw output in
`results/contextual.json`.

A 0.5B model wrote one sentence for each of the 763 sections, situating it inside
its instrument, prepended before indexing. That is contextual retrieval as
published, and the reported gains for it are large.

It was tried here for a specific reason rather than a fashionable one:
`results/failures.md` measured that **62% of missed sections are the right
instrument and the wrong article inside it**, and a per-chunk context sentence is
aimed exactly at telling sibling articles apart.

## The result

| configuration | recall@10 | full recall@10 | vs base | 95% interval |
|---|---:|---:|---:|---|
| whole sections | 0.791 | 0.663 | — | |
| **+ document title** | **0.866** | **0.756** | **+0.076** | **+0.035 to +0.122** |
| + generated context | 0.837 | 0.698 | +0.047 | +0.000 to +0.099 |
| + context + title | 0.826 | 0.698 | +0.035 | −0.017 to +0.087 |

**The free option wins.** Indexing the document title - a string already sitting
in the metadata, costing nothing - beats 75 minutes of LLM generation, and is the
only row whose interval clears zero comfortably.

And the two do not compose. Adding the generated context **on top of** the title
*lowers* recall from 0.866 to 0.826. Head to head:

| | difference | 95% interval | established |
|---|---:|---|---|
| context → title | +0.029 | −0.017 to +0.070 | no |
| title → context + title | −0.041 | −0.087 to +0.000 | no |

Neither head-to-head clears zero at n=100, so the honest statement is that the
title is **at least as good** as the generated context and plausibly better,
while costing nothing. What is not in doubt is the direction: every arrangement
involving generated text scores below the title alone.

## Why they interfere

Both changes put text in front of the provision, and the budget is not free. The
context sentences average 191 characters. Prepending both a 15-word instrument
title *and* a 30-word generated sentence pushes the article's own language down
the passage and dilutes it in a fixed-size embedding. Two signals competing for
the same space is a different situation from `results/combined.md`, where
whole-section chunking and the title were superadditive - there, one change made
room for the other; here, both consume it.

## The failure that a score alone would hide

`INS-LIC-001::Article 1` is the Licensing Regulation's **Definitions** section: a
glossary of forty-odd defined terms, beginning with *Actuary*. The model wrote:

> *"This section outlines the qualifications and requirements for an actuary to
> ensure the stability and solvency of an insurance company."*

That is not a hallucination in the usual sense - every word traces to text the
model saw. It is worse in a subtle way: it describes the section as being *about*
actuary requirements, when the section is a glossary and "Actuary" is merely its
first entry. The model was shown the first 600 characters, and those happen to
open with that one definition.

The cost is indexed. Queries about actuaries now get an extra pull toward a
definitions section, and queries about the other thirty-nine defined terms get a
context sentence that describes none of them.

That 600-character limit was a deliberate trade, recorded in `contextual.py`
before the run: prompt processing dominated the cost, and a section's subject is
*usually* settled by its opening. Definitions sections are exactly where "usually"
fails, and this corpus has 113 sections labelled by a heading rather than a
number, many of them definitional.

This is the distinctive risk of the technique and the reason the write-up prints
what the model wrote rather than only what it scored. The document title cannot
do this, because it is metadata and true by construction.

## A cache bug that hit exactly the cases the experiment was for

The first run of this was invalid and the counts said so quietly: 763 chunks
produced 727 cache entries and zero empties.

The cache key hashed the model name and the chunk text. The prompt also carries
the document title and the section label. This corpus contains matched
instruments whose articles are textually *identical*, so 61 chunks in 25 groups
collided - and they are the INS-FIN-001 / INS-FIN-002 pairs. Both twins were
receiving whichever context generated first, which read "insurance companies in
the UAE" and named no Takaful distinction at all.

The whole premise of trying this was that a generated sentence can say what a
shared title cannot. The cache was destroying that on precisely the pairs it was
meant to fix, and nothing about the run looked wrong.

After the fix, the same pair reads:

> `INS-FIN-001::Section 1, Article 5` — "...for **insurance companies**..."
> `INS-FIN-002::Section 1, Article 5` — "...for **takaful** insurance companies..."

Entries for chunks with unique text could not have collided, so 702 were migrated
forward and only the 61 ambiguous ones regenerated.

## Limits

- **One generator, and a small one.** A larger model would write better contexts,
  would not mistake a glossary for an actuary provision, and might well beat the
  title. This says a 0.5B model's contexts lose to free metadata here.
- **600 characters of each section** were shown to the model, which is what
  produced the Definitions failure. A full-section prompt was measured at 10.6s
  per chunk against 5.8s, or roughly two and a quarter hours for the corpus.
- One corpus, and one where documents have long, distinctive, informative titles.
  The comparison would look very different on documents titled "policy_v3".
- n=100: neither head-to-head comparison resolves, which is the same constraint
  `results/model_sweep.md` ran into.

## Reproducing

```
python scripts/run_contextual.py --generate   # ~75 minutes for 763 sections
python scripts/run_contextual.py              # evaluates from the cache
```
