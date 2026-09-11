# Indexing the instrument's own title

Measured 2026-09-11 with `scripts/run_doc_title.py`, over the 86 answerable
questions. Raw output in `results/doc_title.json`.

## Where this came from

Not from a technique list. `results/failures.md` classified every missed section
and found four cases where a matched instrument outranked its counterpart -
`INS-FIN-002::Section 2, Article 1` returned when the answer is in
`INS-FIN-001::Section 2, Article 1`. Those two carry the same article number, the
same heading, and near-identical bodies. The word that separates them is
*Takaful*, and it appears only in the document title.

Which `indexable_text` did not index. It concatenated `section_title`,
`section_heading` and the body - and `section_title` equals the document title
for **44 of 763 sections**. For the other 719, the name of the instrument a
provision belongs to was invisible to every retriever in the comparison.

## The result

recall@10, paired bootstrap over 10,000 resamples:

| system | baseline | with title | difference | 95% interval |
|---|---:|---:|---:|---|
| hybrid | 0.686 | 0.721 | +0.035 | +0.000 to +0.076 |
| **hybrid + reranker** | **0.750** | **0.802** | **+0.052** | **+0.012 to +0.093** |

On the production system the interval clears zero. Ten questions improved, two
worsened.

By category, hybrid + reranker:

| category | baseline | with title | change |
|---|---:|---:|---:|
| adversarial | 0.818 | 0.909 | **+0.091** |
| comparative | 0.462 | 0.538 | +0.077 |
| cross_section | 0.759 | 0.833 | +0.074 |
| cross_document | 0.824 | 0.853 | +0.029 |
| single_hop | 0.833 | 0.833 | +0.000 |

## The prediction was right about the direction and wrong about the mechanism

Written down before the run: *this should help `comparative` and `adversarial`,
where the twins compete, and do nothing or slightly hurt elsewhere.*

It helped nearly everywhere, and the biggest single category gain was
`cross_section`, which the twin story does not explain at all. Naming the
questions that moved makes the size of the error clear:

| moved | question | category | |
|---|---|---|---|
| up | Q091 | adversarial | 0.00 → 1.00 |
| up | Q010, Q077, Q082, Q083 | comparative | |
| down | Q081, Q084 | comparative | |
| up | Q076 | cross_document | 0.50 → 1.00 |
| up | Q016, Q032, Q060, Q061 | cross_section | all 0.50 → 1.00 |

**Of the four matched-instrument failures this change was designed to fix, one
moved.** Q077 (`INS-MOT-002` against `INS-MOT-003`) was corrected. Q009, Q011 and
Q012 - the `INS-FIN-001` / `INS-FIN-002` confusions that motivated the whole idea
- did not move at all.

The reason is visible in the titles:

> Insurance Authority Board Decision Number **(25)** of 2014 Pertinent to
> Financial Regulations for Insurance Companies
>
> Insurance Authority Board Decision Number **(26)** of 2014 Pertinent to
> Financial Regulations for **Takaful** Insurance Companies

Fifteen words of shared boilerplate around one distinguishing token. Adding that
title gives a retriever more signal, but not enough to flip a pair whose titles
are themselves near-duplicates.

So the change works, and it works for a different reason than the one that
suggested it: the title carries the instrument's *topic* - "Financial
Regulations", "Corporate Governance", "Risk Management" - and that helps match a
question to the right document generally. Nine of the ten improvements are that,
not twin disambiguation.

Worth keeping as a caution about mechanism. A defect was correctly identified, a
fix was correctly predicted to help, the measurement confirmed it, and the
explanation was still mostly wrong. Had the run only reported +0.052, the wrong
story would have been recorded as a validated one.

## What it costs

Two questions got worse (Q081, Q084, both `comparative`). Every chunk gains a
dozen words of formal boilerplate, which dilutes the body's own vocabulary in a
dense embedding and lengthens every document for BM25's length normalisation.
The hybrid-only row shows the cost more plainly than the reranked one:
`adversarial` *falls* 0.045 without the reranker and rises 0.091 with it. The
reranker reads the query and the passage together, so it can use the title as
context; the bi-encoder mostly absorbs it as noise.

That is an argument for the switch being a switch. It is not free, and on a
corpus with longer or less distinctive titles it could plausibly cost more than
it returns.

## Limits

- One corpus, and one where documents have long formal titles. A corpus of
  documents titled "Policy v3.docx" would get nothing from this.
- Off by default. Turning it on changes every number in the results table, so
  it is reported as a measured option rather than folded in silently - see the
  note on the same question in `results/chunking.md`.
- Two questions worsened and the reasons were not investigated individually.

## Reproducing

```
python scripts/run_doc_title.py --fast   # hybrid only
python scripts/run_doc_title.py          # both systems, ~10 minutes
```
