#!/usr/bin/env python
"""Populate documentId and fix truncated pdfPath in data/processed/projects.json.

Matching strategies (tried in order):
  1. Exact case-insensitive ilike
  2. NFKC-normalised exact match  (fixes CJK compatibility-ideograph mismatches)
  3. Prefix match                  (fixes filenames truncated at ~80 chars)
  4. NFKC-normalised prefix match  (truncated + normalisation combined)

When a match is found the script:
  - Sets  project["documentId"] = <pdf_documents.id>
  - Fixes project["pdfPath"]   = <folder_prefix>\<full DB filename>
    only when the original filename was truncated or had normalisation issues.

Usage (from repo root):
    python scripts/populate_document_ids.py [--dry-run]

Requires DATABASE_URL in the environment or a .env file.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

# Force UTF-8 output on Windows where the default console encoding (CP950/GBK)
# can't represent all CJK characters in filenames.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


def _pfn(project: dict) -> str:
    """Filename portion of pdfPath (no folder prefix)."""
    return project.get("pdfPath", "").replace("\\", "/").split("/")[-1].strip()


def _pfolder(project: dict) -> str:
    """Folder prefix of pdfPath, with trailing backslash. Empty if none."""
    pp = project.get("pdfPath", "").replace("\\", "/")
    parts = pp.rsplit("/", 1)
    return (parts[0].replace("/", "\\") + "\\") if len(parts) > 1 else ""


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).lower()


def _stem(fn: str) -> str:
    """Filename without .pdf extension."""
    return fn[:-4] if fn.lower().endswith(".pdf") else fn


def _find_match(fn: str, db_docs: list) -> tuple:
    """Return (doc, needs_path_fix: bool) or (None, False).

    needs_path_fix is True when the project filename differs from the DB filename
    (truncated or normalisation mismatch), meaning pdfPath should be updated.
    """
    fn_norm = _norm(fn)
    fn_stem_norm = _norm(_stem(fn))

    # 1. Exact ilike (original behaviour)
    for d in db_docs:
        if d.filename.lower() == fn.lower():
            return d, False

    # 2. NFKC-normalised exact match
    for d in db_docs:
        if _norm(d.filename) == fn_norm:
            return d, (d.filename != fn)  # fix if raw bytes differ

    # 3. Prefix match (project filename is a truncated prefix of DB filename)
    for d in db_docs:
        ds = _norm(_stem(d.filename))
        if ds.startswith(fn_stem_norm) and len(ds) > len(fn_stem_norm):
            return d, True

    return None, False


def main():
    parser = argparse.ArgumentParser(
        description="Populate documentId and fix truncated pdfPath in projects.json"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    args = parser.parse_args()

    projects_path = ROOT / "data" / "processed" / "projects.json"
    with open(projects_path, encoding="utf-8") as f:
        projects = json.load(f)

    from app.database_pdf import PdfSessionLocal
    from app.models.pdf_models import PdfDocument

    with PdfSessionLocal() as db:
        db_docs = db.query(PdfDocument).filter(PdfDocument.status == "ready").all()

    matched = 0
    path_fixed = 0
    skipped = 0
    missing = 0

    for project in projects:
        if project.get("documentId") is not None:
            skipped += 1
            continue

        fn = _pfn(project)
        if not fn:
            print(f"  NOPDF  {project['id']:10s}")
            missing += 1
            continue

        doc, needs_fix = _find_match(fn, db_docs)

        if doc:
            project["documentId"] = doc.id
            matched += 1
            if needs_fix:
                old_path = project["pdfPath"]
                project["pdfPath"] = _pfolder(project) + doc.filename
                path_fixed += 1
                print(
                    f"  FIX    {project['id']:10s}  doc_id={doc.id:5d}\n"
                    f"         old: {old_path}\n"
                    f"         new: {project['pdfPath']}"
                )
            else:
                print(f"  MATCH  {project['id']:10s}  doc_id={doc.id:5d}  {fn}")
        else:
            print(f"  MISS   {project['id']:10s}  {fn}")
            missing += 1

    print(
        f"\nMatched: {matched}  pdfPath fixed: {path_fixed}  "
        f"Already set: {skipped}  No match: {missing}"
    )

    if args.dry_run:
        print("[dry-run] No changes written.")
        return

    with open(projects_path, "w", encoding="utf-8") as f:
        json.dump(projects, f, ensure_ascii=False, indent=2)
    print(f"Wrote {projects_path}")


if __name__ == "__main__":
    main()
