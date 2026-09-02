# Can the system tell when it should not answer?

Measured 2026-09-02 with `scripts/run_answering.py`, over hybrid+reranker at
k=5, on 100 benchmark questions. Raw output in `results/answering.json`.

## Citation validity

| | |
|---|---|
| Citations grounded (section was in the retrieved context) | **1.000** |
| Citations supported (quoted text appears in that section) | **1.000** |

Both are 1.0 **by construction, not by achievement**. The answerer is
extractive: it quotes the retrieved sections and attributes each quote, so it
cannot cite a section it did not retrieve or attribute words that are not there.

The number is reported because it is the baseline an abstractive generator has
to be measured against. A model that paraphrases becomes more readable and can
score below 1.0 on either row; the gap is the price of fluency, and it is only
visible if the extractive figure is on the page.

## Abstention: now established, and it was not at n=6

Relevance scores of the top passage:

| | min | median | max |
|---|---|---|---|
| Answerable (n=86) | -7.98 | 1.63 | 7.32 |
| Unanswerable (n=14) | -9.96 | -1.24 | 4.21 |

**AUC = 0.806, 95% interval 0.671 - 0.915.** The interval clears 0.5, so the
relevance score genuinely separates questions the corpus cannot answer from
those it can.

The earlier measurement, on 6 unanswerable questions, gave **AUC 0.761 with an
interval of 0.492 - 0.962** - straddling the value that means no separation at
all. The point estimate barely moved. What changed is that 14 negatives can
support the claim and 6 could not, which is the same lesson the retrieval
results taught: the instrument was the limit, not the system.

### The trade-off curve

| Threshold | Unanswerable declined (of 14) | Answerable wrongly declined (of 86) |
|---:|---:|---:|
| -3.28 | 3 | 4 |
| -2.53 | 5 | 7 |
| -1.43 | 7 | 11 |
| -0.13 | 11 | 21 |
| 0.96 | 13 | 32 |
| 5.90 | 14 | 81 |

Declining half the unanswerable questions costs 7 of 86 answerable ones - a
better ratio than the 5-for-14 measured on the smaller set, though the earlier
figure was too noisy to compare against directly.

No threshold is used as a default in `answer_question`, and `threshold=None`
disables abstention entirely. Picking the value that looks best on these
questions would be fitting a parameter to the test set.

## Why the hard cases are hard

The unanswerable questions were written as near-misses on subject matter, and
that is exactly what defeats a relevance score. The worst case scores 4.21,
higher than most answerable questions:

> "What are the capital adequacy requirements for a finance company?"
> retrieves `INS-FIN-001::Section 2, Article 3`, titled *Group Capital Adequacy*.

A cross-encoder trained to judge topical relevance is right that the passage is
about capital adequacy. What it cannot see is that the passage governs a
different kind of entity.

**That is a scope question, not a relevance question**, and no threshold on a
relevance score will answer it. What would: checking whether the entity the
question asks about is one the retrieved instrument actually applies to. Every
document in this corpus has a Scope of Application section, so the material for
that check exists and it is the obvious next experiment.

## Limits of this measurement

- Fourteen unanswerable questions. The AUC interval is still 0.24 wide.
- One retrieval configuration, one k, one reranker model.
- The extractive citation figures are definitional, not empirical, and should
  never be quoted as evidence that the answering stage is faithful.
