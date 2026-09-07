# ReguLens

**A retrieval evaluation over UAE insurance regulatory documents.**

Most RAG projects ship a chatbot and assert that it works. This one ships a
benchmark and measures four retrieval architectures against it. The chatbot is
the demo; the evaluation is the project.

> **Status:** Phases 1-5 complete. Corpus, benchmark, the four-system
> comparison, and grounded answering with citation validation and abstention are
> all measured and reported below. Phase 6 (cross-reference graph) is optional
> and not built.

---

## The question

Regulatory answers are rarely contained in a single passage. A question about a
broker's risk-management obligations may depend on one article establishing the
duty, another defining an exception, and a third in a separate instrument
setting the reporting requirement. Keyword search retrieves documents; it does
not reliably assemble the complete evidence needed to answer.

**Does hybrid retrieval with reranking improve evidence recall on multi-hop
regulatory questions, compared with lexical or dense retrieval alone?**

## What is measured, and what is not

This project measures **retrieval quality**: given a question, did the system
surface the document sections a human labelled as necessary to answer it?

This project does **not** claim legal accuracy. Determining whether an answer
is legally correct requires qualified compliance expertise, which the author
does not have and does not claim. The benchmark's ground truth is *which
sections are required*, not *what the law says*. Every metric below follows
from that choice.

This is a deliberate design decision, not a hedge. Evidence recall is
objectively checkable by anyone with the corpus open. Legal correctness is not.

**This repository is a technical portfolio project. Nothing in it is legal,
regulatory, or compliance advice.**

---

## Corpus

| | |
|---|---|
| Source | CBUAE Rulebook, Insurance section |
| Documents | 46 |
| Sections after parsing | 763 |
| Chunks indexed | 954 (512-word budget, 64-word overlap) |
| Words | 206,705 |
| Date collected | 2026-08-24 |

Every document is an instrument in its own right - regulations, standards, board
decisions and resolutions - covering licensing, governance and risk management,
financial and solvency regulation, reporting, Takaful, conduct, sanctions, motor
insurance and reinsurance.

Source documents are **not committed to this repository**. `corpus/registry.csv`
lists every document with its URL and metadata, and the pipeline rebuilds the
corpus from scratch:

```bash
pip install -r requirements.txt
python scripts/enrich_registry.py
python scripts/download_corpus.py
python scripts/build_corpus.py
```

`download_corpus.py` writes `corpus/manifest.json` with a SHA-256 for every
file, so a run can be tied to an exact corpus state. `build_corpus.py` writes
`corpus/processed/sections.jsonl`, `chunks.jsonl` and an `ingest_report.json`
recording the chunking parameters and every parser warning.

### How the documents are parsed

Worth stating plainly, because it is the decision that removed most of the
project's schedule risk: **there is no PDF parsing here.**

The Rulebook publishes every instrument as HTML in which each section is an
`h2.page-title` followed by a `div.field--name-body`, and each instrument has an
`/en/entiresection/<node_id>` view returning all of its articles in one request.
Section structure is therefore read from the document's own markup rather than
inferred from font sizes or heading regexes over extracted text. Official PDFs
exist and their URLs are recorded in the registry for provenance, but nothing in
the pipeline reads them.

Every chunk carries `doc_id` and the section identifier as printed, which
together form the `evidence_id` that benchmark labels are scored against. Three
things about that mapping are worth knowing before labelling questions:

- **Labels are normalised, not invented.** `Article (3): Effective Risk
  Management System` becomes `Article 3`; `Schedule No. (1)` becomes
  `Schedule 1`. The full heading survives in chunk metadata.
- **Compound instruments are qualified by their own addressing.** INS-FIN-001
  restarts its article numbering in each part, so its sections are
  `Section 1, Article 3` and `Section 2, Article 3` rather than a bare
  `Article 3` that would name two different provisions.
- **Sections without a printed identifier keep their heading as the label** -
  `Definitions`, `General Provisions`. 113 of the 763 sections are labelled this
  way; the other 650 carry a number.

One genuine ambiguity survives: INS-CON-001 prints `Article (14)` twice. It is
stored as `Article 14` and `Article 14 (2)` and flagged in the ingest report,
rather than silently collapsed.

### In the index, not in the ground truth

Four instruments are retrievable but may never be cited as required evidence.
`corpus/registry.csv` marks them `labelling_eligible=false`, and
`scripts/validate_benchmark.py` rejects any question whose `required_evidence`
names one.

They are the three Takaful standards commencing 2027-07-15 and the Takaful
Insurance Regulation commencing 2026-09-14 - all four listed by the Rulebook as
In-Force while carrying a commencement date after the corpus was collected.

**What that pairing means is not stated on the page, and this project does not
assert an interpretation.** It may be that an instrument is validly issued and
part of the current Rulebook with obligations phased in later; that is a
plausible reading, not a documented fact, so only the observation and the
handling are recorded here.

The handling follows from what this project already declines to claim.
Determining which instrument governs a given obligation *today* is a legal
judgement about commencement and transition. This benchmark measures retrieval.
So:

- **They stay in the index.** Three Takaful standards on adjacent subject matter
  are precisely the near-miss distractors that separate a good retriever from a
  bad one. Removing the hardest negatives would make every system look better
  than it is.
- **They stay out of the answer key**, because a label naming one would be an
  assertion about which instrument currently governs.
- They are the natural material for the `temporal` category if it is ever built.

`helpful_evidence` may still reference them: it is not scored for recall.

### Documents the Rulebook lists but has not published

Four entries - INS-GOV-005, INS-GOV-007, INS-GOV-009 and INS-TAK-007 - parse to
a title and nothing else. Three have no PDF in the Rulebook file store either.
They are kept in the registry and reported by `build_corpus.py` so the gap reads
as a finding about the source rather than a parser failure, but they contain no
citable text.

A separate observation, recorded because it is a limitation rather than a bug:
INS-GOV-008 publishes no effective date on its page, and its 17-page PDF
contains no date anywhere either. `effective_date_source` is `not_published` for
it and for three others. A missing effective date has no bearing on whether an
article is the right retrieval target, so those documents remain fully
labelling-eligible.

### Licensing and attribution

Corpus documents are © Central Bank of the UAE, retrieved from the CBUAE
Rulebook and reproduced locally for non-commercial research use only under the
CBUAE website [Terms and Conditions](https://www.centralbank.ae/en/footer/terms-and-conditions/)
(clause 2.3). This project is not affiliated with, endorsed by, or connected to
the Central Bank of the UAE.

Those terms permit download for non-commercial use with attribution, but **not
redistribution** — which is why no source document is committed here and why the
Phase 5 demo links to the Rulebook rather than mirroring it. The CBUAE Open Data
policy is more permissive but its stated scope is reports and studies, not the
Rulebook's regulatory text, so the more restrictive reading is the one applied.

Full record, including what was checked and when: `SOURCES.md`.

---

## Benchmark

**100 questions, verified in two batches of 50.** Counts are regenerated by
`python scripts/validate_benchmark.py`, which also reports drift from the target
mix in `benchmark/PLAN.md`.

| category | n | description |
|---|---:|---|
| single_hop | 18 | answerable from one section |
| cross_section | 27 | two or more sections, same document |
| cross_document | 17 | sections across separate instruments |
| temporal | 0 | requires the currently-in-force version; deferred from v1 |
| comparative | 13 | contrasts obligations across entity types |
| adversarial | 11 | premise is false or unsupported |
| unanswerable | 14 | not covered by the corpus; correct response is abstention |

Verification took 302 minutes in total - 173 for the first fifty, 129 for the
second - at a median of 3 minutes per question.

The second batch was spread roughly equally across categories rather than
repeating the first mix, which was shaped by a 50-question budget. That lifted
`adversarial` from 3 and `comparative` from 5, neither of which could support an
inference, and doubled `cross_document`. Both decisions were made from the
Phase 4 power analysis, which is recorded in `benchmark/PLAN.md` along with the
claims it says *not* to size for.

Each question records the sections that must be retrieved, why each one is
required, how long labelling took, and the labeller's confidence. Format is
defined in `benchmark/schema.json`; the target mix, the construction rule for
cross-document items, and the labelling protocol are in `benchmark/PLAN.md`.

### How a question gets into the benchmark

Questions are drafted into `benchmark/drafts.jsonl` and only enter
`benchmark/questions.jsonl` once a person has opened the cited sections and
checked them. `scripts/promote_drafts.py` enforces this: it refuses any item
without a recorded verification time and confidence level, the two fields only a
human can honestly supply.

This matters because the drafts were LLM-written. Every one resolves to a real
section and passes every automated check, which is not the same as being
correct - whether a section is genuinely *required* is a judgement about the
regulation. A benchmark drafted and approved by the same model would measure the
model's reading rather than the regulation, and every number downstream would
inherit that. `provenance.source` records `llm_drafted_human_verified` on each
item so the split is visible rather than implied.

**Labelling honesty.** Low-confidence items are excluded from headline metrics by
default. Distribution: **100 high, 0 medium, 0 low**, so every item is scored and
none is excluded.

That uniformity carries no information, and it is recorded here rather than
presented as reassurance: one item was originally marked medium and was raised
to high after the fact, and no label in either batch changed during verification. Self-reported confidence is weak evidence in any case,
which is why this project does not rest on it. A blind negative control measures
the verification directly - **5 of 8 planted label errors caught, 1 false alarm
across 8 untouched items** - and that number is the honest calibration. See
`results/label_verification_control.md`.

---

## Systems compared

| # | System | Description |
|---|---|---|
| 1 | BM25 | Lexical baseline |
| 2 | Dense | `BAAI/bge-small-en-v1.5`, 384 dimensions, normalised, CPU |
| 3 | Hybrid | Reciprocal rank fusion of 1 and 2, untuned k=60 |
| 4 | Hybrid + reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` over 50 candidates |

Everything runs locally with no paid API keys.

---

## Results

Measured by `scripts/run_eval.py` over the 86 answerable questions, on CPU.
Regenerate the tables with `scripts/report_results.py`; raw per-question output
is in `results/`.

### Overall

| System | recall@5 | recall@10 | full_recall@10 | nDCG@10 | MRR | median latency |
|---|---|---|---|---|---|---|
| BM25 | 0.471 | 0.581 | 0.465 | 0.442 | 0.448 | 4 ms |
| Dense | 0.552 | 0.680 | 0.523 | 0.542 | 0.579 | 44 ms |
| Hybrid (RRF) | 0.570 | 0.686 | 0.547 | 0.530 | 0.558 | 56 ms |
| Hybrid + reranker | 0.645 | **0.750** | **0.593** | **0.626** | **0.674** | 1042 ms |

### The answer to the question this project asks

**Yes.** Hybrid retrieval with reranking improves evidence recall over lexical
or dense retrieval alone, and at 100 questions the benchmark can show it.

| Comparison | difference in recall@10 | 95% interval | separates? |
|---|---|---|---|
| Dense vs BM25 | +0.099 | +0.006 – +0.198 | **yes** |
| Hybrid vs BM25 | +0.105 | +0.035 – +0.174 | **yes** |
| Hybrid + reranker vs BM25 | **+0.169** | **+0.087 – +0.250** | **yes** |
| Hybrid + reranker vs Dense | +0.070 | +0.006 – +0.134 | **yes** |
| Hybrid vs Dense | +0.006 | −0.070 – +0.081 | no |
| Hybrid + reranker vs Hybrid | +0.064 | −0.012 – +0.134 | no |

Paired bootstrap, 10,000 resamples, seeded per comparison. Pairing matters:
both systems answer the same questions, so the interval on the difference is
much tighter than the overlap between two per-system intervals suggests.

**At 50 questions, none of these separated.** The same four systems, the same
code, twice the questions — and the project's central claim went from "inside
what the benchmark can resolve" to established. That is the clearest argument in
this repository for why the evaluation is the project: nothing about the
retrieval changed, only the instrument measuring it.

Two comparisons still do not separate, and they are the two the power analysis
in `benchmark/PLAN.md` predicted would need roughly 1,200 questions. Their
effects are genuinely close to zero. Adding questions to chase them would be a
poor use of anyone's evenings.

### What doubling the benchmark changed about the answer

Not just the confidence — the ranking. On the first 50 questions BM25 scored
0.659 and dense 0.625, so lexical retrieval looked stronger. On 100, BM25 is
0.581 and dense 0.680, and dense beats it by a margin that clears zero.

The first 50 gave a misleading picture. The second 50 draw on 17 documents the
first never touched, and BM25 degrades on that wider material while dense holds
up. Any conclusion drawn from the earlier table about lexical retrieval being
competitive was an artefact of which documents happened to be covered.

### By question category — recall@10

| System | single_hop | cross_section | cross_document | comparative | adversarial |
|---|---|---|---|---|---|
| BM25 | 0.667 | 0.519 | 0.618 | 0.385 | 0.773 |
| Dense | 0.778 | 0.648 | 0.735 | 0.385 | **0.864** |
| Hybrid (RRF) | 0.778 | 0.593 | **0.853** | 0.423 | 0.818 |
| Hybrid + reranker | **0.833** | **0.759** | 0.824 | **0.462** | 0.818 |

n: single_hop 18, cross_section 27, cross_document 17, comparative 13,
adversarial 11.

**`cross_document` remains where the effect is largest**: BM25 0.618 against
hybrid 0.853. That category was named as the decisive one in the project plan
before any system was built, and it has now held up across two independent
batches of questions and a doubling of sample size.

**`comparative` is where every system is weakest**, and by a distance — the best
system reaches 0.462. These questions require the same provision from two
parallel instruments, and retrieving one copy is easy while retrieving both is
not. That is a genuine finding about a real weakness, and it only became visible
once the category had 13 questions instead of 5.

### What the reranker actually buys

At 100 questions the reranker looks better than it did at 50: **+0.169 recall@10
over BM25** and +0.070 over dense, both clearing zero, plus MRR 0.558 → 0.674.
It also lifts `cross_section` from 0.593 to 0.759.

The cost is unchanged and still the main argument against it: **1042 ms against
56 ms**, roughly nineteen times slower, because it runs 50 cross-encoder forward
passes per query on CPU. Against hybrid alone it does not separate (+0.064,
−0.012 – +0.134). What it does buy outright is abstention, below.

### Questions no system could answer

**6 of the 86 answerable questions scored recall@10 = 0 on all four systems**:
Q001, Q003, Q028, Q042, Q078, Q083. A further **16 were never answered
completely** by any system, with at least one required section always missing.

Those were re-checked against their cited articles, on the theory that a
question no system can answer is either genuinely hard or mislabelled. No label
changed.

### Why the absolute numbers are lower than they look

The questions are **paraphrases, not quotations**. `benchmark/schema.json`
requires it - "avoid quoting the regulation verbatim, that turns the task into
string matching" - so a question asks about "exposure beyond the level its board
signed off on" where the regulation says "deviation from the Risk Appetite".

That choice costs a great deal of measured recall. Taking the six questions no
system could answer and re-querying BM25 with the vocabulary of the cited
sections' own headings instead of the question as written:

| Question | rank as written | rank with keywords |
|---|---|---|
| Q001 | not in top 50 | **1** |
| Q003 | 46 | **1** |
| Q028 | 26 | **1** |
| Q042 | not in top 50 | **3** |
| Q078 | 27 | **1** |
| Q083 | 23 | **1** |

Every one is near-trivially retrievable by keyword. The systems are not failing
to find these sections; they are failing to connect a paraphrase to them.

This matters when comparing these figures to published benchmarks. A recall@10
of 0.581 for BM25 looks weak next to numbers from datasets whose questions were
generated *from* the passage they answer, and those are not measuring the same
thing.

## Answering: citations and abstention

Measured by `scripts/run_answering.py` over hybrid+reranker at k=5. Full
write-up in `results/abstention.md`.

### Citation validity

| | |
|---|---|
| Citations grounded - the cited section was in the retrieved context | **1.000** |
| Citations supported - the quoted text appears in that section | **1.000** |

**Both are 1.0 by construction, not by achievement.** The default answerer is
extractive: it quotes retrieved sections and attributes each quote, so it cannot
cite a section it did not retrieve or attribute words that are not there. It
cannot hallucinate, which is the right default for a regulatory tool.

The figure is reported because it is the bar an abstractive generator must
clear. A model that paraphrases is more readable and can score below 1.0 on
either row, and that gap is the price of fluency.

### Abstention now works, and at 50 questions it did not

| | min | median | max |
|---|---|---|---|
| Answerable (n=86) | -7.98 | 1.63 | 7.32 |
| Unanswerable (n=14) | -9.96 | -1.24 | 4.21 |

**AUC = 0.806, 95% interval 0.671 - 0.915.** The interval clears 0.5, so the
relevance score does distinguish a question the corpus cannot answer from one it
can.

At 6 unanswerable questions the same measurement gave AUC 0.761 with an interval
of 0.492 - 0.962, which includes the value meaning no separation at all. The
score distribution barely moved; the sample got big enough to see it.

The trade-off is still a trade-off:

| Threshold | Unanswerable declined (of 14) | Answerable wrongly declined (of 86) |
|---:|---:|---:|
| -3.28 | 3 | 4 |
| -2.53 | 5 | 7 |
| -1.43 | 7 | 11 |
| -0.13 | 11 | 21 |
| 5.90 | 14 | 81 |

`answer_question` still ships with no default threshold. Choosing the value that
looks best on these questions would be fitting a parameter to the test set, so
the curve is reported and the operating point is left to whoever deploys it.

**Why the hard cases are hard.** The worst offender scores 4.21, higher than
most answerable questions:

> *"What are the capital adequacy requirements for a finance company?"*
> -> top hit `INS-FIN-001::Section 2, Article 3`, titled **Group Capital Adequacy**

A cross-encoder trained on topical relevance is *right* that the passage is
about capital adequacy. What it cannot see is that the passage governs a
different kind of entity. **That is a scope question, not a relevance question**,
and no threshold on a relevance score will answer it.

### The cheap fix for that does not work

Every instrument states near its start who it binds, so the obvious experiment
was to build a scope profile from those framing sections and score the question
against it with the same cross-encoder. That was tested. It failed.

| Strategy | AUC | 95% interval |
|---|---:|---|
| **Relevance only** | **0.806** | 0.664 - 0.918 |
| Scope only | 0.575 | 0.393 - 0.757 |
| Relevance + scope | 0.675 | 0.512 - 0.823 |
| min(relevance, scope) | 0.575 | 0.392 - 0.752 |

Every combination is worse than relevance alone. The reason is in the medians:
answerable questions score -10.06 against framing text and unanswerable ones
-9.91, both at the floor. The cross-encoder scores *every* question poorly there,
because framing text is not answer-shaped - "This Regulation applies to all
Companies" does not look like a passage that answers anything.

The model judges whether a passage answers a query. Whether a query falls inside
a jurisdiction is not that task applied to different text. A real scope check
needs entailment - entity extraction, or an NLI model that can call "this
question concerns a finance company" a *contradiction* of "this instrument
applies to insurance companies" rather than a low-relevance pair. That is a
larger piece of work, which is exactly why the cheap version was worth testing
first. Write-up in `results/scope_check.md`.

### The price of fluency, measured

The extractive 1.000 above is only meaningful next to a model that writes prose,
so one was plugged in: **Qwen2.5-0.5B-Instruct**, local, CPU, 9.5 s per question,
all 100 questions. Full write-up in `results/abstractive.md`.

The first result is not the citation score. **The model declined 69 of 100
questions** - including 55 of the 86 the corpus does answer and the retriever
found. It refused every unanswerable question, which reads like perfect
abstention until you notice that refusing *everything* scores the same, and that
buying 14/14 cost 64% of the answerable set. It declines least on
`cross_document` and most on `comparative` and `adversarial` - a capability
ceiling, not caution.

Of the 28 answers that cited anything, 74 citations:

| | abstractive | extractive |
|---|---|---|
| Grounded | 1.000 | 1.000 |
| Supported, lenient (4 shared words) | 0.851 | - |
| Supported, strict (60% overlap) | **0.557** | **0.972** |

**Grounded 1.000 is a design artifact, not a result.** Passages are numbered in
the prompt and out-of-range tags are dropped rather than clamped, so an invented
reference vanishes instead of surviving as a wrong citation.

The distance between the two supported rows matters as much as either number:
four shared content words is nothing in a corpus where "company" and "board"
appear on every page, so the lenient figure mostly measures subject matter. The
strict one is the honest figure, and the gap is a warning about how much a
citation metric depends on its threshold.

The failure underneath it is specific. The model copies a passage closely and
then tags the sentence `[2][3]`, crediting one claim to several sections when
only one contains it:

| | answers | supported (strict) |
|---|---:|---:|
| Every claim names one passage | 14 | **0.738** |
| At least one claim names several | 14 | **0.375** |

Exactly half the answers do it, and it roughly halves their support - a fixable
defect rather than general unreliability.

**0.557 is a lower bound on abstractive citation validity, not an estimate of
it.** It is what a 0.5B model does, and the 69 refusals say model size is the
binding constraint. A larger model would refuse less and support more. What the
measurement establishes is that the gap between quoting and paraphrasing is real
and large on this corpus, and that reporting the extractive 1.000 without it
would have been misleading.

An earlier run of this was discarded: the citation parser split on sentence
boundaries, which put the full stop before the model's tag and checked each
citation against the *following* claim's words. It moved the headline number
with no model behaving differently, and was caught by a test rather than by
reading output that looked entirely plausible. `results/abstractive.md` records
the before and after.

### Deploying it

```bash
docker build -t regulens .
docker run --rm -p 8000:8000 regulens
```

The build fetches the corpus, parses it, downloads both models and warms the
embedding cache, so a container starts in seconds. Without that warming the
first request spends about ninety seconds embedding 954 chunks while the service
looks hung.

**The built image contains CBUAE text, so it must not be pushed to a public
registry.** `SOURCES.md` records that the terms permit download for
non-commercial use but not redistribution, and a public image is redistribution.
Keep it private, or build on the host that runs it. The repository itself stays
clean - no source document is committed.

**Measured footprint: 1,225 MB resident** with both models loaded and the index
built. That is the number that decides where this can run, and it rules out the
512 MB free tiers. Torch is most of it; the two models together are only about
220 MB on disk. Realistic options are a small paid instance, or exporting the
models to ONNX Runtime and dropping torch entirely - the larger piece of work,
and the one that would make a free tier possible.

Embeddings are cached to `corpus/processed/embeddings.npz`, keyed by a hash of
the model name and every text encoded, so rebuilding the corpus or changing the
model invalidates the cache automatically rather than silently serving vectors
for text that no longer exists.

---

## Limitations

Written before the results, not after.

**Every question was LLM-drafted and human-verified, and verification changed
nothing** — so the verification itself was measured rather than asserted. A
blind negative control planted deliberate errors in 8 of 16 sampled labels:
**5 of 8 were caught, with 1 false alarm on the 8 untouched items**
(`results/label_verification_control.md`).

At a detection rate near 62%, the fact that no correction was made across the
real 50 labels rules out four or more undetected errors at the 5% level, but not
zero to three. **The defensible claim is therefore that the benchmark contains
at most about three label errors, probably fewer** — a measured bound rather
than an assurance, and a weaker claim than the project would like.

The control also showed *which* errors get through. Swapped and superfluous
sections were caught 5 of 6 times; the two misses were a **dropped required
section** and an **unanswerable item given evidence**. Both are errors of
omission — the review reliably judged whether a listed section belonged, and
less reliably noticed what was absent. Those two shapes were re-checked across
the whole benchmark as a result.

A second review pass ran after the results, targeted at the two shapes the
control showed slipping through and at the 13 questions no system answered
completely. It changed nothing either. That does not prove the labels are
correct — it is the same reviewer, and the control measured what this reviewer
catches — but it is the second independent opportunity the errors had to
surface.

Read the ground truth as *checked, with a known detection rate*, not as
*independently established*.

**Ground truth is labelled by one non-expert author.** There is no second
labeller and no inter-rater agreement figure, so a systematic misreading would
not be caught by anything in this repository.

**The benchmark is small: n = 100, of which 86 are answerable.** By-category
counts are smaller still - `adversarial` has 11, `comparative` 13. Two
comparisons in the results table do not separate and, by the power analysis in
`benchmark/PLAN.md`, would need roughly 1,200 questions to do so; their effects
are close to zero and are reported as unresolved rather than as absent.

**The first 50 questions gave a different answer from the first 100.** BM25 led
dense at n=50 and trails it at n=100. Nothing about the systems changed - the
second batch simply covered 17 documents the first did not. Treat any single
batch of this benchmark as provisional, including this one.

**The corpus is a subset.** 46 instruments from the Insurance section of the
Rulebook, of which 39 carry substantive text. Four are listed but unpublished;
four more are indexed as distractors but barred from the answer key. Nothing
outside insurance is present, which is why questions about banking, the DIFC or
finance companies are correctly unanswerable *here* and not unanswerable in
general.

**Evidence labels reflect one reading.** Another reader could reasonably include
a section this benchmark treats as merely helpful, or drop one it treats as
required.

**Questions are paraphrases, so absolute recall is not comparable to benchmarks
built from quoted text.** The schema requires it, and the cost is measurable:
the six questions no system answered are all retrieved at rank 1 to 3 by BM25
when queried with the vocabulary of their own cited sections. See "Why the
absolute numbers are lower than they look".

**The corpus is a snapshot.** Collected 2026-08-24 from a live site.
`corpus/manifest.json` pins a SHA-256 per document so a result ties to an exact
corpus state, but the published text may since have moved.

### What surprised me

- **The Rulebook publishes structured HTML**, so there is no PDF parsing in this
  project at all — section identity is read from the document's own markup. That
  removed most of the schedule risk the project was scoped around.
- **Instruments are listed In-Force with commencement dates in the future.** Four
  are, one only three weeks after collection. They are indexed as distractors but
  barred from the answer key, because deciding which instrument governs an
  obligation today is a legal judgement this project does not make.
- **Three registry rows initially fetched an entire category** rather than a
  document, which would have indexed the same article under four `doc_id`s and
  quietly destroyed the meaning of evidence recall.
- **Article numbering restarts inside compound instruments.** `Article 3` names
  two different provisions in INS-FIN-001, so labels there carry the document's
  own `Section N,` qualifier.
- **The abstractive measurement was wrong the first time and looked fine.** The
  citation parser split on sentence boundaries, so each citation was checked
  against the next claim's words; the output read plausibly and the number was
  off by six points. A test asserting that a quote is the claim it was attached
  to found it. Measurement code needs tests as much as the system under
  measurement does, and it is easier to forget.

---

## Repository layout

```
corpus/
  registry.csv          documents to collect - the source of truth
  registry.example.csv  shape reference (all values fake)
  raw/                  downloaded sources (gitignored)
  processed/            parsed sections (gitignored)
benchmark/
  schema.json           question format
  questions.jsonl       the benchmark
  questions.example.jsonl
scripts/
  download_corpus.py    fetch the corpus
src/regulens/
  ingest/               parsing and chunking
  retrieval/            the four systems, one interface
  evaluation/           metrics and harness
  generation/           extractive and abstractive answering, citation checks
tests/
results/                measured output, committed
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest
```

## Build order

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Calibration: difficulty and question mix decided (`benchmark/PLAN.md`) | done |
| 1 | Registry populated, corpus downloading, licensing recorded | done |
| 2 | Parsing and chunking; sections carry citable identifiers | done |
| 3 | 50 labelled benchmark questions | done |
| 4 | Four systems built and measured; results tables filled | done |
| 5 | Grounded answering, citation validation, API and UI | done |
| 6 | *Optional:* cross-reference graph expansion | |

Phase 6 is optional and should not be started until 1–5 are complete.
