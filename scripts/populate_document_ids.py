#!/usr/bin/env python
"""Populate documentId in data/processed/projects.json.

Matches each project's pdfPath filename against pdf_documents.filename (ilike),
writes the matched pdf_documents.id back to the JSON as the "documentId" field.

Usage (from repo root):
    python scripts/populate_document_ids.py [--dry-run]

Requires DATABASE_URL (or PDF_DATABASE_URL) in the environment or a .env file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Force UTF-8 output on Windows where the default console encoding (CP950/GBK)
# can't represent all CJK characters in filenames.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


def _match_document(db, filename: str):
    from app.models.pdf_models import PdfDocument

    safe_fn = filename.replace("%", r"\%").replace("_", r"\_")
    return (
        db.query(PdfDocument.id, PdfDocument.filename)
        .filter(
            PdfDocument.filename.ilike(f"%{safe_fn}%", escape="\\"),
            PdfDocument.status == "ready",
        )
        .first()
    )


def main():
    parser = argparse.ArgumentParser(description="Populate documentId in projects.json")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    args = parser.parse_args()

    projects_path = ROOT / "data" / "processed" / "projects.json"
    with open(projects_path, encoding="utf-8") as f:
        projects = json.load(f)

    from app.database_pdf import PdfSessionLocal

    matched = 0
    skipped = 0
    missing = 0

    with PdfSessionLocal() as db:
        for project in projects:
            if project.get("documentId") is not None:
                skipped += 1
                continue
            pdf_path = project.get("pdfPath")
            if not pdf_path:
                missing += 1
                continue
            filename = pdf_path.replace("\\", "/").split("/")[-1]
            row = _match_document(db, filename)
            if row:
                print(f"  MATCH  {project['id']:10s}  doc_id={row.id:5d}  {filename}")
                project["documentId"] = row.id
                matched += 1
            else:
                print(f"  MISS   {project['id']:10s}  {filename}")
                missing += 1

    print(f"\nMatched: {matched}  Already set: {skipped}  No match/no pdf: {missing}")

    if args.dry_run:
        print("[dry-run] No changes written.")
        return

    with open(projects_path, "w", encoding="utf-8") as f:
        json.dump(projects, f, ensure_ascii=False, indent=2)
    print(f"Wrote {projects_path}")


if __name__ == "__main__":
    main()
