#!/usr/bin/env python3
"""Backfill registry metadata from the CBUAE Rulebook document pages.

Phase 1. Each Rulebook document page carries the metadata the registry needs -
its node id, instrument code, effective date and in-force status - so none of it
has to be transcribed by hand. This script reads corpus/registry.csv, fetches
each document page once, and writes the values back.

It also records which Rulebook section each document actually sits in. Four
registry URLs carry Drupal deduplication suffixes (operational-risk-0,
climate-related-financial-risk-management-1, and so on), which appear when the
same title exists in more than one section. Those are exactly the rows that
could silently point at the Banking copy of a document instead of the Insurance
one, so the section is captured and checked rather than assumed.

Run it before scripts/download_corpus.py:

    python scripts/enrich_registry.py            # fetch and write
    python scripts/enrich_registry.py --dry-run  # report, change nothing

Nothing here is destructive: existing non-empty values are kept unless --force
is passed, and every change is printed.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "corpus" / "registry.csv"
BASE = "https://rulebook.centralbank.ae"

# See SOURCES.md. The Rulebook's load balancer rejects any client that does not
# present a browser User-Agent - it returns 403 even for its own robots.txt -
# while that robots.txt permits /en/rulebook/ and /en/entiresection/ for every
# agent. A From header carries the contact information the UA string cannot.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "From": "ReguLens corpus builder (non-commercial research; contact via repository)",
    "Accept-Language": "en",
}
REQUEST_TIMEOUT = 60
DELAY_BETWEEN_REQUESTS = 2.0
MAX_RETRIES = 3

# Columns this script adds to the registry, in the order they are appended.
ADDED_COLUMNS = ["node_id", "code", "rulebook_section", "pdf_url"]

# Columns this script is allowed to write into.
MANAGED_COLUMNS = ["effective_date", "status"] + ADDED_COLUMNS

STATUS_MAP = {
    "in-force": "in_force",
    "in force": "in_force",
    "superseded": "superseded",
    "repealed": "repealed",
    "revoked": "repealed",
    "not yet in force": "not_yet_in_force",
}


@dataclass
class PageFacts:
    node_id: str = ""
    code: str = ""
    effective_date: str = ""
    status: str = ""
    rulebook_section: str = ""
    pdf_url: str = ""
    problems: tuple[str, ...] = ()


def normalise_date(raw: str) -> str:
    """The Rulebook prints DD/MM/YYYY. ISO is what the registry stores."""
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw.strip())
    if not match:
        return ""
    day, month, year = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def normalise_status(raw: str) -> str:
    return STATUS_MAP.get(raw.strip().lower(), raw.strip().lower().replace(" ", "_"))


def extract(html: str) -> PageFacts:
    soup = BeautifulSoup(html, "lxml")
    problems: list[str] = []

    body_classes = " ".join(soup.body.get("class") or []) if soup.body else ""
    node_match = re.search(r"page-node-(\d+)", body_classes)
    node_id = node_match.group(1) if node_match else ""
    if not node_id:
        problems.append("no node id in body class")

    main = soup.select_one("main") or soup.body
    text = re.sub(r"[ \t]+", " ", main.get_text("\n")) if main else ""
    text = re.sub(r"\n{2,}", "\n", text)

    date_match = re.search(r"Effective from\s*([\d/]+)", text)
    effective_date = normalise_date(date_match.group(1)) if date_match else ""
    if date_match and not effective_date:
        problems.append(f"unparsable date {date_match.group(1)!r}")

    status_match = re.search(r"Status:\s*([A-Za-z \-]+)", text)
    status = normalise_status(status_match.group(1)) if status_match else ""

    # Instrument code, e.g. "C 25/2022". Printed on its own line under the title.
    code_match = re.search(r"\n\s*([A-Z]{1,3}\s?\d+/\d{4})\s*(?:Effective|\n)", text)
    code = code_match.group(1).strip() if code_match else ""

    # Which top-level Rulebook section this document belongs to. The document
    # page links back to its own section, so read it rather than infer it.
    section = ""
    for anchor in soup.find_all("a", href=True):
        match = re.fullmatch(r"/en/rulebook/(insurance|banking)", anchor["href"])
        if match:
            section = match.group(1)
            break
    if not section:
        problems.append("could not determine rulebook section")

    pdf_url = ""
    for anchor in soup.find_all("a", href=True):
        if anchor["href"].lower().endswith(".pdf"):
            pdf_url = anchor["href"]
            if pdf_url.startswith("/"):
                pdf_url = BASE + pdf_url
            break

    return PageFacts(
        node_id=node_id,
        code=code,
        effective_date=effective_date,
        status=status,
        rulebook_section=section,
        pdf_url=pdf_url,
        problems=tuple(problems),
    )


def fetch(url: str, session: requests.Session) -> str | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            response.encoding = response.encoding or "utf-8"
            return response.text
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES:
                print(f"    fetch failed: {type(exc).__name__}: {exc}")
                return None
            time.sleep(DELAY_BETWEEN_REQUESTS * attempt)
    return None


def infer_parents(rows: list[dict[str, str]]) -> dict[str, str]:
    """Pair each '<X> Standards' document with the '<X> Regulation' it elaborates.

    The Rulebook publishes several regulation/standards pairs as separate
    documents. That pairing is the clearest 'general instrument -> specific
    instrument' link in the corpus, which benchmark/PLAN.md names as one of the
    two shapes a cross_document question may be built on. Matching is on title
    stem only, and every suggestion is printed for confirmation rather than
    written silently.
    """
    by_stem: dict[str, dict[str, str]] = {}
    for row in rows:
        title = row["title"].strip()
        stem = re.sub(r"\b(Regulation|Standards?)\b", "", title, flags=re.I)
        stem = re.sub(r"\s+", " ", stem).strip().lower()
        kind = "standard" if re.search(r"\bStandards?\b", title, re.I) else "regulation"
        by_stem.setdefault(stem, {})[kind] = row["doc_id"]

    parents: dict[str, str] = {}
    for pair in by_stem.values():
        if "standard" in pair and "regulation" in pair:
            parents[pair["standard"]] = pair["regulation"]
    return parents


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite values already present, not just fill blanks",
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    with REGISTRY.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]

    if not rows:
        sys.exit("Registry is empty.")

    for column in ADDED_COLUMNS:
        if column not in fieldnames:
            fieldnames.append(column)
        for row in rows:
            row.setdefault(column, "")

    session = requests.Session()
    session.headers.update(HEADERS)

    changed = 0
    failures: list[str] = []
    anomalies: list[str] = []

    for index, row in enumerate(rows, start=1):
        doc_id = row["doc_id"]
        print(f"[{index}/{len(rows)}] {doc_id} ... ", end="", flush=True)

        html = fetch(row["url"], session)
        if html is None:
            failures.append(doc_id)
            print("FAILED")
            continue

        facts = extract(html)
        updates: dict[str, str] = {}
        for column in MANAGED_COLUMNS:
            value = getattr(facts, column, "")
            if value and (args.force or not row.get(column, "").strip()):
                if row.get(column, "").strip() != value:
                    updates[column] = value

        if facts.rulebook_section and facts.rulebook_section != "insurance":
            anomalies.append(
                f"{doc_id}: sits in the '{facts.rulebook_section}' section, not insurance"
                f" -> {row['url']}"
            )
        for problem in facts.problems:
            anomalies.append(f"{doc_id}: {problem}")
        if not facts.effective_date:
            anomalies.append(f"{doc_id}: no effective date published on the page")

        row.update(updates)
        if updates:
            changed += 1
        summary = (
            f"node={facts.node_id or '?'} "
            f"code={facts.code or '-'} "
            f"eff={facts.effective_date or '-'} "
            f"status={facts.status or '-'} "
            f"section={facts.rulebook_section or '?'}"
        )
        print(summary)

        if index < len(rows):
            time.sleep(DELAY_BETWEEN_REQUESTS)

    suggested_parents = infer_parents(rows)
    applied_parents = 0
    for doc_id, parent_id in suggested_parents.items():
        row = next(r for r in rows if r["doc_id"] == doc_id)
        if args.force or not row.get("parent_doc_id", "").strip():
            row["parent_doc_id"] = parent_id
            applied_parents += 1

    print(f"\n{changed}/{len(rows)} row(s) updated; {applied_parents} parent link(s) set")

    if suggested_parents:
        print("\nParent links (regulation -> its standards), confirm these by eye:")
        for doc_id, parent_id in sorted(suggested_parents.items()):
            print(f"  {doc_id} -> parent {parent_id}")

    if anomalies:
        print("\nAnomalies to resolve before labelling questions:")
        for note in anomalies:
            print(f"  {note}")

    if failures:
        print(f"\nFailed to fetch: {', '.join(failures)}")

    if args.dry_run:
        print("\n--dry-run: registry not written.")
        return 1 if failures else 0

    with REGISTRY.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {REGISTRY.relative_to(REPO_ROOT)}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
