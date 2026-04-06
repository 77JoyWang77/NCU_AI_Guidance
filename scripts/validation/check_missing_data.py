"""
Step 1: 缺失資料檢查
比對課程原始資料（基準）vs 課程地圖 vs 應修科目表，輸出缺失報告

輸出：data/processed/missing_report.json
"""

import os
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent

# === 路徑設定 ===
RAW_COURSES_DIR   = BASE_DIR / "data" / "raw" / "courses"
CURRICULUM_MAP_DIR = BASE_DIR / "data" / "raw" / "課程地圖"
REQUIREMENTS_DIR  = BASE_DIR / "data" / "raw" / "應修科目表"
PROGRAMS_DIR      = BASE_DIR / "data" / "raw" / "學分學程"
OUTPUT_PATH       = BASE_DIR / "data" / "processed" / "validation" / "missing_report.json"

# 檔名已手動修正，不需要別名對照
DEPT_ALIASES = {}

# 排除不需要課程地圖/應修科目表的單位
EXCLUDED_UNITS = {
    "軍訓室", "核心通識課程", "通識教育中心",
    "臺灣大專院校人工智慧學程聯盟", "語言中心",
    "學務處-服務學習發展中心", "學務處-職涯發展中心",
    "總教學中心", "體育室", "師資培育中心",
    # 院級單位（本身沒有獨立課程地圖需求）
    "工學院", "文學院", "生醫理工學院", "理學院",
    "客家學院", "管理學院", "資訊電機學院",
    "地球科學學院", "永續與綠能科技研究學院",
}


def get_all_departments() -> dict[str, list[str]]:
    """
    從 data/raw/courses/ 的資料夾結構取得完整系所清單。
    回傳 { "系所名稱": ["114_1", "114_2", ...] }
    """
    dept_semesters: dict[str, list[str]] = {}
    for semester_dir in sorted(RAW_COURSES_DIR.iterdir()):
        if not semester_dir.is_dir():
            continue
        semester = semester_dir.name
        for json_file in semester_dir.glob("*.json"):
            # 格式：學院_系所.json
            dept_name = json_file.stem.split("_", 1)[-1]  # 取 _ 後面的部分
            dept_semesters.setdefault(dept_name, []).append(semester)
    return dept_semesters


def get_target_departments(all_depts: dict[str, list[str]]) -> set[str]:
    """篩選出需要課程地圖/應修科目表的系所（排除中心/院級單位）"""
    return {dept for dept in all_depts if dept not in EXCLUDED_UNITS}


def normalize_filename_stem(stem: str) -> str:
    """
    將檔案 stem 標準化：
    - 移除學年後綴（_113, _114）
    - 套用別名對照
    例如：
      "數學系_計算與資料科學組_114" → "數學系_計算與資料科學組"
      "化學系"                     → "化學學系"
      "地科院學士班_114"           → "地球科學學院學士班"
    """
    # 移除學年後綴
    stem = re.sub(r'_\d{3}$', '', stem)
    # 整體別名對照
    if stem in DEPT_ALIASES:
        return DEPT_ALIASES[stem]
    # 前綴別名（如「地科院學士班_客家社會及政策組」）
    for alias, standard in DEPT_ALIASES.items():
        if stem.startswith(alias):
            stem = standard + stem[len(alias):]
    return stem


def get_curriculum_map_coverage() -> dict[str, str]:
    """
    回傳課程地圖已覆蓋的系所：
    { "系所名稱（標準化）": "原始檔名.副檔名" }
    """
    coverage = {}
    for f in CURRICULUM_MAP_DIR.iterdir():
        if f.is_file():
            normalized = normalize_filename_stem(f.stem)
            coverage[normalized] = f.name
    return coverage


def get_requirements_coverage() -> dict[str, str]:
    """
    回傳應修科目表已覆蓋的系所：
    { "系所名稱（標準化）": "原始檔名.副檔名" }
    注意：客家語文暨社會科學學系分成兩組，視為一個系所覆蓋
    """
    coverage = {}
    for f in REQUIREMENTS_DIR.rglob("*.pdf"):
        if f.is_file():
            normalized = normalize_filename_stem(f.stem)
            # 客家系的兩個組視為一個系所
            base_dept = normalized.split("_")[0] if "_" in normalized else normalized
            # 若已有記錄就保留（只標記「有」即可）
            if base_dept not in coverage:
                coverage[base_dept] = f.name
            # 把完整名稱也記錄
            coverage[normalized] = f.name
    return coverage


def build_report(
    target_depts: set[str],
    all_depts: dict[str, list[str]],
    curriculum_coverage: dict[str, str],
    requirements_coverage: dict[str, str],
) -> dict:
    """建立完整的缺失報告"""

    missing_curriculum = []
    missing_requirements = []
    fully_covered = []

    for dept in sorted(target_depts):
        has_curriculum  = dept in curriculum_coverage
        has_requirement = dept in requirements_coverage

        # 某些系所有組別分法（如數學系），只要有任一組就算覆蓋
        if not has_curriculum:
            # 檢查是否有以此系所為前綴的組別
            has_curriculum = any(
                k.startswith(dept) for k in curriculum_coverage
            )
        if not has_requirement:
            has_requirement = any(
                k.startswith(dept) for k in requirements_coverage
            )

        semesters = all_depts.get(dept, [])
        entry = {
            "dept": dept,
            "semesters": semesters,
        }

        if not has_curriculum:
            missing_curriculum.append(entry)
        if not has_requirement:
            missing_requirements.append(entry)
        if has_curriculum and has_requirement:
            fully_covered.append(dept)

    return {
        "summary": {
            "total_target_depts": len(target_depts),
            "missing_curriculum_map": len(missing_curriculum),
            "missing_requirements_table": len(missing_requirements),
            "fully_covered": len(fully_covered),
        },
        "missing_curriculum_map": missing_curriculum,
        "missing_requirements_table": missing_requirements,
        "fully_covered": fully_covered,
        "file_coverage": {
            "curriculum_map_files": {
                v: k for k, v in curriculum_coverage.items()
            },
            "requirements_files": {
                v: k for k, v in requirements_coverage.items()
            },
        },
        "aliases_applied": DEPT_ALIASES,
    }


def print_report(report: dict):
    """人類可讀的報告輸出"""
    s = report["summary"]
    print("=" * 60)
    print("缺失資料報告")
    print("=" * 60)
    print(f"目標系所總數：{s['total_target_depts']}")
    print(f"完整覆蓋（兩份都有）：{s['fully_covered']}")
    print()

    print(f"【課程地圖缺失】共 {s['missing_curriculum_map']} 個")
    print("-" * 40)
    for item in report["missing_curriculum_map"]:
        print(f"  ❌ {item['dept']}  （有課程資料於：{', '.join(item['semesters'])}）")

    print()
    print(f"【應修科目表缺失】共 {s['missing_requirements_table']} 個")
    print("-" * 40)
    for item in report["missing_requirements_table"]:
        print(f"  ❌ {item['dept']}  （有課程資料於：{', '.join(item['semesters'])}）")

    print()
    print("【命名別名對照】")
    for alias, standard in report["aliases_applied"].items():
        print(f"  {alias} → {standard}")
    print("=" * 60)


def main():
    print("讀取系所基準清單...")
    all_depts     = get_all_departments()
    target_depts  = get_target_departments(all_depts)

    print(f"目標系所：{len(target_depts)} 個")

    print("讀取課程地圖覆蓋...")
    curriculum_coverage = get_curriculum_map_coverage()

    print("讀取應修科目表覆蓋...")
    requirements_coverage = get_requirements_coverage()

    print("比對缺失...")
    report = build_report(
        target_depts, all_depts,
        curriculum_coverage, requirements_coverage
    )

    print_report(report)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 報告已輸出至：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()
