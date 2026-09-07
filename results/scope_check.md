# Can a scope check catch what relevance cannot? No.

Measured 2026-09-02 with `scripts/scope_check.py`, over the same 100 benchmark
questions. Raw output in `results/scope_check.json`.

## The hypothesis

Abstention on relevance alone reaches AUC 0.806, and the residual errors share a
shape: a question about an entity the corpus does not govern retrieves a passage
about the right *topic*. The worst case scores 4.21, higher than most answerable
questions:

> "What are the capital adequacy requirements for a finance company?"
> retrieves `INS-FIN-001::Section 2, Article 3`, titled *Group Capital Adequacy*.

The cross-encoder is right that the passage concerns capital adequacy. It cannot
see that the passage governs a different kind of entity. That is a question about
**scope**, and the corpus states scope explicitly: every instrument says near its
start who it binds.

So: build a scope profile per document from its framing sections - preamble,
introduction, objective, scope, definitions - and score the question against that
profile with the same cross-encoder. Where relevance and scope disagree, suspect
an out-of-scope question.

## Result

| Strategy | AUC | 95% interval |
|---|---:|---|
| **Relevance only** | **0.806** | 0.664 – 0.918 |
| Scope only | 0.575 | 0.393 – 0.757 |
| Relevance + scope | 0.675 | 0.512 – 0.823 |
| min(relevance, scope) | 0.575 | 0.392 – 0.752 |

**Every combination is worse than relevance alone.** Scope on its own is barely
above chance, and adding it to relevance destroys about 13 points of AUC.

## Why it fails, which is the part worth keeping

| | median scope score |
|---|---:|
| Answerable questions | −10.06 |
| Unanswerable questions | −9.91 |

The two distributions are indistinguishable, and both sit at the floor. The
cross-encoder scores *every* question poorly against framing text, because
framing text is not answer-shaped: "This Regulation and the accompanying
Standards apply to all Companies" does not look like a passage that answers a
question, whatever the question is.

The model was trained to judge whether a passage answers a query. It was not
trained to judge whether a query falls inside a jurisdiction, and the second task
is not the first task applied to different text.

The signal does exist in the individual case that motivated this. Q050 scores
4.21 on relevance and −10.42 on scope, the widest gap in the set. But answerable
questions show the same gap, because their scope scores are equally low, so the
disagreement carries no information across the population.

## What this rules out, and what it leaves

Ruled out: reusing the reranker as a scope classifier by pointing it at different
text. The cheap version of this idea does not work, and now there is a number
saying so rather than an untested intuition.

Still open, and now better specified - a real scope check needs a mechanism that
does entailment rather than relevance:

- extract the entity a question asks about, extract the entities an instrument
  binds, and compare them directly;
- or use a natural language inference model, where "this question concerns a
  finance company" against "this instrument applies to insurance companies" is
  a contradiction rather than a low-relevance pair.

Both are larger pieces of work than reusing a model already in the pipeline,
which is exactly why the cheap version was worth testing first.

## Limits of this measurement

- Fourteen unanswerable questions. Every interval here is wide enough that a
  small real effect could hide, though not one large enough to change the
  conclusion that combining hurts.
- One cross-encoder, one profile construction, 1,400 characters of framing text.
- Framing sections were used rather than a dedicated Scope of Application
  section because only 21 of 46 documents have one the parser can identify.
