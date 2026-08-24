# Sources and reuse terms

Complete this **before making the repository public**. This file is the record
that the corpus was collected lawfully and with attribution.

## Why this exists

Source documents are not committed to this repository; `scripts/download_corpus.py`
fetches them from the publisher at clone time. That keeps the repo small and
avoids a redistribution question. It does not remove the need to check terms.

## Per-source record

### Central Bank of the UAE (CBUAE)

- **Documents used:** 46 instruments from the Insurance section of the CBUAE
  Rulebook (`https://rulebook.centralbank.ae`) — regulations, standards, board
  decisions and resolutions. Listed in `corpus/registry.csv`. No other publisher
  is used.
- **Terms page:** https://www.centralbank.ae/en/footer/terms-and-conditions/
  (Intellectual Property, clauses 2.1–2.5; page states it was last updated
  2 August 2022). The Rulebook sits on a subdomain and links to this page as its
  terms.
- **Also checked:**
  - https://www.centralbank.ae/en/footer/disclaimer/ (Links, clauses 1.1–1.2;
    General Provisions 3.1–3.3)
  - https://www.centralbank.ae/en/open-data-landing/ and its Open Data Policy
    and Open Data Guidelines sub-pages (page states last updated
    19 February 2025)
- **Date checked:** 2026-08-24
- **What the terms say:**
  - CBUAE asserts copyright over all material on the website unless otherwise
    stated (clause 2.2).
  - Download and print are permitted for personal use, use within an
    organisation, or non-commercial use — and the copyright symbol
    "© Central Bank of the UAE" must appear on any material reproduced, saved,
    printed or otherwise distributed (clause 2.3).
  - The CBUAE name and logo must not be used in advertising or public
    announcements without prior written consent (clause 2.4).
  - Unauthorised reproduction is prohibited (clause 2.5).
  - Direct links to pages are expressly permitted; loading CBUAE pages inside
    frames on another site is not (disclaimer clause 1.2).
  - Terms may change without notice, and UAE law and courts govern
    (disclaimer clauses 3.1–3.3).
- **Attribution required?:** **Yes.** "© Central Bank of the UAE" must appear on
  reproduced or saved material. Provided in three places: the corpus notice
  written into `corpus/raw/` by `scripts/download_corpus.py`, the README, and the
  citation line of any generated answer in Phase 5.
- **Redistribution:** **Not permitted.** Clause 2.5 prohibits unauthorised
  reproduction, and clause 2.3 grants only download/print for non-commercial use
  — not onward publication.
- **Approach taken:** Fetch at clone time only. No source document is committed
  to this repository, and none is served as a mirror. `corpus/raw/` and
  `corpus/processed/` are gitignored.

## Which terms actually govern the Rulebook

This is the one genuinely ambiguous point, so it is recorded rather than assumed.

The CBUAE Open Data pages describe an open data policy under which material can
be accessed, used, distributed, modified and shared for any purpose without
technical, financial or legal restriction, subject to citing the source and
honouring any copyleft licence. That is a permissive grant.

**But its stated scope is reports, studies and other content** — it does not name
the Rulebook's regulatory text, and the open-data material is published through a
separate "Open Data Documents" area. The Rulebook is not part of that area.

**Operative conclusion for this project: treat the Rulebook under the site-wide
Terms and Conditions, not the Open Data policy.** That is the more restrictive
reading, and it is the one this repository is built around. Nothing here depends
on the open-data grant applying.

An earlier scoping note for this project characterised CBUAE material as open
data with attribution. That was too permissive for the Rulebook specifically, and
this file supersedes it.

## Consequences for the build

- **Phase 1** — no corpus files committed. Already the design; now also a
  requirement rather than a convenience.
- **Phase 5** — a public demo must not become a mirror of the Rulebook. Show the
  citation, a short excerpt, and a deep link to the article on
  `rulebook.centralbank.ae`. Do not serve full article text as the product.
- **Presentation** — clause 2.4 restricts use of the CBUAE name in advertising or
  public announcements. Describing the corpus factually ("built over publicly
  available CBUAE insurance regulation") is nominative use and is not the concern;
  anything that implies CBUAE involvement, endorsement or partnership is.
  Do not use the CBUAE logo anywhere.
- **Accuracy** — the Rulebook is an access aid. Where it differs from the
  instruments issued through formal channels, the formally issued version
  prevails. The README already declines to claim legal accuracy; this is a second
  reason that framing is correct.

## Open questions

- [ ] Confirm whether any of the 46 registry rows are also published in the Open
      Data Documents area. If so, those specific documents carry the more
      permissive grant, and that should be recorded per-row rather than assumed
      corpus-wide.
- [ ] `status` and `effective_date` are unpopulated for all 46 rows. Superseded
      instruments must be marked before any question is labelled against them.
- [ ] Terms may change without notice (disclaimer 3.1). Re-check this page before
      the repository is made public, and record the date here.
