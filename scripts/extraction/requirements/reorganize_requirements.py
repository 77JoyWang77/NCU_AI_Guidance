"""
從 data/processed/schedule_draft/ 讀取各系所的 when 資料，
更新回 data/processed/curriculum_requirements_114.json。

流程：schedule_draft/學院/系所.json → curriculum_requirements_114.json
"""

import json
from pathlib import Path

BASE_DIR  = Path(__file__).parent.parent.parent.parent   # scripts/extraction/requirements/ → project root
PROC_DIR  = BASE_DIR / "data" / "processed"
SRC_JSON  = PROC_DIR / "curriculum_requirements_114.json"
DRAFT_DIR = PROC_DIR / "schedule_draft"


def collect_when_from_draft(draft_node: dict) -> dict:
    """從 draft 節點收集 code → {when, when_auto}（走訪所有巢狀課程）。"""
    result: dict[str, dict] = {}

    def _walk(node):
        if isinstance(node, dict):
            if "code" in node and "when" in node:
                code = node["code"]
                result[code] = {
                    "when":      node.get("when", ""),
                    "when_auto": node.get("when_auto", False),
                }
            for v in node.values():
                if isinstance(v, (dict, list)):
                    _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(draft_node)
    return result


def collect_group_when(draft_node: dict) -> dict:
    """group_label → {code → {when, when_auto}}，用於組別課程的精確匹配。"""
    result: dict[str, dict] = {}
    for grp in draft_node.get("groups", []):
        gl = grp.get("group_label", "")
        if not gl:
            continue
        grp_map: dict[str, dict] = {}
        for c in grp.get("required_courses", []):
            code = c.get("code", "")
            if code and c.get("when"):
                grp_map[code] = {
                    "when":      c["when"],
                    "when_auto": c.get("when_auto", False),
                }
        result[gl] = grp_map
    return result


def apply_when_to_node(target: dict, flat_lookup: dict, group_lookup: dict) -> None:
    """遞迴地把 when 從 lookup 套用到 target（in-place）。"""

    def _apply(node, grp_label=None):
        if isinstance(node, list):
            for item in node:
                _apply(item, grp_label)
        elif isinstance(node, dict):
            if "code" in node and "departments" not in node:
                code = node.get("code", "")
                # 優先用組別專屬 when，fallback 到全系 when
                info = None
                if grp_label and grp_label in group_lookup:
                    info = group_lookup[grp_label].get(code)
                if info is None:
                    info = flat_lookup.get(code)
                if info and info.get("when"):
                    node["when"] = info["when"]
            else:
                # 處理 groups 層（帶入 group_label）
                grps = node.get("groups", [])
                if isinstance(grps, list):
                    for grp in grps:
                        if not isinstance(grp, dict):
                            continue
                        gl = grp.get("group_label", "")
                        _apply(grp.get("required_courses", []), gl)
                # 其他 list / dict 欄位繼續遞迴
                for k, v in node.items():
                    if k != "groups" and isinstance(v, (list, dict)):
                        _apply(v, grp_label)

    _apply(target)


def main():
    print(f"BASE_DIR: {BASE_DIR}")
    print(f"SRC_JSON: {SRC_JSON}")
    print(f"DRAFT_DIR: {DRAFT_DIR}\n")

    if not SRC_JSON.exists():
        print(f"❌ 找不到 {SRC_JSON}")
        return
    if not DRAFT_DIR.exists():
        print(f"❌ 找不到 {DRAFT_DIR}")
        return

    raw = json.loads(SRC_JSON.read_text(encoding="utf-8"))
    total_updated = 0
    total_skipped = 0

    for college in raw.get("colleges", []):
        col_name = college.get("name", "")
        col_draft_dir = DRAFT_DIR / col_name

        for dept in college.get("departments", []):
            dept_name = dept.get("name", "")
            draft_file = col_draft_dir / f"{dept_name}.json"
            if not draft_file.exists():
                print(f"  ⚠️  找不到 {col_name}/{dept_name}.json，跳過")
                total_skipped += 1
                continue
            draft_data = json.loads(draft_file.read_text(encoding="utf-8"))
            flat_lk    = collect_when_from_draft(draft_data)
            group_lk   = collect_group_when(draft_data)
            apply_when_to_node(dept, flat_lk, group_lk)
            total_updated += 1
            print(f"  ✅ {col_name}/{dept_name}（{len(flat_lk)} 門課）")

        for bp in college.get("college_bachelor_programs", []):
            bp_name = bp.get("name", "")
            draft_file = col_draft_dir / f"{bp_name}.json"
            if not draft_file.exists():
                print(f"  ⚠️  找不到 {col_name}/{bp_name}.json，跳過")
                total_skipped += 1
                continue
            draft_data = json.loads(draft_file.read_text(encoding="utf-8"))
            flat_lk    = collect_when_from_draft(draft_data)
            group_lk   = collect_group_when(draft_data)
            apply_when_to_node(bp, flat_lk, group_lk)
            total_updated += 1
            print(f"  ✅ {col_name}/{bp_name}")

    SRC_JSON.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n{'='*50}")
    print(f"完成！更新 {total_updated} 個系所/學程，跳過 {total_skipped} 個")
    print(f"輸出：{SRC_JSON}")


if __name__ == "__main__":
    main()
