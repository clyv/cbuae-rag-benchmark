# Is the provision this answer cites actually law yet?

Measured 2026-09-11 with `scripts/analyse_temporal.py`, as of 2026-09-11, over
recorded output. Raw output in `results/temporal.json`.

## The gap

Every other metric in this project is timeless. Recall asks whether the right
section was found. Citation validity asks whether the words are really in it.
Abstention asks whether the corpus can answer at all. None of them asks the
question a compliance officer asks first:

> Is this the law today?

Four instruments in the corpus are listed by the Rulebook as **In-Force** while
carrying a commencement date in the future:

| instrument | commences |
|---|---|
| INS-TAK-001 | 2026-09-14 |
| INS-TAK-006 | 2027-07-15 |
| INS-TAK-007 | 2027-07-15 |
| INS-TAK-008 | 2027-07-15 |

They are indexed on purpose - three Takaful standards on adjacent subject matter
are exactly the near-miss distractors that separate a good retriever from a bad
one - and they are barred from the answer key, because deciding which instrument
governs an obligation today is a legal judgement this project declines to make.

Being out of the answer key does not stop a retriever returning them.

## The exposure

Questions where the top 10 contains a section whose instrument has not commenced:

| system | questions | premature sections | at rank 1 |
|---|---:|---:|---:|
| BM25 | 15/100 | 23 | 1 |
| Dense | 17/100 | 38 | 2 |
| Hybrid RRF | 11/100 | 23 | 2 |
| **Hybrid + reranker** | **7/100** | **16** | **2** |

**Better retrieval more than halves the exposure and does not remove it.** The
shipped system still puts a provision that is not law at **rank 1 on two
questions**, with nothing on the page saying so. Ranking quality is not a
temporal check, and improving it will never become one.

The seven, on the shipped system:

| question | category | first premature rank |
|---|---|---:|
| Q011 | comparative | **1** |
| Q084 | comparative | **1** |
| Q010 | comparative | 2 |
| Q012 | adversarial | 2 |
| Q028 | comparative | 2 |
| Q009 | comparative | 3 |
| Q045 | unanswerable | 6 |

Five of the seven are `comparative`, which is what the shape of the corpus
predicts: a question comparing conventional and Takaful treatment reaches for
Takaful instruments, and three of the four premature ones are Takaful standards.
Q009, Q011 and Q012 are also the questions where a matched instrument outranked
its counterpart in `results/failures.md` - the same small set of questions is the
hot spot for both failure modes.

## Unknown is not the same as future

Four other instruments - INS-GOV-005, INS-GOV-007, INS-GOV-008, INS-OTH-004 -
publish no date at all. They are reported separately and **not** counted as
premature.

Collapsing the two would be wrong in both directions. Treating a missing date as
"not in force" would suppress four perfectly citable documents; treating it as
"in force" would assert something the Rulebook does not print. `in_force_on`
returns `None` for them and makes the caller decide, which is the same posture
the corpus notes already take.

## What this is, and what it is not

It reads the commencement date the Rulebook prints and compares it to a date.
That is the arithmetic underneath the legal question, not the legal question:

- It does not interpret transition provisions, grandfathering, or partial
  commencement.
- It cannot tell that an article inside an in-force instrument was itself amended
  later - the corpus has one date per instrument, not per provision.
- It has no notion of an instrument being *repealed*, because the Rulebook's
  insurance index lists none and the registry has no field for it.

So this does not decide which instrument governs. It flags when a system is
citing something that has not commenced, which is a prerequisite for that
judgement rather than a substitute for it.

## Why it is worth having at all

The corpus was collected on 2026-08-24 and the numbers above are computed for
2026-09-11. Nothing about the system changed in between - but INS-TAK-001
commences on 2026-09-14, so in three days one of these four rows stops being a
false citation and becomes a correct one, and this page's numbers change without
a line of code changing.

That is the argument for a date-aware check existing at all. A retrieval system
over regulation is not a static artifact: it is a claim about a moving body of
law, and it has no way to notice when the law moves underneath it.

## Reproducing

```
python scripts/analyse_temporal.py
python scripts/analyse_temporal.py --as-of 2027-08-01
```

The second is worth running: with every Takaful standard commenced, the exposure
goes to zero and the same corpus becomes temporally clean.
