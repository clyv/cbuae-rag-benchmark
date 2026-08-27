### Overall, over the 44 answerable questions

| System | recall@5 | recall@10 | full_recall@10 | ndcg@10 | mrr | median latency |
|---|---|---|---|---|---|---|
| bm25 | 0.545 | 0.659 | 0.545 | 0.498 | 0.493 | 4 ms |
| dense | 0.477 | 0.625 | 0.432 | 0.500 | 0.575 | 28 ms |
| hybrid-rrf | 0.614 | 0.705 | 0.568 | 0.562 | 0.593 | 39 ms |
| hybrid+reranker | 0.625 | 0.727 | 0.568 | 0.599 | 0.653 | 1996 ms |

### recall@10 with 95% bootstrap intervals

| System | recall@10 | 95% interval |
|---|---|---|
| bm25 | 0.659 | 0.534 – 0.773 |
| dense | 0.625 | 0.511 – 0.727 |
| hybrid-rrf | 0.705 | 0.591 – 0.807 |
| hybrid+reranker | 0.727 | 0.625 – 0.830 |

### Does each step actually help? Paired differences in recall@10

Paired on the same questions, so this is tighter than comparing the
intervals above. An interval spanning zero means this benchmark cannot
separate the two systems.

| Comparison | difference | 95% interval | separates? |
|---|---|---|---|
| dense vs bm25 | -0.034 | -0.159 – +0.091 | no |
| hybrid-rrf vs dense | +0.080 | +0.000 – +0.170 | no |
| hybrid+reranker vs hybrid-rrf | +0.023 | -0.057 – +0.102 | no |
| | | | |
| hybrid-rrf vs bm25 | +0.045 | -0.045 – +0.125 | no |
| hybrid+reranker vs bm25 | +0.068 | -0.034 – +0.170 | no |
| hybrid+reranker vs dense | +0.102 | +0.023 – +0.193 | **yes** |

### recall@10 by category

| System | adversarial | comparative | cross_document | cross_section | single_hop |
|---|---|---|---|---|---|
| bm25 | 0.833 | 0.700 | 0.688 | 0.583 | 0.700 |
| dense | 0.500 | 0.400 | 0.812 | 0.639 | 0.600 |
| hybrid-rrf | 0.667 | 0.600 | 0.938 | 0.694 | 0.600 |
| hybrid+reranker | 0.667 | 0.400 | 0.875 | 0.778 | 0.700 |

`n` per category: adversarial 3, comparative 5, cross_document 8, cross_section 18, single_hop 10

### The 6 unanswerable questions are not scored here

Retrieval always returns its top k, so a retriever has no abstention
decision to make. Every figure on an item with no required evidence is
then fixed by construction: recall is 1.0 because nothing can be missed,
precision is 0.0 because nothing retrieved can be required. Neither
varies between systems and neither measures anything.

Abstention is a property of the answering stage, which is Phase 5. These
six questions exist to test whether it declines to answer rather than
confabulating from whatever retrieval handed it. A number for them now
would be an artefact of the metric definition, not a result.
