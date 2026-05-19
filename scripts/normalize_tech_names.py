"""
normalize_tech_names.py — 正規化 nlp_tech_nodes.json 與 nlp_simplified_concepts.json
                          中的技術名稱大小寫，消除 23 組重複節點衝突。

用法：
    python scripts/normalize_tech_names.py [--dry-run]

--dry-run：只顯示會修改哪些條目，不寫入檔案。
"""

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent

# ──────────────────────────────────────────────────────────────────────────────
# 正規化對照表（lowercase key → canonical form）
# 依各工具 / 語言官方命名決定
# ──────────────────────────────────────────────────────────────────────────────
CANONICAL: dict[str, str] = {
    "arena":       "Arena",
    "code v":      "Code V",
    "fiori":       "Fiori",
    "fortran":     "Fortran",
    "github":      "GitHub",
    "labview":     "LabVIEW",
    "latex":       "LaTeX",
    "linux":       "Linux",
    "llama":       "LLaMA",
    "matlab":      "MATLAB",
    "matplotlib":  "Matplotlib",
    "notebooklm":  "NotebookLM",
    "numpy":       "NumPy",
    "obspy":       "ObsPy",
    "pandas":      "pandas",
    "plotly":      "Plotly",
    "python":      "Python",
    "rviz":        "RViz",
    "scikit-learn": "scikit-learn",
    "scipy":       "SciPy",
    "simulink":    "Simulink",
    "solidworks":  "SolidWorks",
    "stata":       "Stata",
}


def normalize_list(items: list[str]) -> tuple[list[str], int]:
    """正規化字串列表，回傳 (新列表, 修改次數)。去重後維持首次出現順序。"""
    seen: set[str] = set()
    result: list[str] = []
    changes = 0
    for item in items:
        item = item.strip()
        if not item:
            continue
        canonical = CANONICAL.get(item.lower(), item)
        if canonical != item:
            changes += 1
        if canonical.lower() not in seen:
            seen.add(canonical.lower())
            result.append(canonical)
        # else: 重複項直接捨棄
    return result, changes


def process_tech_nodes(path: Path, dry_run: bool) -> int:
    """處理 nlp_tech_nodes.json，回傳修改筆數。"""
    data: dict = json.loads(path.read_text(encoding="utf-8"))
    total_changes = 0
    modified_courses: list[str] = []

    for code, entry in data.items():
        if not isinstance(entry, dict):
            continue
        course_changes = 0
        for field in ("languages", "tools"):
            original = entry.get(field, [])
            normalized, n = normalize_list(original)
            if n > 0 or normalized != original:
                course_changes += n
                entry[field] = normalized
        if course_changes:
            total_changes += course_changes
            modified_courses.append(code)

    if dry_run:
        print(f"[DRY-RUN] {path.name}: {len(modified_courses)} 門課共 {total_changes} 項會被修改")
        for c in modified_courses[:20]:
            print(f"  {c}")
        if len(modified_courses) > 20:
            print(f"  ...（共 {len(modified_courses)} 門）")
    else:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ {path.name}: 修改 {len(modified_courses)} 門課，共 {total_changes} 項正規化")

    return total_changes


def process_simplified_concepts(path: Path, dry_run: bool) -> int:
    """處理 nlp_simplified_concepts.json，回傳修改筆數。"""
    if not path.exists():
        print(f"  跳過（不存在）：{path.name}")
        return 0

    data: dict = json.loads(path.read_text(encoding="utf-8"))
    total_changes = 0
    modified = []

    for code, entry in data.items():
        if not isinstance(entry, dict):
            continue
        course_changes = 0
        for field in ("languages", "tools"):
            original = entry.get(field, [])
            if not isinstance(original, list):
                continue
            normalized, n = normalize_list(original)
            if n > 0 or normalized != original:
                course_changes += n
                entry[field] = normalized
        if course_changes:
            total_changes += course_changes
            modified.append(code)

    if dry_run:
        print(f"[DRY-RUN] {path.name}: {len(modified)} 筆共 {total_changes} 項會被修改")
    else:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ {path.name}: 修改 {len(modified)} 筆，共 {total_changes} 項正規化")

    return total_changes


def main():
    parser = argparse.ArgumentParser(description="正規化 NLP 技術名稱大小寫")
    parser.add_argument("--dry-run", action="store_true", help="只顯示不寫入")
    args = parser.parse_args()

    print("=== 技術名稱正規化 ===\n")
    print(f"正規化規則數：{len(CANONICAL)}\n")

    nlp_dir = BASE / "data" / "processed" / "nlp"
    tech_path = nlp_dir / "nlp_tech_nodes.json"
    concepts_path = nlp_dir / "nlp_simplified_concepts.json"

    total = 0
    total += process_tech_nodes(tech_path, args.dry_run)
    total += process_simplified_concepts(concepts_path, args.dry_run)

    print(f"\n{'[DRY-RUN] 預計' if args.dry_run else ''}共正規化 {total} 項名稱。")
    if not args.dry_run:
        print("\n下一步：python scripts/graph/build_graph.py --enrich-only")


if __name__ == "__main__":
    main()
