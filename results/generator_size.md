# A three times larger generator scores worse, and the metric is why

Measured 2026-09-11 with `scripts/run_abstractive.py --model Qwen/Qwen2.5-1.5B-Instruct`,
over the same 100 questions. Raw output in
`results/abstractive-qwen2.5-1.5b-instruct.json`.

## The prediction this falsifies

`results/abstractive.md` said, in bold:

> **0.557 is a lower bound on abstractive citation validity, not an estimate of
> it.** It is what a 0.5B parameter model does... A 7B model, or a hosted
> frontier model, would very likely refuse far less and support far more.

Both halves are now measured, and both are wrong at this step in size.

## The result

| | Qwen2.5-0.5B | Qwen2.5-1.5B |
|---|---:|---:|
| Declined | 69 | **66** |
| Answers carrying a citation | 28 | 31 |
| Citations issued | 74 | 69 |
| Grounded | 1.000 | 1.000 |
| Supported, lenient | 0.851 | 0.688 |
| **Supported, strict (60%)** | **0.557** | **0.366** |
| **Obligation fidelity** | **0.902** | **0.944** |
| Claims that weaken an obligation | 4 | **1** |
| Median claim length | 31 words | **20 words** |
| Answers over-attributing | 14 of 28 | 8 of 31 |

Bootstrapped over answers, 10,000 resamples:

| | supported, strict | 95% interval |
|---|---:|---|
| 0.5B | 0.557 | 0.443 to 0.676 |
| 1.5B | 0.366 | 0.245 to 0.487 |
| **difference** | **−0.191** | **−0.358 to −0.025** |

The interval clears zero. The larger model is genuinely worse on the citation
metric, and refusals barely moved: 69 to 66, not the collapse predicted.

## Why: the metric rewards copying

**Median claim length falls from 31 words to 20.** The 1.5B writes shorter,
denser claims — it *summarises* where the 0.5B *copies*.

`supported_strict` asks whether 60% of a claim's vocabulary appears in the cited
section. A near-verbatim 31-word restatement passes that easily. A genuine
20-word paraphrase does not, however faithful it is. The metric cannot tell the
difference between "said something the source does not" and "said the same thing
in different words".

Seen from the other end, the whole ladder is a ladder of verbatimness:

| | supported, strict | what it does |
|---|---:|---|
| Extractive answerer | 0.972 | copies the source |
| Qwen2.5-0.5B | 0.557 | copies most of it |
| Qwen2.5-1.5B | 0.366 | paraphrases |

That is not a quality ranking. It is a measurement of how much of the source
survives word-for-word, which is what the number was built to be — and
`results/abstractive.md` called it "the price of fluency" without noticing that
the price is charged for fluency itself, not only for unfaithfulness.

## The semantic metric moves the other way

`results/obligation.md` exists because citation overlap is blind to the thing
regulation is made of. That metric asks whether a claim keeps the *force* the
source stated — mandatory, prohibitive, permissive, advisory — and it does not
care what words carry it.

It goes **up** with model size: 0.902 to 0.944, with weakenings falling from four
to one. The dangerous error — telling a firm it *may* skip something it *must*
do — happened once in 36 force-bearing claims rather than four in 51.

Over-attribution also improves: 14 of 28 answers tagged one claim to several
sections, against 8 of 31.

So the two metrics dissociate cleanly, and in the directions that make sense:

- **Lexical overlap punishes the better model**, because it paraphrases.
- **Obligation fidelity rewards it**, because it understands modality better.

A project reporting only "faithfulness" would have concluded the 1.5B is
substantially worse. A project reporting only obligation fidelity would have
concluded it is better. Both numbers are correct and they measure different
things, which is the argument for having built the second one.

## What this changes about the earlier write-up

`results/abstractive.md` has been corrected. The claim that 0.557 is a floor
tied to model size does not survive one step up in size. The honest statement is
narrower:

> 0.557 is what a 0.5B model's *copying* scores on a metric that rewards
> copying. Whether a larger model is more faithful cannot be read off it, and on
> the one semantic metric available here, the larger model is.

## Limits

- **One step in size**, 0.5B to 1.5B, same family, same prompt, same quantised
  arithmetic. A 7B or a frontier model may behave differently again, and the
  trend from two points is not a trend.
- **bfloat16 for the 1.5B** against float32 for the 0.5B, because this machine
  had 3.4 GB free and float32 would need 6 GB. Quantisation could account for
  some of the difference and is not separated out here.
- **36 force-bearing claims** is a small denominator for the obligation figure,
  and no interval is computed for it.
- Both models decline about two thirds of questions, so every number describes
  the third they answer.

## Reproducing

```
python scripts/run_abstractive.py                                        # 0.5B
python scripts/run_abstractive.py --model Qwen/Qwen2.5-1.5B-Instruct --dtype bfloat16
```

Each writes to its own file, so one generator cannot overwrite another's numbers.
