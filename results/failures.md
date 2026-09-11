# Why retrieval misses what it misses

Measured 2026-09-11 with `scripts/analyse_failures.py`, over the recorded output
of hybrid+reranker at k=10. Raw output in `results/failures.json`.

`0.750` recall@10 is a number you can put in a README. It is not a reason, and it
does not tell you what to build next. This classifies every miss.

## What is missed

| | |
|---|---|
| Found every required section | **51** of 86 |
| Found some but not all | 27 |
| Found none | 8 |

Those 35 incomplete questions leave **39 missed sections** between them.

## Why

| | missed sections | |
|---|---:|---|
| **Same document, wrong article** | **24** | **62%** |
| No signal | 8 | 21% |
| Matched instrument outranked | 4 | 10% |
| Same label, unrelated instrument | 2 | 5% |
| Lexical gap | 1 | 3% |

## The dominant failure is not the one the project assumed

Nearly two thirds of misses are **the right instrument, the wrong provision
inside it**. The system knows which regulation governs; it cannot pick which of
that regulation's articles answers the question. By category:

| category | same-document misses |
|---|---:|
| cross_section | 13 |
| comparative | 4 |
| cross_document | 4 |
| adversarial | 2 |
| single_hop | 1 |

`cross_section` dominating is exactly right by construction - those questions
require two provisions of one instrument, so there are two chances to pick the
wrong sibling. But it reframes what would improve the system. The README's
existing narrative is about *paraphrase* difficulty, and that story is not what
the misses are made of:

> **Lexical gap explains one missed section out of 39.**

The six paraphrase questions the README highlights are real, but they are
questions the strong system *solves* - BM25 finds none of them, hybrid+reranker
finds five at rank 1. Paraphrase is where reranking earns its place, not where
the remaining failures live. Vocabulary is not the problem any more; telling
sibling articles apart is.

## Matched instruments, and being honest about how many

This corpus contains matched pairs: a conventional instrument and its Takaful
counterpart, a Regulation and its Standards, two motor policies. They carry the
same article numbers, the same headings, and near-identical bodies.

Four misses are that failure, and all four are genuine pairs:

| question | wanted | got instead |
|---|---|---|
| Q009 | `INS-FIN-001::Section 2, Article 1` | `INS-FIN-002::Section 2, Article 1` |
| Q011 | `INS-FIN-001::Section 2, Article 4` | `INS-FIN-002::Section 2, Article 4` |
| Q012 | `INS-FIN-001::Section 2, Article 1` | `INS-FIN-002::Section 2, Article 1` |
| Q077 | `INS-MOT-002::Chapter Four` | `INS-MOT-003::Chapter Four` |

A first version of this analysis called these "twins" on the strength of a shared
section label alone, and counted six. Two of those were coincidence - "Article 4"
exists in a sanctions resolution and in a motor decision, and a retriever
returning one when the other was wanted has not confused a matched pair, it has
just missed. They are now counted separately, and the headline category is 10%
rather than 15%. The looser rule made the finding look better than it is.

This is the same conclusion `results/scope_check.md` reached from the other
direction: the residual errors are about **which entity an instrument governs**,
not about topic.

## What this rules in

The taxonomy immediately suggested a defect, and the defect turned out to be
real. The four matched-instrument misses have one distinguishing word between
right and wrong - *Takaful* - and it appears only in the document title. But
`indexable_text` indexed the section title, the section heading and the body,
**not the document title**, and `section_title` equals the document title for
only 44 of 763 sections.

So for 719 sections, the one word that separates an instrument from its
counterpart was invisible to every retriever in the comparison. That is measured
in `results/doc_title.md`.

Set expectations honestly: this targets 10% of missed sections, so the ceiling
is about four sections across four questions. It is a real defect with a small
prize, not a fix for the 62%.

## Limits of this classification

- The categories are assigned by rule, not by reading. "No signal" in particular
  is a bucket for misses with no cheap explanation, not a diagnosis.
- `lexical gap` uses a 10% content-word overlap threshold between question and
  target section. The threshold is arbitrary; a looser one would move sections
  out of "no signal" and into it.
- Classification runs on the top 10. A section that ranked 11th and one that
  ranked 900th are both "missed" here, and they are not the same problem. The
  candidate-depth version of this - did the reranker ever see it - needs a
  re-run rather than recorded output.
- One system. BM25 and dense miss more, and may miss differently; the script
  takes `--system` to check.

## Reproducing

```
python scripts/analyse_failures.py
python scripts/analyse_failures.py --system bm25
```

Needs no models and no corpus rebuild - it reads `results/<system>.json`.
