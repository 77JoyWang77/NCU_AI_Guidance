"""Import step2/step3 summaries into processed app data.

Step2 is attached to projects for the research-plan page.
Step3 is converted into assessment questions for the interest scale.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = ROOT / "data" / "raw" / "step2_step3_summaries.jsonl"
PROJECTS_PATH = ROOT / "data" / "processed" / "projects.json"
ASSESSMENT_PATH = ROOT / "data" / "processed" / "assessment_questions.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc
    return rows


def normalized_filename(value: str | None) -> str:
    if not value:
        return ""
    return value.replace("\\", "/").split("/")[-1].strip()


def build_project_indexes(projects: list[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_document_id: dict[int, dict[str, Any]] = {}
    by_filename: dict[str, dict[str, Any]] = {}

    for project in projects:
        document_id = project.get("documentId")
        if document_id is not None:
            by_document_id[int(document_id)] = project
        filename = normalized_filename(project.get("pdfPath"))
        if filename:
            by_filename[filename] = project

    return by_document_id, by_filename


def match_project(
    row: dict[str, Any],
    by_document_id: dict[int, dict[str, Any]],
    by_filename: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    document = row.get("document") or {}
    document_id = document.get("id")
    if document_id is not None and int(document_id) in by_document_id:
        return by_document_id[int(document_id)]

    filename = normalized_filename(document.get("filename"))
    if filename and filename in by_filename:
        return by_filename[filename]

    return None


def apply_step2_to_projects(
    rows: list[dict[str, Any]],
    projects: list[dict[str, Any]],
) -> tuple[int, list[int]]:
    by_document_id, by_filename = build_project_indexes(projects)
    unmatched: list[int] = []
    updated = 0

    for row in rows:
        document = row.get("document") or {}
        project = match_project(row, by_document_id, by_filename)
        if project is None:
            unmatched.append(int(document.get("id", -1)))
            continue

        step2 = row.get("step2") or {}
        project["motivation"] = step2.get("motivation", "")
        project["method"] = step2.get("method", "")
        project["result"] = step2.get("results", "")
        project["tags"] = step2.get("tags", [])
        updated += 1

    return updated, unmatched


def make_assessment_item(
    row: dict[str, Any],
    project: dict[str, Any],
    mode: str,
    question_id: int,
) -> dict[str, Any]:
    step2 = row.get("step2") or {}
    step3 = row.get("step3") or {}
    return {
        "id": f"q{question_id:03d}",
        "mode": mode,
        "department": project.get("department") or (row.get("document") or {}).get("department", ""),
        "title": project.get("title") or normalized_filename((row.get("document") or {}).get("filename")),
        "intro": step3.get("intro", ""),
        "questions": step3.get("questions", []),
        "tags": step2.get("tags", []),
        "sourceDocumentId": (row.get("document") or {}).get("id"),
        "projectId": project.get("id"),
    }


def balanced_order(
    matched: list[tuple[dict[str, Any], dict[str, Any]]],
    seed: int,
    limit: int | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rng = random.Random(seed)
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}

    for row, project in matched:
        department = project.get("department") or (row.get("document") or {}).get("department", "")
        grouped.setdefault(department, []).append((row, project))

    departments = list(grouped)
    rng.shuffle(departments)
    for items in grouped.values():
        rng.shuffle(items)

    ordered: list[tuple[dict[str, Any], dict[str, Any]]] = []
    while departments and (limit is None or len(ordered) < limit):
        next_departments: list[str] = []
        for department in departments:
            items = grouped[department]
            if not items:
                continue
            ordered.append(items.pop())
            if limit is not None and len(ordered) >= limit:
                break
            if items:
                next_departments.append(department)
        departments = next_departments

    return ordered


def build_assessment_questions(
    rows: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    seed: int,
) -> tuple[list[dict[str, Any]], int, list[int]]:
    by_document_id, by_filename = build_project_indexes(projects)
    matched: list[tuple[dict[str, Any], dict[str, Any]]] = []
    unmatched: list[int] = []

    for row in rows:
        document = row.get("document") or {}
        project = match_project(row, by_document_id, by_filename)
        if project is None:
            unmatched.append(int(document.get("id", -1)))
            continue
        matched.append((row, project))

    questions: list[dict[str, Any]] = []
    question_id = 1

    for mode, items in (
        ("grade1", balanced_order(matched, seed + 1, limit=40)),
        ("grade2", balanced_order(matched, seed + 2)),
        ("grade3", balanced_order(matched, seed + 3, limit=50)),
    ):
        for row, project in items:
            questions.append(make_assessment_item(row, project, mode, question_id))
            question_id += 1

    return questions, len(matched), unmatched


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=RAW_PATH)
    parser.add_argument("--projects", type=Path, default=PROJECTS_PATH)
    parser.add_argument("--assessment", type=Path, default=ASSESSMENT_PATH)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows = read_jsonl(args.raw)
    projects = read_json(args.projects)

    project_count, project_unmatched = apply_step2_to_projects(rows, projects)
    assessment_questions, assessment_count, assessment_unmatched = build_assessment_questions(rows, projects, args.seed)

    if not args.dry_run:
        write_json(args.projects, projects)
        write_json(args.assessment, assessment_questions)

    print(f"raw rows: {len(rows)}")
    print(f"projects updated from step2: {project_count}")
    print(f"assessment source rows from step3: {assessment_count}")
    print(f"assessment questions written: {len(assessment_questions)}")
    if project_unmatched or assessment_unmatched:
        unmatched = sorted(set(project_unmatched + assessment_unmatched))
        print(f"unmatched document ids: {unmatched}")


if __name__ == "__main__":
    main()
