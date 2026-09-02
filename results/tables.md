### Overall, over the 86 answerable questions

| System | recall@5 | recall@10 | full_recall@10 | ndcg@10 | mrr | median latency |
|---|---|---|---|---|---|---|
| bm25 | 0.471 | 0.581 | 0.465 | 0.442 | 0.448 | 4 ms |
| dense | 0.552 | 0.680 | 0.523 | 0.542 | 0.579 | 44 ms |
| hybrid-rrf | 0.570 | 0.686 | 0.547 | 0.530 | 0.558 | 56 ms |
| hybrid+reranker | 0.645 | 0.750 | 0.593 | 0.626 | 0.674 | 1042 ms |

### recall@10 with 95% bootstrap intervals

| System | recall@10 | 95% interval |
|---|---|---|
| bm25 | 0.581 | 0.494 – 0.674 |
| dense | 0.680 | 0.599 – 0.756 |
| hybrid-rrf | 0.686 | 0.605 – 0.767 |
| hybrid+reranker | 0.750 | 0.680 – 0.820 |

### Does each step actually help? Paired differences in recall@10

Paired on the same questions, so this is tighter than comparing the
intervals above. An interval spanning zero means this benchmark cannot
separate the two systems.

| Comparison | difference | 95% interval | separates? |
|---|---|---|---|
| dense vs bm25 | +0.099 | +0.006 – +0.198 | **yes** |
| hybrid-rrf vs dense | +0.006 | -0.070 – +0.081 | no |
| hybrid+reranker vs hybrid-rrf | +0.064 | -0.012 – +0.134 | no |
| | | | |
| hybrid-rrf vs bm25 | +0.105 | +0.035 – +0.174 | **yes** |
| hybrid+reranker vs bm25 | +0.169 | +0.087 – +0.250 | **yes** |
| hybrid+reranker vs dense | +0.070 | +0.006 – +0.134 | **yes** |

### recall@10 by category

| System | adversarial | comparative | cross_document | cross_section | single_hop |
|---|---|---|---|---|---|
| bm25 | 0.773 | 0.385 | 0.618 | 0.519 | 0.667 |
| dense | 0.864 | 0.385 | 0.735 | 0.648 | 0.778 |
| hybrid-rrf | 0.818 | 0.423 | 0.853 | 0.593 | 0.778 |
| hybrid+reranker | 0.818 | 0.462 | 0.824 | 0.759 | 0.833 |

`n` per category: adversarial 11, comparative 13, cross_document 17, cross_section 27, single_hop 18

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
