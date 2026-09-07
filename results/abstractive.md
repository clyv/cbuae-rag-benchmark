# The price of fluency

`results/abstention.md` reports citation validity of **1.000** for the shipped
answerer and says plainly that the figure is true by construction, not by
achievement: the answerer quotes the retrieved sections, so it cannot attribute
words that are not there. That page also promises the number exists to be a
baseline - the thing an abstractive generator has to be measured against.

This is that measurement.

Measured 2026-09-07 with `scripts/run_abstractive.py`, over hybrid+reranker at
k=4, on all 100 benchmark questions. Generator: **Qwen2.5-0.5B-Instruct**, CPU,
greedy decoding, 9.5 s per question. Raw output in `results/abstractive.json`.

## What the model did with 100 questions

| | |
|---|---|
| Declined to answer | **69** |
| Answered with at least one citation | 28 |
| Answered citing nothing | 3 |

The dominant result is not the citation score. It is that a 0.5B model handed
four relevant passages **refused two questions in three**, and 55 of those 69
refusals were on questions the corpus does answer and the retriever found.

## Refusal is not the same as judgement

| category | declined | |
|---|---|---|
| unanswerable | 14/14 | 1.00 |
| comparative | 11/13 | 0.85 |
| adversarial | 9/11 | 0.82 |
| single_hop | 11/18 | 0.61 |
| cross_section | 15/27 | 0.56 |
| cross_document | 9/17 | 0.53 |

Read the first row alone and the model looks like a perfect abstainer: every
unanswerable question refused, none missed. That reading is wrong, and the rest
of the table is why. A system that refuses *everything* also scores 14/14 there.
This one refuses 64% of answerable questions to buy that 100%, which as a single
operating point sits at Youden's J = 0.36 - well below the relevance threshold's
AUC of 0.806 on the same questions.

The ordering is still informative. The model declines least on `cross_document`
and `single_hop` and most on `comparative` and `adversarial`, which is what a
capability ceiling looks like rather than caution: the categories that need the
model to hold two passages against each other are the ones it gives up on.

## Citation validity, on the 28 answers that cited anything

74 citations were issued across those 28 answers.

| | abstractive | extractive baseline |
|---|---|---|
| Grounded (cited section was retrieved) | 1.000 | 1.000 |
| Supported, lenient (4 shared content words) | 0.851 | - |
| Supported, strict (60% of the claim's vocabulary) | **0.557** | **0.972** |

**Grounded 1.000 is a design artifact and should not be quoted as a result.**
Passages are numbered in the prompt and the model answers with `[2]`; the parser
drops any tag outside the range instead of clamping it. So an invented reference
cannot survive as a wrong citation - it disappears, and shows up as a lower
citation count rather than a lower grounded score. Prompting a model to emit a
free-text section identifier would put that failure mode back and grounded would
stop being 1.000. That design choice is worth more than the metric it produces.

The distance between 0.851 and 0.557 is worth as much as either number. Four
shared content words is nothing in a corpus where "company", "board" and
"requirements" appear on every page, so the lenient figure mostly measures the
subject matter rather than the claim. The strict figure is the honest one, and
the gap is a warning about how much a citation metric depends on its threshold.

Supported is where fluency costs something: **0.557 against 0.972** at the same
threshold. Nearly half the claims the model wrote could not be traced back to
the section it hung them on.

## The failure is over-attribution, not fabrication

Reading the failures, almost none are invented regulation. The model copies a
passage closely and then tags the sentence `[2][3]` - crediting one claim to two
or three sections when only one of them contains it. The extra citations look
like thoroughness and are unsupported by construction.

Splitting the 28 answers on whether any claim carries more than one number:

| | answers | mean supported (strict) |
|---|---|---|
| Every claim names one passage | 14 | **0.738** |
| At least one claim names several | 14 | **0.375** |

Exactly half the answers do it, and doing it roughly halves the support. This is
a specific, fixable defect rather than a general unreliability: a prompt that
demands one source per sentence, or a validator that requires each tag in a
group to support the claim independently, would attack it directly. Neither is
tried here - the point of the measurement was to find out what breaks, and this
is what broke.

Where it did cite, the citations were largely the right ones: **24 of the 28**
answers named at least one section the benchmark requires. Retrieval put the
evidence in front of the model; the gap is in what the model then wrote about it.

## A first measurement was discarded

The run this page reports is the second. The first was thrown away because the
citation parser was wrong, and the way it was wrong is worth recording.

The prompt asks the model to end each sentence with the numbers of the passages
it used, so the model writes `Claim A. [1] Claim B. [2]`. The parser split on
sentence boundaries, which put the full stop *before* the tag - producing the
segments `Claim A.`, `[1] Claim B.`, and `[2]`. Citation [1] was then checked
against **Claim B's** words, and citation [2] against nothing at all. Both make a
correct citation score as unsupported.

That defect moved the headline number without any model behaving differently:
0.616 strict before the fix, 0.557 after, and 0.729 lenient before against 0.851
after. It was found by writing a test asserting that a citation's quote is the
claim it is attached to - not by reading the output, where the wrong answer
looked entirely plausible.

The parser now works on tag *clusters* rather than sentences: a tag belongs to
the text before it, or the text after it when the model put the tag first, and
`[2][3]` is one act of citation sharing one claim. `tests/test_abstractive.py`
pins both failure shapes.

## What this number is and is not

**0.557 is a lower bound on abstractive citation validity, not an estimate of
it.** It is what a 0.5B parameter model does, and model size is the binding
constraint here - the 69 refusals say so directly. A 7B model, or a hosted
frontier model, would very likely refuse far less and support far more. Nothing
here licenses a claim about abstractive generation in general.

What it does establish, on this corpus with these questions:

1. The gap between quoting and paraphrasing is real and it is large. It is not
   an artifact of a bad prompt or a broken parser - grounded is 1.000, so the
   model's references are well-formed. The prose is what drifts.
2. Reporting the extractive 1.000 without this comparison would have been
   misleading, which is exactly why `abstention.md` said so at the time.
3. The measurement runs on the same free, local footprint as everything else in
   this project. Swapping `AbstractiveGenerator(model_name=...)` for a larger
   model re-runs it in one command, so the bound can be tightened later without
   redesigning anything.

## Reproducing

```
python scripts/run_abstractive.py
```

Downloads the model on first run (~1 GB), then roughly 16 minutes for 100
questions on CPU. `--limit N` for a smaller pilot, `--k` for a different number
of passages.
