# Does an answer keep the obligation the regulation stated?

Measured 2026-09-11 with `scripts/run_abstractive.py`, over the same 100
benchmark questions. Raw output in `results/abstractive.json`.

## Why this metric exists

Regulation is not prose with facts in it. Almost every sentence carries a
*force*: a company **shall** maintain a risk register, **may** outsource the
function, **must not** delegate the Board's responsibility, **should** review it
annually. Those four words are the content of a compliance obligation. A system
that reports one where the text says another has not made a wording error - it
has told a regulated firm the wrong thing about what is required of it.

Standard RAG metrics cannot see this. Citation validity asks whether a claim's
words appear in the section it cites, and:

> "an insurer **may** appoint an actuary"
> "an insurer **shall** appoint an actuary"

share every content word but one. A claim can score a perfect citation while
inverting the obligation. LLM-judged faithfulness inherits the same blindness and
adds its own: published measurements put RAGAS-style judgements at around 0.55
correlation with human assessment.

This is a domain-specific metric for a domain-specific failure, and the corpus
justifies it - 1,483 uses of *shall*, 1,355 of *must*, 578 of *may*, 339 of
*should*, with 159 sections mixing mandatory and permissive language in the same
provision.

## The result

| | abstractive (Qwen2.5-0.5B) | extractive |
|---|---:|---:|
| Claims made | 74 | 297 |
| Claims stating an obligation | 51 | 240 |
| Preserved | 46 | 240 |
| Strengthened | 1 | 0 |
| **Weakened** | **4** | **0** |
| **Obligation fidelity** | **0.902** | **1.000** |

The extractive 1.000 is true by construction, as with citation validity - a quote
carries whatever force its source carried. It is the bar, not an achievement.

## The interesting part: this disagrees with citation validity

The same run measured citation support at **0.557** strict. Obligation fidelity
is **0.902**. Those are not two views of one quantity:

- The model is **bad at being traceable** - nearly half its claims cannot be tied
  back to the section cited at a 60% vocabulary threshold.
- The model is **good at preserving obligation force** - nine times in ten, when
  it says a thing is required, the source does require it.

A system optimised on citation overlap alone would look far worse than it is on
the axis a compliance officer cares about, and a system optimised on obligation
fidelity alone would look far better than it is on traceability. Reporting one
number for "faithfulness" hides both.

## The four that went the wrong way

Direction matters more than count. Strengthening tells a firm to do something it
need not - wasteful. **Weakening tells a firm it may skip something it must do**,
and that is the one that ends in an enforcement action.

Four of the five errors are weakenings. A real one:

> **Source:** "The company **shall** provide electronic claim forms for
> submitting claims and uploading electronic copies of the claim documents..."
>
> **Model wrote:** "The website **should** provide electronic claim forms for
> submitting claims and uploading electronic copies of the claim documents..."

*Shall* became *should*. A binding requirement was reported as advisory good
practice, and every other word in the sentence is the source's own - so citation
validity passes it comfortably. This is precisely the case the metric was built
for, and it is the strongest single argument in this repository for why the
shipped answerer quotes instead of paraphrasing.

## Why 23 of 74 claims are excluded

A claim that states no obligation at all - "the actuary is appointed annually" -
has no force to get wrong. Those are counted separately rather than as passes,
because a metric that rewards saying nothing is not measuring faithfulness. The
denominator is force-bearing claims only.

## How the classifier works, and what would break it

Negated forms are matched first and removed before anything else is looked for.
"may not" contains "may"; "shall not" contains "shall". Matching the positive
forms first would read every prohibition as its own opposite - the single most
damaging error this module could make, and the one pinned hardest in
`tests/test_obligation.py`.

A claim counts as preserved if its force is one the source *carries*, not merely
the source's strongest. A section that mandates one thing and permits another
supports a claim about either; comparing against the strongest alone would score
the permissive half as a weakening.

## Limits

- **Pattern matching, not understanding.** "shall" inside a quoted definition, or
  in a sentence about what a *policyholder* shall do rather than the insurer, is
  scored the same as a direct obligation. The classifier sees force, not who
  bears it.
- **No scope.** "The Board shall approve" and "the actuary shall approve" carry
  the same force and different meanings. This measures whether the modality
  survives, not whether the duty-holder does.
- **51 force-bearing claims** is a small denominator, because the 0.5B generator
  declined 69 of 100 questions. The 0.902 has a wide interval that is not
  computed here; a larger model answering more questions would tighten it and
  probably move it.
- One generator. Whether obligation fidelity rises or falls with model size is
  unmeasured, and it is not obvious which way it goes: a bigger model writes more
  fluently, which is exactly what introduces paraphrase of modal verbs.

## Reproducing

```
python scripts/run_abstractive.py
```
