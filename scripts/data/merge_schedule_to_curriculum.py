"""
merge_schedule_to_curriculum.py

以 data/processed/schedule_draft/ 作為人工驗證後的權威資料源，
重新輸出整合版 data/processed/curriculum_requirements_114.json。

規則：
- 保留 curriculum_requirements_114.json 的 metadata 與學院階層結構
- 對每個系所/學士班：若 schedule_draft 有對應 id → 以 schedule_draft 為主
- 去除驗證用欄位：when_auto、verified、note（全部為空，無實質資訊）
- 保留 when 欄位（這是本次驗證的核心輸出）
- dept_with_groups 的子群組已含在父系所的 groups 陣列中，一起處理

執行：
  python scripts/data/merge_schedule_to_curriculum.py
"""

import json
import re
from pathlib import Path

BASE = Path(__file__).parent.parent.parent
CURRICULUM_PATH = BASE / "data" / "processed" / "curriculum_requirements_114.json"
SCHEDULE_DIR    = BASE / "data" / "processed" / "schedule_draft"

STRIP_FIELDS = {"when_auto", "verified", "note"}


# ── 工具函式 ─────────────────────────────────────────────────────────────────

def strip_course(c: dict) -> dict:
    """去除課程 dict 中的驗證欄位。"""
    return {k: v for k, v in c.items() if k not in STRIP_FIELDS}


def strip_courses_in_obj(obj: dict) -> dict:
    """遞迴清理物件中所有課程欄位的驗證屬性。"""
    result = dict(obj)

    # 直接是課程列表的欄位
    for key in ("required_courses", "required_electives", "elective_courses",
                "cross_group_required", "college_required_courses",
                "common_required_courses", "foundation_courses",
                "application_courses", "cross_domain_required",
                "earth_system_courses", "first_domain_electives"):
        if key in result:
            result[key] = [strip_course(c) for c in result[key]]

    # ElectiveGroup 類型的欄位
    for key in ("elective_groups", "core_elective_groups",
                "college_required_elective_groups", "science_ability_groups",
                "other_elective_groups"):
        if key in result:
            groups = []
            for g in result[key]:
                g = dict(g)
                for ckey in ("courses", "option_a", "option_b", "option_c"):
                    if ckey in g:
                        g[ckey] = [strip_course(c) for c in g[ckey]]
                # slots
                if "slots" in g:
                    g["slots"] = [
                        {**s, "courses": [strip_course(c) for c in s.get("courses", [])]}
                        for s in g["slots"]
                    ]
                groups.append(g)
            result[key] = groups

    # 子群組
    for key in ("groups", "tracks", "specialization_tracks"):
        if key in result:
            result[key] = [strip_courses_in_obj(sub) for sub in result[key]]

    return result


def load_schedule_lookup() -> dict[str, dict]:
    """掃描 schedule_draft，以 id 為 key 回傳 dict。"""
    lookup: dict[str, dict] = {}
    for college_dir in SCHEDULE_DIR.iterdir():
        if not college_dir.is_dir():
            continue
        for dept_file in college_dir.glob("*.json"):
            try:
                data = json.loads(dept_file.read_text(encoding="utf-8"))
                did = data.get("id", "")
                if did:
                    lookup[did] = data
                    # 子群組（dept_with_groups）
                    for g in data.get("groups", []):
                        gid = g.get("id", "")
                        if gid and gid not in lookup:
                            lookup[gid] = g
                    # specialization_tracks（學院學士班）
                    for t in data.get("specialization_tracks", []):
                        tid = t.get("id", "")
                        if tid and tid not in lookup:
                            lookup[tid] = t
                            # track 的 groups（生醫領域等）
                            for g in t.get("groups", []):
                                gid = g.get("id", "")
                                if gid and gid not in lookup:
                                    lookup[gid] = g
            except Exception as e:
                print(f"  [WARN] {dept_file.name}: {e}")
    return lookup


# ── 合併邏輯 ─────────────────────────────────────────────────────────────────

def merge_dept(curr_dept: dict, sched_lookup: dict) -> dict:
    """
    以 schedule_draft 為主合併單一系所節點。
    若找不到對應 id 則直接回傳清理後的 curr_dept。
    """
    did = curr_dept.get("id", "")
    sched = sched_lookup.get(did)

    if sched is None:
        # 沒有 schedule_draft 資料 → 保留 curriculum 資料，僅清理課程欄位
        return strip_courses_in_obj(curr_dept)

    # 以 schedule_draft 為基礎，補上 curriculum 中有但 schedule_draft 無的欄位
    merged = dict(sched)

    # 保留 curriculum 有、schedule_draft 沒有的 elective_groups（某些選修群只在 curriculum）
    for key in ("elective_groups",):
        if key not in merged and key in curr_dept:
            merged[key] = curr_dept[key]

    # graduation_rules：schedule_draft 優先，但補上 curriculum 中有而 sched 沒有的 type
    if curr_dept.get("graduation_rules") and merged.get("graduation_rules") is not None:
        sched_types = {r.get("type") for r in merged["graduation_rules"]}
        for r in curr_dept.get("graduation_rules", []):
            if r.get("type") and r["type"] not in sched_types:
                merged.setdefault("graduation_rules", []).append(r)

    return strip_courses_in_obj(merged)


def process_college(college: dict, sched_lookup: dict) -> dict:
    college = dict(college)

    new_depts = []
    for dept in college.get("departments", []):
        merged = merge_dept(dept, sched_lookup)
        # dept_with_groups：子群組也需合併
        if dept.get("program_type") == "dept_with_groups":
            new_groups = []
            for g in dept.get("groups", []):
                new_groups.append(merge_dept(g, sched_lookup))
            merged["groups"] = new_groups
        new_depts.append(merged)
    college["departments"] = new_depts

    new_cbps = []
    for cbp in college.get("college_bachelor_programs", []):
        merged = merge_dept(cbp, sched_lookup)
        # specialization_tracks
        if cbp.get("specialization_tracks"):
            merged["specialization_tracks"] = [
                merge_dept(t, sched_lookup)
                for t in cbp["specialization_tracks"]
            ]
        new_cbps.append(merged)
    college["college_bachelor_programs"] = new_cbps

    # 學院共同必修（若有）
    if "college_required_courses" in college:
        college["college_required_courses"] = [
            strip_course(c) for c in college["college_required_courses"]
        ]

    return college


# ── 主程式 ───────────────────────────────────────────────────────────────────

def main():
    print("=== merge_schedule_to_curriculum ===")
    print(f"  讀取 curriculum：{CURRICULUM_PATH}")
    curriculum = json.loads(CURRICULUM_PATH.read_text(encoding="utf-8"))

    print(f"  掃描 schedule_draft：{SCHEDULE_DIR}")
    sched_lookup = load_schedule_lookup()
    print(f"  schedule_draft IDs：{len(sched_lookup)}")

    new_colleges = []
    for college in curriculum["colleges"]:
        new_colleges.append(process_college(college, sched_lookup))

    curriculum["colleges"] = new_colleges

    # 更新 metadata 的 generated 日期
    from datetime import date
    curriculum["metadata"]["generated"] = str(date.today())
    curriculum["metadata"]["source"] = "schedule_draft_verified"

    out = CURRICULUM_PATH
    out.write_text(json.dumps(curriculum, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  輸出：{out}")

    # 統計
    total_depts = 0
    merged_depts = 0
    for college in curriculum["colleges"]:
        for dept in college.get("departments", []):
            total_depts += 1
            if dept.get("id") in sched_lookup:
                merged_depts += 1
            for g in dept.get("groups", []):
                total_depts += 1
                if g.get("id") in sched_lookup:
                    merged_depts += 1
        for cbp in college.get("college_bachelor_programs", []):
            total_depts += 1
            if cbp.get("id") in sched_lookup:
                merged_depts += 1
            for t in cbp.get("specialization_tracks", []):
                total_depts += 1
                if t.get("id") in sched_lookup:
                    merged_depts += 1

    print(f"  系所節點共 {total_depts} 個，其中 {merged_depts} 個採用 schedule_draft 資料")
    print("✓ 完成")


if __name__ == "__main__":
    main()
