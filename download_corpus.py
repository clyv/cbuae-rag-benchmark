#!/usr/bin/env python3
"""Download the corpus described in corpus/registry.csv.

The registry is the single source of truth for what the corpus contains.
Source documents are NOT committed to this repository - this script fetches
them at clone time so that the repo stays small and stays clear of any
redistribution question.

Usage:
    python scripts/download_corpus.py                 # fetch everything missing
    python scripts/download_corpus.py --force         # re-fetch everything
    python scripts/download_corpus.py --dry-run       # show what would happen
    python scripts/download_corpus.py --only DOC-001  # fetch a single document

Exit codes:
    0  all requested documents present
    1  one or more downloads failed
    2  registry missing or malformed
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("requests is not installed. Run: pip install -r requirements.txt")


REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "corpus" / "registry.csv"
RAW_DIR = REPO_ROOT / "corpus" / "raw"
MANIFEST = REPO_ROOT / "corpus" / "manifest.json"

REQUIRED_COLUMNS = {
    "doc_id",
    "title",
    "doc_type",
    "authority",
    "url",
    "effective_date",
    "status",
    "parent_doc_id",
    "notes",
}

# Be a good citizen: identify the client and don't hammer the server.
USER_AGENT = "ReguLens-corpus-builder/0.1 (research portfolio project; contact via repo)"
REQUEST_TIMEOUT = 60
DELAY_BETWEEN_REQUESTS = 2.0
MAX_RETRIES = 3


@dataclass
class RegistryRow:
    doc_id: str
    title: str
    doc_type: str
    authority: str
    url: str
    effective_date: str
    status: str
    parent_doc_id: str
    notes: str

    @property
    def suffix(self) -> str:
        """File extension inferred from the URL path, defaulting to .pdf."""
        path = urlparse(self.url).path
        ext = Path(path).suffix.lower()
        return ext if ext in {".pdf", ".html", ".htm", ".txt", ".docx"} else ".pdf"

    @property
    def target(self) -> Path:
        return RAW_DIR / f"{self.doc_id}{self.suffix}"


def load_registry() -> list[RegistryRow]:
    if not REGISTRY.exists():
        sys.exit(
            f"Registry not found at {REGISTRY}.\n"
            "Copy corpus/registry.example.csv to corpus/registry.csv and fill it in."
        )

    with REGISTRY.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            sys.exit("Registry has no header row.")

        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            sys.exit(f"Registry is missing required columns: {sorted(missing)}")

        rows: list[RegistryRow] = []
        seen: set[str] = set()
        for lineno, raw in enumerate(reader, start=2):
            doc_id = (raw.get("doc_id") or "").strip()
            url = (raw.get("url") or "").strip()

            if not doc_id:
                sys.exit(f"Row {lineno}: doc_id is empty.")
            if doc_id in seen:
                sys.exit(f"Row {lineno}: duplicate doc_id {doc_id!r}.")
            if not url.startswith(("http://", "https://")):
                sys.exit(f"Row {lineno} ({doc_id}): url must be absolute, got {url!r}.")
            seen.add(doc_id)

            rows.append(
                RegistryRow(
                    doc_id=doc_id,
                    title=(raw.get("title") or "").strip(),
                    doc_type=(raw.get("doc_type") or "").strip(),
                    authority=(raw.get("authority") or "").strip(),
                    url=url,
                    effective_date=(raw.get("effective_date") or "").strip(),
                    status=(raw.get("status") or "").strip(),
                    parent_doc_id=(raw.get("parent_doc_id") or "").strip(),
                    notes=(raw.get("notes") or "").strip(),
                )
            )

    if not rows:
        sys.exit(
            "Registry is empty. Populate corpus/registry.csv with the documents "
            "you intend to collect - see corpus/registry.example.csv for the shape."
        )
    return rows


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(row: RegistryRow, session: requests.Session) -> tuple[bool, str]:
    """Download one document. Returns (success, message)."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(row.url, timeout=REQUEST_TIMEOUT, stream=True)
            response.raise_for_status()
            tmp = row.target.with_suffix(row.target.suffix + ".part")
            with tmp.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=1 << 16):
                    fh.write(chunk)
            if tmp.stat().st_size == 0:
                tmp.unlink(missing_ok=True)
                return False, "downloaded file was empty"
            tmp.replace(row.target)
            return True, "ok"
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES:
                return False, f"{type(exc).__name__}: {exc}"
            time.sleep(DELAY_BETWEEN_REQUESTS * attempt)
    return False, "exhausted retries"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    parser.add_argument("--dry-run", action="store_true", help="list actions, fetch nothing")
    parser.add_argument("--only", metavar="DOC_ID", help="fetch a single document")
    args = parser.parse_args()

    rows = load_registry()
    if args.only:
        rows = [r for r in rows if r.doc_id == args.only]
        if not rows:
            sys.exit(f"No registry entry with doc_id {args.only!r}.")

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    pending = [r for r in rows if args.force or not r.target.exists()]
    skipped = len(rows) - len(pending)
    print(f"{len(rows)} document(s) in registry | {skipped} already present | {len(pending)} to fetch")

    if args.dry_run:
        for row in pending:
            print(f"  would fetch {row.doc_id} <- {row.url}")
        return 0

    failures: list[tuple[str, str]] = []
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    for index, row in enumerate(pending, start=1):
        print(f"[{index}/{len(pending)}] {row.doc_id} ... ", end="", flush=True)
        ok, message = fetch(row, session)
        print(message)
        if not ok:
            failures.append((row.doc_id, message))
        if index < len(pending):
            time.sleep(DELAY_BETWEEN_REQUESTS)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry_sha256": sha256_of(REGISTRY),
        "documents": [],
    }
    for row in rows:
        entry = asdict(row)
        if row.target.exists():
            entry["local_path"] = str(row.target.relative_to(REPO_ROOT))
            entry["bytes"] = row.target.stat().st_size
            entry["sha256"] = sha256_of(row.target)
        else:
            entry["local_path"] = None
        manifest["documents"].append(entry)

    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    present = sum(1 for d in manifest["documents"] if d["local_path"])
    print(f"\nManifest written to {MANIFEST.relative_to(REPO_ROOT)} ({present}/{len(rows)} present)")

    if failures:
        print("\nFailed:")
        for doc_id, message in failures:
            print(f"  {doc_id}: {message}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
