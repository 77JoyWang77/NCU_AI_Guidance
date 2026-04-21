"""
整理 data/processed/ 的應修科目表相關資料：

1. 拆分 curriculum_requirements_114.json
   → data/processed/curriculum_requirements/學院/系所.json
   （結構與 data/raw/應修科目表/ 一致）

2. 重建 schedule_draft/
   → data/processed/schedule_draft/學院/系所.json
   以 curriculum_requirements 為課程來源，
   從 requirements_semester_map.json 補入 when 欄位

3. 刪除舊檔案：
   - data/processed/requirements_schedule_draft.json
   - data/processed/schedule_draft/credit_programs_*.json（舊版）
"""

import json
import re
import shutil
from pathlib import Path

BASE_DIR   = Path(__file__).parent.parent.parent
PROC_DIR   = BASE_DIR / "data" / "processed"

SRC_JSON   = PROC_DIR / "curriculum_requirements_114.json"
MAP_PATH   = PROC_DIR / "requirements_semester_map.json"
CURREQ_DIR = PROC_DIR / "curriculum_requirements"
DRAFT_DIR  = PROC_DIR / "schedule_draft"

YEAR_NAMES = {1: "大一", 2: "大二", 3: "大三", 4: "大四"}
SEM_NAMES  = {1: "上",   2: "下"}


# ── when 編碼 ────────────────────────────────────────────────

def encode_when(spans: list) -> str:
    if not spans:
        return ""
    labels = []
    seen: set = set()
    for y, s in spans:
        lb = YEAR_NAMES.get(y, f"?{y}") + SEM_NAMES.get(s, f"?{s}")
        if lb not in seen:
            seen.add(lb)
            labels.append(lb)
    if len(labels) == 1:
        return labels[0]
    return f"{labels[0]}~{labels[-1]}"


def build_code_when_lookup(sem_map: dict) -> dict:
    """code → {"when": "大一上", "auto": bool}，跨系所衝突時 auto=False"""
    lookup: dict = {}
    conflicts: set = set()
    code_re = re.compile(r'^[A-Z]{2,4}\d{4}$')

    for dept_data in sem_map.values():
        for c in dept_data.get("courses", []):
            if c.get("key_type") != "code":
                continue
            code  = c["key"]
            spans = c.get("spans_semesters") or [(c["year_level"], c["semester"])]
            when  = encode_when(spans)
            auto  = not c.get("low_confidence", False)

            if code in lookup:
                if lookup[code]["when"] != when:
                    conflicts.add(code)
            else:
                lookup[code] = {"when": when, "auto": auto}

    for code in conflicts:
        if code in lookup:
            lookup[code]["auto"] = False

    return lookup


# ── 遞迴走訪所有課程物件，加入 when 欄位 ────────────────────

COURSE_LIST_KEYS = {
    "required_courses", "elective_groups", "groups", "tracks",
    "core_elective_groups", "required_electives", "college_required_courses",
    "common_required_courses", "foundation_courses", "application_courses",
    "specialization_tracks", "college_required_elective_groups",
    "earth_system_courses", "cross_domain_required",
}

def enrich_course(course: dict, lookup: dict) -> dict:
    out = dict(course)
    code = course.get("code", "")
    info = lookup.get(code)
    if info:
        out["when"]      = info["when"]
        out["when_auto"] = info["auto"]
    else:
        out["when"]      = ""
        out["when_auto"] = False
    out["verified"] = False
    out["note"]     = ""
    return out


def enrich_node(node, lookup: dict):
    """遞迴地替每個課程 dict（有 code 欄位）加入 when 欄位。"""
    if isinstance(node, list):
        return [enrich_node(item, lookup) for item in node]

    if isinstance(node, dict):
        # 是課程物件（有 code 且沒有 departments 這種巢狀結構鍵）
        if "code" in node and "departments" not in node and "courses" not in node:
            return enrich_course(node, lookup)
        # 否則遞迴處理所有 list 值
        out = {}
        for k, v in node.items():
            if isinstance(v, list):
                out[k] = enrich_node(v, lookup)
            elif isinstance(v, dict):
                out[k] = enrich_node(v, lookup)
            else:
                out[k] = v
        return out

    return node


# ── 主流程 ─────────────────────────────────────────────────────

def main():
    # ── 載入資料 ──
    print("載入資料...")
    raw = json.loads(SRC_JSON.read_text(encoding="utf-8"))
    sem_map = json.loads(MAP_PATH.read_text(encoding="utf-8")) if MAP_PATH.exists() else {}
    lookup = build_code_when_lookup(sem_map)
    print(f"  when lookup：{len(lookup)} 個課號")

    # ── 清理舊 schedule_draft（credit_programs 版） ──
    old_draft_file = PROC_DIR / "requirements_schedule_draft.json"
    if old_draft_file.exists():
        old_draft_file.unlink()
        print(f"  刪除舊檔：requirements_schedule_draft.json")

    # 清空 schedule_draft/ 裡的舊 credit_programs_*.json
    if DRAFT_DIR.exists():
        for f in DRAFT_DIR.glob("credit_programs_*.json"):
            f.unlink()
        # 若還有子資料夾就先清空整個 schedule_draft
        for item in DRAFT_DIR.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            elif item.suffix == ".json":
                item.unlink()
        print(f"  清空舊 schedule_draft/")

    # ── 建立目錄 ──
    CURREQ_DIR.mkdir(parents=True, exist_ok=True)
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)

    colleges = raw.get("colleges", [])
    print(f"\n拆分 {len(colleges)} 個學院...\n")

    total_depts = 0
    total_courses = 0
    total_auto = 0

    for college in colleges:
        col_name = college.get("name", "未知學院")
        col_dir_curreq = CURREQ_DIR / col_name
        col_dir_draft  = DRAFT_DIR  / col_name
        col_dir_curreq.mkdir(exist_ok=True)
        col_dir_draft.mkdir(exist_ok=True)

        # 各系所
        depts = college.get("departments", [])
        for dept in depts:
            dept_name = dept.get("name", "未知系所")
            dept_id   = dept.get("id", dept_name)

            # ── curriculum_requirements ──
            (col_dir_curreq / f"{dept_name}.json").write_text(
                json.dumps(dept, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # ── schedule_draft：enriched 版本 ──
            enriched = enrich_node(dept, lookup)
            (col_dir_draft / f"{dept_name}.json").write_text(
                json.dumps(enriched, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # 統計
            def count_courses(node, auto_count=None):
                if auto_count is None:
                    auto_count = [0, 0]  # [total, auto]
                if isinstance(node, dict):
                    if "code" in node and "verified" in node:
                        auto_count[0] += 1
                        if node.get("when_auto"):
                            auto_count[1] += 1
                    for v in node.values():
                        if isinstance(v, (dict, list)):
                            count_courses(v, auto_count)
                elif isinstance(node, list):
                    for item in node:
                        count_courses(item, auto_count)
                return auto_count

            tc, ta = count_courses(enriched)
            total_depts   += 1
            total_courses += tc
            total_auto    += ta
            print(f"  {col_name}/{dept_name}：{tc} 門課，{ta} 門自動偵測")

        # 學院學士班
        bp_list = college.get("college_bachelor_programs", [])
        for bp in bp_list:
            bp_name = bp.get("name", "學院學士班")

            (col_dir_curreq / f"{bp_name}.json").write_text(
                json.dumps(bp, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            enriched_bp = enrich_node(bp, lookup)
            (col_dir_draft / f"{bp_name}.json").write_text(
                json.dumps(enriched_bp, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tc, ta = count_courses(enriched_bp)
            total_depts   += 1
            total_courses += tc
            total_auto    += ta
            print(f"  {col_name}/{bp_name}（學士班）：{tc} 門課，{ta} 門自動偵測")

    auto_pct = f"{total_auto/total_courses*100:.0f}%" if total_courses else "0%"
    print(f"""
{'='*55}
完成！

curriculum_requirements/ 結構：
  {CURREQ_DIR}

schedule_draft/ 結構：
  {DRAFT_DIR}

統計：
  系所/學程：{total_depts} 個
  總課程數：{total_courses} 門
  自動偵測（when_auto=true）：{total_auto} 門（{auto_pct}）
  需人工填寫：{total_courses - total_auto} 門

下一步：執行 schedule_review_html.py 重新產生審核介面
""")


if __name__ == "__main__":
    main()
