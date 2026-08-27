# Does label verification actually catch errors?

Measured 2026-08-25. Reproduce with `python scripts/negative_control.py --score`
against `benchmark/control/`.

## Why this was run

All 50 benchmark labels were LLM-drafted and human-verified, and verification
changed none of them. Two readings fit that record: the drafts were sound, or
the check was confirmatory rather than adversarial. The difference matters,
because the project's one substantive claim is that a person established the
ground truth.

A sample of 16 questions was drawn, 8 corrupted, all shuffled and reviewed blind.

## Result

| | count | 95% CI |
|---|---:|---|
| Corrupted items caught | 5 of 8 | 31% – 86% |
| Untouched items passed | 7 of 8 | |
| False alarms | 1 of 8 | 2% – 47% |

**Verification catches roughly three errors in five.** The interval is wide -
eight corrupted items cannot support a precise figure - but the result is
clearly neither perfect nor useless.

The single false alarm matters as much as the catches. A reviewer who marked
everything sound would have scored 3 of 8 by luck and zero false alarms; one
correct label being challenged shows the review was doing work rather than
rubber-stamping.

## What this says about the real benchmark

If verification catches an error with probability 0.62, and no corrections were
made across the real 50 labels, then the probability of missing every error is
`0.38^E` for `E` true errors:

| true errors hiding | probability none was caught |
|---:|---:|
| 0 | 1.00 |
| 1 | 0.38 |
| 2 | 0.14 |
| 3 | 0.05 |
| 4 | 0.02 |

**Four or more undetected errors can be ruled out at the 5% level; zero to three
cannot.** So the honest statement is not "the labels are correct" but "the
labels contain at most about three errors, and probably fewer" - a bound, from a
measurement, rather than an assurance.

That is a weaker claim than the project would like and a much stronger one than
it could otherwise make.

## Which errors got through

n = 1 per shape apart from swaps, so this is suggestive, not established.

| corruption | caught |
|---|---:|
| swapped a section for its neighbour | 4 of 5 |
| added a superfluous neighbour | 1 of 1 |
| **dropped a required section** | **0 of 1** |
| **gave an unanswerable item evidence** | **0 of 1** |

The two misses are the two most damaging failure modes, which is unlikely to be
coincidence:

- **A dropped section is an incomplete label.** The question then cannot be
  answered from its own evidence set, and every system is marked wrong for
  retrieving correctly. Spotting it requires noticing an *absence*, which is
  harder than judging whether a section that is present belongs.
- **An unanswerable item given evidence** stops testing abstention and starts
  testing retrieval, silently changing what the item measures.

Both are errors of omission in the reviewing, not of judgement: the reviewer was
checking whether the listed sections belonged, which catches swaps and additions
but not gaps.

## Actions taken

1. All six `unanswerable` items re-checked for the Q050 shape.
2. The 33 multi-section labels re-checked for completeness specifically - is
   anything *missing* - rather than for whether the listed sections belong.
3. The five items citing `INS-GOV-003::Article 3` re-checked, that being where
   the missed swap occurred.

## Limits of this measurement

- Eight corrupted items. Every figure here has a wide interval.
- One reviewer, who also verified the original labels and knew a control was
  running, though not which items were corrupted.
- Corruptions were generated mechanically. Real drafting errors may be
  distributed differently.
