# ReguLens — build plan

Eight phases. Each has an exit criterion, so you always know whether you are
done. Each also has a **demoable artifact**, so the project is never in a state
where you have nothing to show.

**Timing.** Estimates assume evenings and weekends around full-time work. They
are estimates, not measurements — treat them as rough shape, not commitments.
Total realistic span: **3–4 months**.

**The governing principle.** The evaluation is the project. The chatbot is the
demo. If you have to cut something, cut toward the benchmark, never away from
it.

---

## Phase 0 — Scoping and calibration ✅ COMPLETE

**Goal.** Decide what to build and confirm the corpus can support it.

**What was established:**

- Corpus: CBUAE Rulebook, Insurance section
- Thesis: compare retrieval architectures on evidence recall, not answer correctness
- Constraint: runs fully local, no paid API keys
- Calibration finding: regulations are largely **self-contained**. A question
  about risk management obligations *and* who approves them is answerable
  entirely within C 25/2022. Cross-document questions must be built around
  **definitional dependencies** (Article 3.2 defers to the Financial
  Regulations for the Solvency Capital Requirement; Article 10 lists seven
  other instruments), not around "two related-sounding regulations."
- Structural finding: every article has its own URL, so sections are free —
  no PDF parsing, no OCR, no heading heuristics.
- Structural finding: cross-references are real hyperlinks, so the reference
  graph is a link-scrape rather than an NLP project.

**Decision to record for interviews:** why retrieval metrics and not answer
correctness. Short version: evidence recall is verifiable by anyone with the
corpus open; legal correctness requires a compliance lawyer. Claiming only
what you can prove is the whole point.

---

## Phase 1 — Corpus acquisition and licensing

**Effort:** ~1 week. Mostly waiting and reading, not coding.

**Preconditions:** scaffold cloned.

### Tasks

1. **Registry is populated** — 46 rows covering nine categories. ✅ done
2. **Add Insurance-Related Professions.** Open
   `rulebook/insurance-related-professions` and expand its nine sub-folders
   (Actuaries, Bank Insurance, Insurance Agents, Insurance Brokers, Insurance
   Consultants, Insurance Producers, Points of Sale, Surveyors & Loss
   Adjusters, Third Party Health Insurance Administrators). Each contains
   documents. Add them with IDs `INS-PRO-001` onward. Expect this to bring the
   corpus to roughly 60–80 documents.
   *Why this matters:* the Brokers regulation is the natural counterparty for
   cross-document questions about entity-type comparison.
3. **Dry-run.** `python scripts/download_corpus.py --dry-run`. Fix any row the
   script rejects.
4. **Download.** Drop `--dry-run`. Roughly 2 seconds per document by design.
5. **Spot-check five files.** Open them. Confirm you got document text, not a
   cookie banner, a login wall, or a JavaScript shell. This is the single most
   common silent failure in corpus collection.
6. **Licensing audit.** Read the Rulebook's own terms/copyright page — not the
   general CBUAE open-data page, which describes reports and studies and does
   not explicitly cover regulatory text. Record findings in `SOURCES.md`:
   exact URL, date checked, what the terms say, what attribution is required,
   whether redistribution is permitted.
7. **Record the mitigation.** Source files are gitignored and fetched at clone
   time. Write down that this is deliberate.

### Deliverables

- `corpus/registry.csv` — complete
- `corpus/raw/` — populated locally, gitignored
- `corpus/manifest.json` — SHA-256 per file
- `SOURCES.md` — completed licensing record

### Exit criteria

- [ ] Every registry row downloaded successfully
- [ ] Five files manually confirmed to contain real text
- [ ] `SOURCES.md` has no TODOs
- [ ] `manifest.json` committed (it is metadata, not content)

### Risks

| Risk | Mitigation |
|---|---|
| Pages render via JavaScript, so you get an empty shell | Spot-check step 5. If it happens, fall back to the PDF download links on each page |
| Terms turn out to prohibit redistribution | You are already fetch-at-clone-time. Document it and move on |
| Rate limiting or blocking | Increase `DELAY_BETWEEN_REQUESTS`. Do not parallelise |

### Demoable artifact

A repo anyone can clone and run one command against to reproduce your exact
corpus. That reproducibility is itself a talking point.

---

## Phase 2 — Parsing and chunking

**Effort:** ~1 week. Cheaper than originally planned because of the HTML finding.

**Preconditions:** Phase 1 complete.

### Tasks

1. **Write the section extractor** (`src/regulens/ingest/parse.py`). Parse each
   saved HTML page into sections. Target structure per section:
   `doc_id`, `section` (as printed — "Article (3)", "Introduction", "Scope of
   Application"), `text`, `order`.
2. **Handle the article-vs-page distinction.** A regulation's top-level page
   contains all its articles inline. Decide whether to parse that one page or
   fetch each article URL separately. Parsing the single page is fewer requests
   and is what your current registry supports.
3. **Extract document metadata while you are in there** — the regulation code
   (e.g. `C 25/2022`), effective date, and in-force status appear on the page.
   Backfill `registry.csv`'s `effective_date` and `status` columns.
4. **Extract outbound references.** Every hyperlink to another
   `rulebook.centralbank.ae` node is an edge. Save to
   `corpus/processed/references.json` as `{from_doc, from_section, to_node,
   to_doc_if_resolvable}`. Cheap now, valuable in Phase 4.
5. **Handle tables.** Regulatory text here uses tables heavily for enumerated
   sub-clauses. Flatten them into readable text; do not drop them. Losing
   table content silently is the second most common corpus failure.
6. **Write the chunker** (`src/regulens/ingest/chunk.py`). Sections vary from
   one line to several pages. Split long sections, keep the section label on
   every resulting chunk, record chunking parameters.
7. **Persist** to `corpus/processed/chunks.jsonl`.
8. **Sanity-check the output.** Print the ten longest and ten shortest chunks
   and read them. Look for navigation boilerplate, footer text, and language
   switcher links leaking in — the pages carry a lot of chrome.

### Deliverables

- `corpus/processed/sections.jsonl`
- `corpus/processed/chunks.jsonl`
- `corpus/processed/references.json`
- `registry.csv` with dates and statuses backfilled

### Exit criteria

- [ ] Every document produces at least one section
- [ ] Every chunk carries a `doc_id` and a `section` you could cite
- [ ] Manual read of 20 random chunks shows no boilerplate contamination
- [ ] Chunk count and token distribution recorded in `results/corpus_stats.json`

### Risks

| Risk | Mitigation |
|---|---|
| Boilerplate contaminates chunks | Step 8. Strip nav/footer by CSS selector before extracting |
| Section labels inconsistent across documents | Normalise to a canonical form; record the normalisation rule |
| Very long documents produce hundreds of chunks and skew retrieval | Report chunk distribution; consider per-document caps |

### Decision to record

Chunking strategy and why. "Section-aware with a 512-token cap and 64-token
overlap, because regulatory articles are semantically self-contained" is a
defensible answer. "512 because that's the default" is not.

### Demoable artifact

`corpus_stats.json` plus a notebook cell printing a parsed article. You can
show someone the pipeline works before any retrieval exists.

---

## Phase 3 — Benchmark construction

**Effort:** ~2–3 weeks. **The slowest phase and the actual differentiator.**
Budget more than feels reasonable.

**Preconditions:** Phase 2 complete — you need section IDs to label against.

### Target mix (revised after Phase 0 calibration)

| Category | Count | Notes |
|---|---|---|
| `single_hop` | 15 | One section, one document |
| `cross_section` | 20 | Two or more sections, same document. **The bulk** — this is what the corpus naturally supports |
| `cross_document` | 8 | Built around definitional dependencies only |
| `unanswerable` | 7 | Plausible-sounding, not in corpus. Tests abstention |
| **Total** | **50** | |

`temporal` and `comparative` are deferred. There is a revision-history page but
its usability for clean before/after pairs is unverified.

### Tasks

1. **Write 10 questions first, then stop and label them.** Do not write 50 and
   then label 50. You will discover your question style is unlabellable and
   waste the batch.
2. **For each question, record:** the question, the required evidence sections
   with a one-line justification each, how long labelling took, and your
   confidence.
3. **Keep evidence sets small and bounded.** "What are a company's risk
   management obligations" has no determinate answer — Articles 2, 3, 5, 6, 7,
   8 and 12 all qualify. "Who must approve a deviation from the risk appetite"
   resolves to one clause in five minutes. Narrow questions can still be hard
   to *retrieve* while being easy to *label*.
4. **Do not quote the regulation verbatim in the question.** That turns the
   task into string matching and inflates BM25 artificially.
5. **Build `cross_document` questions from real reference edges** —
   use `references.json` from Phase 2 to find where one document genuinely
   defers to another, then write the question around that dependency.
6. **Write `unanswerable` questions that sound plausible.** "What are the
   minimum capital requirements for a cryptocurrency insurance product?" — a
   real-sounding question the corpus does not address.
7. **Validate continuously.** `python scripts/validate_benchmark.py` after
   every batch. It catches duplicate IDs, doc_ids missing from the registry,
   and category/evidence mismatches.
8. **Log the labelling time honestly.** Items over 20 minutes are a signal the
   question is ambiguous, not that you are slow. Mark them low-confidence.

### Deliverables

- `benchmark/questions.jsonl` — 50 validated items
- A short note in the README on how questions were constructed

### Exit criteria

- [ ] 50 non-retired questions
- [ ] `validate_benchmark.py` exits 0
- [ ] Every required-evidence entry has a `why`
- [ ] Confidence distribution recorded — and low-confidence count is under ~10
- [ ] You could re-derive any evidence label from the documents in under 10
      minutes

### Risks

| Risk | Mitigation |
|---|---|
| **Wrong labels silently invalidate every downstream number** | Exclude low-confidence items from headline metrics by default (the loader already does this). Report the sensitivity |
| Questions too easy — BM25 saturates | Check after the first 10: run a quick keyword search by hand. If Ctrl+F finds it, rewrite it |
| Burnout — this phase is tedious | 10 questions per session, not 50. It is a marathon phase |
| Unconscious bias toward questions your system will answer well | Write all 50 **before** building any retriever. Non-negotiable |

### Decision to record

How ground truth was established, and its limitations. Say plainly: single
non-expert labeller, evidence-level not answer-level, confidence recorded per
item. Interviewers respect stated limitations far more than unstated ones.

### Demoable artifact

The benchmark itself. Honestly, this is the most impressive file in the repo —
almost nobody building RAG portfolios has one.

---

## Phase 4 — Retrieval systems and measurement

**Effort:** ~2 weeks.

**Preconditions:** Phases 2 and 3 complete. Do not start before the benchmark
exists.

### Build order — deliberately weakest first

**4a. BM25** (`retrieval/bm25.py`). `rank_bm25` over your chunks.
*This is a checkpoint, not just a baseline.* If BM25 scores above roughly 0.85
recall@10, your questions are too easy — go back to Phase 3 before building
anything else.

**4b. Dense** (`retrieval/dense.py`). `sentence-transformers` with a small
BGE or E5 model on CPU. FAISS or in-memory numpy — at this corpus size numpy is
genuinely fine and one less dependency to justify. Record model name,
dimension, indexing time, whether you normalised.

**4c. Hybrid** (`retrieval/hybrid.py`). Reciprocal rank fusion of 4a and 4b.
RRF over weighted score fusion because it needs no score normalisation and no
tuned weights — one less arbitrary choice to defend.

**4d. Hybrid + reranker** (`retrieval/rerank.py`). Retrieve 50 candidates,
rerank with a local cross-encoder (bge-reranker family), keep top k.
**Measure latency here** — the accuracy/speed trade-off is the question you
will be asked.

**4e. Optional: + graph expansion.** After retrieving, follow reference edges
from `references.json` one hop and add those sections as candidates. Originally
deferred to a later phase; the Phase 0 finding that references are plain
hyperlinks makes it cheap enough to attempt here. **Only after 4a–4d are
measured and committed.**

### Tasks

1. Build each system behind the `Retriever` protocol in `retrieval/base.py`.
2. Write `scripts/run_eval.py` — loads the benchmark, runs each system, writes
   `results/<system_name>.json` and a markdown table.
3. Run all systems on identical inputs. Never tune a system after seeing its
   benchmark score without saying so.
4. Fill in the README results tables from actual measured output.
5. Produce the by-category table. **This is the interesting one** — expect all
   systems to look similar on `single_hop` and to separate on
   `cross_section` / `cross_document`.

### Deliverables

- Four (or five) working retrievers
- `results/*.json` per system
- README results tables populated with real numbers

### Exit criteria

- [ ] Every system scored on all 50 questions
- [ ] Overall and by-category tables in the README
- [ ] Latency recorded per system
- [ ] Results reproducible from a single command

### Risks

| Risk | Mitigation |
|---|---|
| Hybrid does not beat its parents | **Report it.** A negative result you can explain beats a positive one you cannot |
| Reranker is unusably slow on CPU | Reduce candidate count; report the trade-off as a finding |
| Tuning against the benchmark inflates results | Freeze the benchmark before this phase. If you must tune, hold out 10 questions |

### Decision to record

Why RRF over weighted fusion. Why that embedding model. Why that candidate
count for reranking. Have an answer for each.

### Demoable artifact

**The results table.** This is the thing you put on LinkedIn.

---

## Phase 5 — Grounded generation and citation validation

**Effort:** ~1–2 weeks.

**Preconditions:** Phase 4 complete. A best retriever chosen on measured evidence.

### Tasks

1. **Pick a local model.** A small instruct model via `llama.cpp` or Ollama.
   Quality matters less than you think — the retrieval does the work.
2. **Write the prompt for strict grounding.** Answer only from provided
   passages; decline when evidence is insufficient; cite `doc_id` and section
   for every claim.
3. **Test abstention** against your seven `unanswerable` questions. Report the
   rate. This is a headline number.
4. **Implement citation validation** (`generation/answer.py`). Parse citations
   out of the answer; verify each cited section was actually in the retrieved
   context. Report: citation validity rate, uncited-claim rate.
5. **Add the disclaimer** to every generated answer in the UI, not only the
   README.

### Deliverables

- Working grounded answering
- Abstention rate and citation-validity numbers in the README

### Exit criteria

- [ ] Abstains on a majority of `unanswerable` items
- [ ] Citation validity measured and reported
- [ ] Disclaimer present in generated output

### Risks

| Risk | Mitigation |
|---|---|
| Small model ignores grounding instructions | Try a larger quantised model; report which models held the constraint — that is itself a finding |
| Citation parsing is brittle | Constrain output format (JSON with a citations array) rather than parsing prose |

### Decision to record

Why grounding is enforced at the prompt *and* validated afterward. Belt and
braces, because prompts are not guarantees.

---

## Phase 6 — API, UI, deployment

**Effort:** ~2 weeks.

### Tasks

1. **FastAPI service** — `POST /query` returning answer, citations, retrieval
   trace, and latency.
2. **Minimal UI.** The important design choice: **show the retrieval trace**,
   not just the answer. Which sections were retrieved, at what rank, from which
   system, and which the answer actually cited. That visibly communicates you
   thought about provenance.
3. **Resolve the local-vs-deployed tension.** Local retrieval plus a local LLM
   will not fit a free hosting tier's memory. Options, pick one and document it:
   - Deploy retrieval only; generation runs locally (demo shows retrieval trace)
   - Deploy with a free-tier hosted inference endpoint for generation
   - Record a video demo of the fully-local version; deploy nothing
   Verify current free-tier specs before committing — do not assume.
4. **Dockerfile** for reproducibility.

### Exit criteria

- [ ] API runs locally from a documented command
- [ ] UI shows retrieval trace and citations
- [ ] Either deployed with a public URL, or a recorded demo exists

### Risks

| Risk | Mitigation |
|---|---|
| Deployment eats a week | Timebox it. A recorded demo is an acceptable outcome |
| Free tier changes or disappears | Local-first design means the project still works |

---

## Phase 7 — Write-up and publication

**Effort:** ~1 week. **Do not skip. This is what converts work into interviews.**

### Tasks

1. **Finish the README.** Fill every TODO. Write the limitations section
   honestly and specifically.
2. **Write the methodology note** — how the benchmark was built, how ground
   truth was established, what is and is not claimed.
3. **Resume bullets** — draft from measured numbers, never illustrative ones.
4. **LinkedIn post** — lead with the finding, not the tech stack. "I built a
   50-question benchmark and measured four retrieval architectures; here is
   where they separate" beats "I built a RAG chatbot with LangChain."
5. **Interview prep.** Write out your answer to each recorded decision from the
   earlier phases. If you cannot defend a choice, that is a gap to close now.

### Exit criteria

- [ ] No TODOs in the README
- [ ] Limitations section written and specific
- [ ] Every design decision has a prepared answer
- [ ] Repo public, licensing recorded

---

## Optional extensions

Only after Phase 7 is complete.

- **Temporal / versioning.** Use the Rulebook's revision-updates page to build
  before/after question pairs. Adds a genuinely novel evaluation category.
- **Query understanding.** Classify question type and route to different
  retrieval strategies. Measure whether routing beats a single strategy.
- **Ablations.** Chunk size, embedding model, fusion weights. Cheap
  experiments, good README paragraphs.

---

## If you run out of time

Cut in this order, from first to cut:

1. Optional extensions
2. Graph expansion (4e)
3. Deployment — a recorded demo is fine
4. Generation quality — retrieval is the thesis
5. Corpus size — 30 documents with a good benchmark beats 80 with a bad one

**Never cut:** the benchmark, the results table, or the limitations section.
Those three are the project.

---

## Phase summary

| Phase | Effort | Exit criterion | Demoable artifact |
|---|---|---|---|
| 0 Scoping | done | Corpus and thesis chosen | — |
| 1 Corpus | ~1 wk | All documents downloaded, licensing recorded | Reproducible corpus |
| 2 Parsing | ~1 wk | Every chunk citable | Corpus stats |
| 3 Benchmark | ~2–3 wk | 50 validated questions | The benchmark |
| 4 Retrieval | ~2 wk | Four systems measured | **Results table** |
| 5 Generation | ~1–2 wk | Citation validity measured | Grounded answers |
| 6 API + UI | ~2 wk | Deployed or recorded | Live demo |
| 7 Write-up | ~1 wk | No TODOs | The README |
