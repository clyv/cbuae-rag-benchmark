# Can the system tell when it should not answer?

Measured 2026-08-27 with `scripts/run_answering.py`, over hybrid+reranker at
k=5. Raw output in `results/answering.json`.

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

## Abstention: the honest answer is that this does not work reliably

Relevance scores of the top passage:

| | min | median | max |
|---|---|---|---|
| Answerable (n=44) | −2.92 | 2.17 | 6.44 |
| Unanswerable (n=6) | −9.96 | −1.14 | 4.21 |

The distributions separate, but they overlap badly.

**AUC = 0.761, 95% interval 0.492 – 0.962.** The interval includes 0.5, which is
the value meaning no separation at all. With six unanswerable questions this
measurement cannot establish that the score distinguishes them from answerable
ones, even though the point estimate suggests it does.

### The trade-off curve

| Threshold | Unanswerable declined (of 6) | Answerable wrongly declined (of 44) |
|---:|---:|---:|
| −2.49 | 2 | 1 |
| −1.84 | 3 | 4 |
| 0.45 | 4 | 12 |
| 0.96 | 5 | 14 |
| 5.09 | 6 | 39 |

Declining five of the six costs fourteen wrongly refused answerable questions -
**32% of the benchmark refused to catch 83% of the unanswerable**. For a
compliance tool that ratio might still be the right choice, since a refusal is
recoverable and a confident wrong answer is not. It is not a solved problem
either way, and the README quotes the curve rather than a single flattering
operating point.

No threshold is used as a default in `answer_question`, and `threshold=None`
disables abstention entirely. Picking the value that looks best on these six
questions would be fitting a parameter to the test set.

## Why it fails, which is the useful part

The unanswerable questions were written as near-misses on subject matter, and
that is exactly what defeats a relevance score.

| Score | Question | Top retrieved section |
|---:|---|---|
| **4.21** | capital adequacy requirements for a finance company | `INS-FIN-001::Section 2, Article 3` — *Group Capital Adequacy* |
| 0.96 | minimum bank guarantee for an insurance broker | `INS-FIN-004::Article 1` |
| 0.14 | licence for an intermediary in the DIFC | `INS-LIC-001::Introduction` |
| −2.42 | capital adequacy ratio for a UAE bank under Basel | `INS-GOV-008::Introduction` |
| −7.00 | minimum benefits of a Dubai health insurance policy | `INS-CON-002::Article 15` |
| −9.96 | debt burden ratio for a residential mortgage | `INS-FIN-001::Section 1, Article 3` |

The worst case scores higher than most answerable questions. "Capital adequacy
requirements for a finance company" retrieves an article titled *Group Capital
Adequacy*, and a cross-encoder trained to judge topical relevance is right that
the passage is about capital adequacy. What it cannot see is that the passage
governs a different kind of entity.

**That is a scope question, not a relevance question**, and no threshold on a
relevance score will answer it. What would: checking whether the entity the
question asks about is one the retrieved instrument actually applies to. Every
document in this corpus has a Scope of Application section, so the material for
that check exists and it is the obvious next experiment.

The three questions about banking and Dubai health insurance score low and are
declined easily. The two hardest are the two closest to the corpus subject
matter, which is what the category was designed to produce.

## Limits of this measurement

- Six unanswerable questions. The AUC interval is nearly as wide as the range.
- One retrieval configuration, one k, one reranker model.
- The extractive citation figures are definitional, not empirical, and should
  never be quoted as evidence that the answering stage is faithful.
