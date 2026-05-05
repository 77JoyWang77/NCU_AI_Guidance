"""
批次同步 when 欄位（以來源 verified=True 為準）。

用途：
- 來源資料夾（預設）：drive-download-20260425T163123Z-3-001
- 目標資料夾（預設）：data/processed/schedule_draft
- 只會修改目標檔案中的 "when" 值。
- 更新條件改為：來源資料中該課程 code 的 verified=True 才會回填。
- 其他欄位完全不改（包含 when_auto、note、credits...）。

比對規則：
1. 以「檔名（不含副檔名）」對應系所檔案。
   例如：來源「經濟學系.json」對應目標子資料夾內同名「經濟學系.json」。
2. 在單一系所檔內，以課號 code 對應來源課程的 when。
3. 若來源同一 code 出現多個不同 when，視為衝突，該 code 不更新。

使用方式：
python scripts/extraction/requirements/update_when_for_verified.py --dry-run
python scripts/extraction/requirements/update_when_for_verified.py

自訂路徑：
python scripts/extraction/requirements/update_when_for_verified.py ^
  --source-dir drive-download-20260425T163123Z-3-001 ^
  --target-dir data/processed/schedule_draft
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple


BASE_DIR = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE_DIR = BASE_DIR / "new_data"
DEFAULT_TARGET_DIR = BASE_DIR / "data" / "processed" / "schedule_draft"


def walk_course_dicts(node) -> Iterable[dict]:
    """遞迴走訪所有課程物件（含 code 欄位的 dict）。"""
    if isinstance(node, dict):
        if "code" in node:
            yield node
        for value in node.values():
            yield from walk_course_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_course_dicts(item)


def walk_course_entries(node, path: str = "") -> Iterable[Tuple[str, dict]]:
    """遞迴走訪所有課程物件，回傳 (結構路徑, 課程dict)。"""
    if isinstance(node, dict):
        if "code" in node:
            yield path, node
        for k, v in node.items():
            child_path = f"{path}.{k}" if path else k
            yield from walk_course_entries(v, child_path)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            child_path = f"{path}[{i}]"
            yield from walk_course_entries(item, child_path)


def build_source_when_map(source_obj: dict) -> Tuple[Dict[Tuple[str, str], str], Dict[str, str], Set[str], Set[Tuple[str, str]], Set[str], Set[str]]:
    """
    建立來源對照表（僅收錄來源 verified=True 的課程）。
    1) path+code -> when（優先）
    2) code -> when（fallback）
    若 path+code 或 code 對應到多個不同 when，加入 conflicts 並從 map 移除。
    """
    path_seen: Dict[Tuple[str, str], str] = {}
    path_conflicts: Set[Tuple[str, str]] = set()
    code_seen: Dict[str, str] = {}
    code_conflicts: Set[str] = set()
    source_all_codes: Set[str] = set()
    source_verified_codes: Set[str] = set()

    for path, course in walk_course_entries(source_obj):
        if course.get("verified") is not True:
            continue

        code = str(course.get("code", "")).strip()
        if not code:
            continue
        source_all_codes.add(code)
        source_verified_codes.add(code)

        when = str(course.get("when", "")).strip()
        pkey = (path, code)
        if pkey not in path_seen:
            path_seen[pkey] = when
        elif path_seen[pkey] != when:
            path_conflicts.add(pkey)

        if code not in code_seen:
            code_seen[code] = when
        elif code_seen[code] != when:
            code_conflicts.add(code)

    for pkey in path_conflicts:
        path_seen.pop(pkey, None)
    for code in code_conflicts:
        code_seen.pop(code, None)

    return path_seen, code_seen, source_all_codes, path_conflicts, code_conflicts, source_verified_codes


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_dept_name(name: str) -> str:
    """
    檔名正規化規則：
    - 去除前後空白
    - 刪除檔名尾端的流水號：" (1)", "（1）"
    - 移除所有空白字元
    """
    s = name.strip()
    s = re.sub(r"\s*[\(（]\d+[\)）]\s*$", "", s)
    s = re.sub(r"\s+", "", s)
    return s


def find_target_files(target_dir: Path) -> Dict[str, Path]:
    """回傳 {正規化檔名: 完整路徑}，若重名採第一個並列出警告。"""
    mapping: Dict[str, Path] = {}
    duplicates: Dict[str, List[Path]] = {}

    for file in target_dir.rglob("*.json"):
        key = normalize_dept_name(file.stem)
        if key in mapping:
            duplicates.setdefault(key, [mapping[key]]).append(file)
            continue
        mapping[key] = file

    if duplicates:
        print("[WARN] 目標資料夾存在重複檔名，將採用第一個找到的檔案：")
        for key, paths in sorted(duplicates.items()):
            joined = " | ".join(str(p.relative_to(BASE_DIR)) for p in paths)
            print(f"  - {key}: {joined}")

    return mapping


def to_relative_str(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: List[dict], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def update_one_file(source_path: Path, target_path: Path, dry_run: bool) -> Tuple[int, int, int, int, int, List[dict], List[dict]]:
    """
    回傳 (updated_when_count, marked_verified_count, skipped_conflict_count, skipped_missing_source_when_count, scanned_target_course_count, conflict_rows, missing_rows)
    """
    src_obj = load_json(source_path)
    tgt_obj = load_json(target_path)

    source_path_when_map, source_code_when_map, source_all_codes, path_conflicts, code_conflicts, source_verified_codes = build_source_when_map(src_obj)

    updated = 0
    marked_verified = 0
    skipped_conflict = 0
    skipped_missing = 0
    scanned_target_courses = 0
    conflict_rows: List[dict] = []
    missing_rows: List[dict] = []
    changed = False

    source_rel = to_relative_str(source_path)
    target_rel = to_relative_str(target_path)
    dept_name = target_path.stem

    for path, course in walk_course_entries(tgt_obj):
        scanned_target_courses += 1

        code = str(course.get("code", "")).strip()
        if not code:
            continue

        pkey = (path, code)
        new_when = None

        # 優先用 path+code 精準對應（可消除同 code 跨群組衝突）
        if pkey in source_path_when_map:
            new_when = source_path_when_map[pkey]
        elif pkey in path_conflicts:
            skipped_conflict += 1
            conflict_rows.append(
                {
                    "dept": dept_name,
                    "code": code,
                    "source_file": source_rel,
                    "target_file": target_rel,
                    "target_when": str(course.get("when", "")),
                    "path": path,
                    "conflict_type": "path_conflict",
                }
            )
            continue
        elif code in source_code_when_map:
            # 找不到同路徑時，退回 code 對應
            new_when = source_code_when_map[code]
        elif code in code_conflicts:
            skipped_conflict += 1
            conflict_rows.append(
                {
                    "dept": dept_name,
                    "code": code,
                    "source_file": source_rel,
                    "target_file": target_rel,
                    "target_when": str(course.get("when", "")),
                    "path": path,
                    "conflict_type": "code_conflict",
                }
            )
            continue

        if new_when is None:
            skipped_missing += 1
            missing_rows.append(
                {
                    "dept": dept_name,
                    "code": code,
                    "source_file": source_rel,
                    "target_file": target_rel,
                    "target_when": str(course.get("when", "")),
                    "path": path,
                    "missing_reason": "source_code_exists_but_not_verified_true" if code in source_all_codes and code not in source_verified_codes else "source_code_not_found",
                }
            )
            continue

        old_when = str(course.get("when", ""))

        if old_when != new_when:
            course["when"] = new_when
            updated += 1
            changed = True

        if course.get("verified") is not True:
            course["verified"] = True
            marked_verified += 1
            changed = True

    if changed and not dry_run:
        save_json(target_path, tgt_obj)

    return updated, marked_verified, skipped_conflict, skipped_missing, scanned_target_courses, conflict_rows, missing_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="以來源 verified=True 回填 when（路徑+課號優先對應）")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR, help="來源 JSON 資料夾")
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET_DIR, help="目標 JSON 資料夾")
    parser.add_argument("--dry-run", action="store_true", help="只顯示將變更的數量，不寫入檔案")
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=BASE_DIR / "data" / "processed" / "validation",
        help="報表輸出資料夾（預設 data/processed/validation）",
    )
    args = parser.parse_args()

    source_dir = (args.source_dir if args.source_dir.is_absolute() else BASE_DIR / args.source_dir).resolve()
    target_dir = (args.target_dir if args.target_dir.is_absolute() else BASE_DIR / args.target_dir).resolve()

    if not source_dir.exists() or not source_dir.is_dir():
        raise SystemExit(f"[ERROR] 來源資料夾不存在：{source_dir}")
    if not target_dir.exists() or not target_dir.is_dir():
        raise SystemExit(f"[ERROR] 目標資料夾不存在：{target_dir}")

    source_files = sorted(source_dir.glob("*.json"))
    target_map = find_target_files(target_dir)

    total_files_matched = 0
    total_updated = 0
    total_marked_verified = 0
    total_conflict = 0
    total_missing = 0
    total_no_target = 0
    total_scanned_target_courses = 0
    no_target_names: List[str] = []
    matched_target_paths: Set[Path] = set()
    all_conflict_rows: List[dict] = []
    all_missing_rows: List[dict] = []

    for src in source_files:
        dept_name = src.stem
        dept_key = normalize_dept_name(dept_name)
        tgt = target_map.get(dept_key)
        if tgt is None:
            total_no_target += 1
            no_target_names.append(dept_name)
            print(f"[SKIP] 找不到對應目標檔：{dept_name}.json")
            continue

        total_files_matched += 1
        matched_target_paths.add(tgt)
        updated, marked_verified, skipped_conflict, skipped_missing, scanned_target_courses, conflict_rows, missing_rows = update_one_file(src, tgt, args.dry_run)
        total_updated += updated
        total_marked_verified += marked_verified
        total_conflict += skipped_conflict
        total_missing += skipped_missing
        total_scanned_target_courses += scanned_target_courses
        all_conflict_rows.extend(conflict_rows)
        all_missing_rows.extend(missing_rows)

        if updated > 0 or marked_verified > 0:
            mode = "DRY-RUN" if args.dry_run else "UPDATED"
            rel_tgt = tgt.relative_to(BASE_DIR)
            print(f"[{mode}] {rel_tgt}: 更新 {updated} 筆 when，標記 {marked_verified} 筆 verified=true")

    print("\n=== Summary ===")
    print(f"source files         : {len(source_files)}")
    print(f"matched target files : {total_files_matched}")
    print(f"no target file       : {total_no_target}")
    print(f"target courses scanned : {total_scanned_target_courses}")
    print(f"updated when         : {total_updated}")
    print(f"marked verified true : {total_marked_verified}")
    print(f"skipped (conflict)   : {total_conflict}")
    print(f"skipped (no source)  : {total_missing}")
    print(f"mode                 : {'dry-run' if args.dry_run else 'write'}")

    if no_target_names:
        print("\n--- Missing target by source dept ---")
        for name in sorted(no_target_names):
            print(f"- {name}")

    target_only = sorted(
        [p for p in target_map.values() if p not in matched_target_paths],
        key=lambda x: str(x),
    )
    if target_only:
        print("\n--- Target depts not covered by source ---")
        for p in target_only:
            print(f"- {p.relative_to(BASE_DIR)}")

    report_dir = (args.report_dir if args.report_dir.is_absolute() else BASE_DIR / args.report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    conflict_json = report_dir / f"when_update_conflicts_{stamp}.json"
    conflict_csv = report_dir / f"when_update_conflicts_{stamp}.csv"
    missing_json = report_dir / f"when_update_no_source_{stamp}.json"
    missing_csv = report_dir / f"when_update_no_source_{stamp}.csv"

    write_json(
        conflict_json,
        {
            "generated_at": stamp,
            "count": len(all_conflict_rows),
            "rows": all_conflict_rows,
        },
    )
    write_csv(
        conflict_csv,
        all_conflict_rows,
        ["dept", "code", "source_file", "target_file", "target_when", "path", "conflict_type"],
    )

    write_json(
        missing_json,
        {
            "generated_at": stamp,
            "count": len(all_missing_rows),
            "rows": all_missing_rows,
        },
    )
    write_csv(
        missing_csv,
        all_missing_rows,
        ["dept", "code", "source_file", "target_file", "target_when", "path", "missing_reason"],
    )

    print("\n--- Reports ---")
    print(f"- {to_relative_str(conflict_json)}")
    print(f"- {to_relative_str(conflict_csv)}")
    print(f"- {to_relative_str(missing_json)}")
    print(f"- {to_relative_str(missing_csv)}")


if __name__ == "__main__":
    main()
