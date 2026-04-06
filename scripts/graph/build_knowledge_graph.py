"""
Build NCU 114 Curriculum Knowledge Graph（三源整合版）

資料源：
  1. data/processed/curriculum_requirements_114.json  — 系所結構 + 必修/選修
  2. data/raw/courses/ + graduate_courses/ + scraped_missing/  — 課程詳細資訊
  3. data/processed/credit_programs/*.json  — 學分學程

課號對齊策略：
  - 課號完全命中 raw → 連結已有 Course 節點（補充詳細屬性）
  - 課號不在 raw → 建立 Course stub 節點（source=cp_only / curriculum_only）

節點類型：
  University, College, Department, DeptGroup,
  CollegeBachelorProgram, SpecializationTrack,
  CurriculumPlan, ElectiveGroup, Slot, GraduationRule,
  Course, Instructor, Domain, Competency, Certification,
  CreditProgram

相依套件：pip install networkx
"""

import json
import pickle
import re
from collections import Counter, defaultdict
from pathlib import Path

try:
    import networkx as nx
except ImportError:
    print("請先安裝 networkx：pip install networkx")
    raise

BASE = Path(__file__).parent.parent.parent

CURRICULUM_PATH  = BASE / "data" / "processed" / "curriculum_requirements_114.json"
CP_DIR           = BASE / "data" / "processed" / "credit_programs"
RAW_DIRS         = [
    (BASE / "data" / "raw" / "courses",           "ugrad"),
    (BASE / "data" / "raw" / "graduate_courses",  "grad"),
]
SCRAPED_PATH     = BASE / "data" / "raw" / "scraped_missing" / "courses.json"
GRAPH_PKL        = BASE / "data" / "processed" / "graph" / "knowledge_graph.gpickle"
GRAPH_JSON       = BASE / "data" / "processed" / "graph" / "knowledge_graph.json"


# ════════════════════════════════════════════════════════════
# Phase 0: 載入 raw 課程資料
# ════════════════════════════════════════════════════════════

def strip_section(code: str) -> str:
    return re.sub(r"-[A-Z0-9*]+$", "", code.strip())


def load_raw_courses() -> dict:
    """
    回傳 code → {name, credits, dept, college, level, semester,
                  instructors, domain, competencies, source}
    """
    raw: dict = {}

    def register(c: dict, level: str, source: str):
        code = strip_section(c.get("課號-班別", ""))
        if not code:
            return
        name    = c.get("課程名稱(中文)", "").strip()
        credits = c.get("學分", "")
        try:
            credits = int(credits)
        except (ValueError, TypeError):
            credits = 0

        # 課程綱要詳細資訊
        outline    = c.get("課程綱要", {}) or {}
        domain     = outline.get("課程領域", "") or c.get("課程領域", "")
        competencies = [
            a.get("能力名稱", "") for a in (outline.get("核心能力") or [])
            if a.get("能力名稱")
        ]
        instructors = [
            t.strip() for t in re.split(r"[\n,、；;]", c.get("授課教師", "") or "")
            if t.strip()
        ]

        if code in raw:
            # 已存在 → 僅更新 semester 標記
            if raw[code]["semester"] != source:
                raw[code]["semester"] = "both"
            return

        raw[code] = {
            "name":         name,
            "credits":      credits,
            "dept":         c.get("系所", ""),
            "college":      c.get("學院", ""),
            "level":        level,
            "semester":     source,           # e.g. "114_1", "114_2", "both", "scraped"
            "instructors":  instructors,
            "domain":       domain.strip(),
            "competencies": competencies,
            "source":       "raw",
        }

    for raw_dir, level in RAW_DIRS:
        for sem in ["114_1", "114_2"]:
            d = raw_dir / sem
            if not d.exists():
                continue
            for f in d.glob("*.json"):
                for c in json.loads(f.read_text(encoding="utf-8")):
                    register(c, level, sem)

    if SCRAPED_PATH.exists():
        for c in json.loads(SCRAPED_PATH.read_text(encoding="utf-8")):
            if c.get("_not_found") or c.get("_error"):
                continue
            num_m = re.search(r"(\d+)", strip_section(c.get("課號-班別", "")))
            level = "grad" if num_m and int(num_m.group(1)) >= 5000 else "ugrad"
            register(c, level, "scraped")

    return raw


# ════════════════════════════════════════════════════════════
# Course node helpers
# ════════════════════════════════════════════════════════════

def ensure_course(G: nx.DiGraph, raw: dict, code: str,
                  fallback_name: str = "", fallback_credits: int = 0,
                  stub_source: str = "cp_only") -> str:
    """確保 Course 節點存在，有 raw 資料則用詳細版，否則建 stub。"""
    if G.has_node(code):
        return code
    if code in raw:
        r = raw[code]
        G.add_node(code, node_type="Course",
                   name=r["name"], credits=r["credits"],
                   dept=r["dept"], college=r["college"],
                   level=r["level"], semester=r["semester"],
                   domain=r["domain"], source="raw")
    else:
        G.add_node(code, node_type="Course",
                   name=fallback_name, credits=fallback_credits,
                   source=stub_source, level="unknown")
    return code


def add_instructor_domain_competency(G: nx.DiGraph, raw: dict):
    """對所有已存在的 raw Course 節點，建立 Instructor/Domain/Competency 節點與邊。"""
    for code, r in raw.items():
        if not G.has_node(code):
            continue
        # Instructors
        for name in r.get("instructors", []):
            iid = f"instructor::{name}"
            if not G.has_node(iid):
                G.add_node(iid, node_type="Instructor", name=name)
            if not G.has_edge(code, iid):
                G.add_edge(code, iid, relation="TAUGHT_BY")
        # Domain
        domain = r.get("domain", "")
        if domain:
            did = f"domain::{domain}"
            if not G.has_node(did):
                G.add_node(did, node_type="Domain", name=domain)
            if not G.has_edge(code, did):
                G.add_edge(code, did, relation="IN_DOMAIN")
        # Competencies
        for comp in r.get("competencies", []):
            cid = f"competency::{comp}"
            if not G.has_node(cid):
                G.add_node(cid, node_type="Competency", name=comp)
            if not G.has_edge(code, cid):
                G.add_edge(code, cid, relation="DEVELOPS")


# ════════════════════════════════════════════════════════════
# Phase 1: curriculum_requirements（系所結構）
# ════════════════════════════════════════════════════════════

def add_courses(G: nx.DiGraph, raw: dict, courses: list,
                owner_id: str, rel: str = "REQUIRES",
                stub_source: str = "curriculum_only"):
    for c in courses:
        if not isinstance(c, dict) or not c.get("code"):
            continue
        code = c["code"]
        ensure_course(G, raw, code,
                      fallback_name=c.get("name", ""),
                      fallback_credits=c.get("credits", 0),
                      stub_source=stub_source)
        if not G.has_edge(owner_id, code):
            G.add_edge(owner_id, code, relation=rel,
                       credits=c.get("credits", 0))


def add_slot(G: nx.DiGraph, raw: dict, slot: dict,
             parent_id: str, slot_idx: int,
             stub_source: str = "cp_only"):
    """建立 Slot 節點及其 OFFERS_ELECTIVE 邊。"""
    slot_id = f"{parent_id}__slot{slot_idx}__{slot.get('slot_id', slot_idx)}"
    G.add_node(slot_id, node_type="Slot",
               name=slot.get("slot_name", f"Slot {slot_idx}"),
               select=slot.get("select", 1),
               slot_rule=slot.get("slot_rule", ""))
    G.add_edge(parent_id, slot_id, relation="HAS_SLOT")
    for c in slot.get("courses", []):
        if not c.get("code"):
            continue
        ensure_course(G, raw, c["code"],
                      fallback_name=c.get("name", ""),
                      fallback_credits=c.get("credits", 0),
                      stub_source=stub_source)
        if not G.has_edge(slot_id, c["code"]):
            G.add_edge(slot_id, c["code"], relation="OFFERS_ELECTIVE")
    return slot_id


def add_elective_group(G: nx.DiGraph, raw: dict, grp: dict,
                       owner_id: str, idx: int,
                       stub_source: str = "curriculum_only"):
    eg_id = f"{owner_id}__eg{idx}"
    G.add_node(eg_id, node_type="ElectiveGroup",
               name=grp.get("name", f"選修群{idx}"),
               select=grp.get("select"),
               select_credits=grp.get("select_credits"),
               group_rule=grp.get("group_rule", ""))
    G.add_edge(owner_id, eg_id, relation="HAS_ELECTIVE_GROUP")

    # 直接課程（非 slot）
    for key in ("courses", "option_a", "option_b", "option_c"):
        add_courses(G, raw, grp.get(key, []), eg_id, "OFFERS_ELECTIVE", stub_source)

    # Slots（同等課程群組）
    for si, slot in enumerate(grp.get("slots", [])):
        add_slot(G, raw, slot, eg_id, si, stub_source)

    return eg_id


def add_rules(G: nx.DiGraph, rules: list, owner_id: str):
    for i, r in enumerate(rules):
        rid = f"{owner_id}__rule{i}"
        G.add_node(rid, node_type="GraduationRule", **{
            k: v for k, v in r.items() if isinstance(v, (str, int, float, bool))
        })
        G.add_edge(owner_id, rid, relation="GOVERNED_BY")


def add_certs(G: nx.DiGraph, certs: list, owner_id: str):
    for cert in certs:
        cid = f"cert::{cert}"
        if not G.has_node(cid):
            G.add_node(cid, node_type="Certification", name=cert)
        G.add_edge(owner_id, cid, relation="REQUIRES_CERTIFICATION")


def make_plan(G: nx.DiGraph, plan_id: str, name: str,
              required_credits: int = 0) -> str:
    G.add_node(plan_id, node_type="CurriculumPlan",
               name=name, required_credits=required_credits)
    return plan_id


def process_dept_group(G, raw, grp, parent_id, parent_rel="HAS_GROUP"):
    gid = grp["id"]
    G.add_node(gid, node_type="DeptGroup",
               name=grp["name"],
               group_label=grp.get("group_label", ""),
               min_credits=grp.get("min_credits", 0))
    G.add_edge(parent_id, gid, relation=parent_rel)
    add_rules(G, grp.get("graduation_rules", []), gid)
    add_certs(G, grp.get("certifications", []), gid)

    plan_id = make_plan(G, f"{gid}::plan", f"{grp['name']}課程計畫",
                        grp.get("group_required_credits", grp.get("required_credits", 0)))
    G.add_edge(gid, plan_id, relation="HAS_CURRICULUM")

    for key in ("required_courses", "cross_group_required",
                "college_required_courses", "common_required_courses"):
        add_courses(G, raw, grp.get(key, []), plan_id, "REQUIRES")
    add_courses(G, raw, grp.get("first_domain_electives", []), plan_id, "OFFERS_ELECTIVE")

    for i, eg in enumerate(grp.get("elective_groups", [])):
        add_elective_group(G, raw, eg, plan_id, i)
    for sub in grp.get("groups", []):
        process_dept_group(G, raw, sub, gid, "HAS_GROUP")


def process_dept(G, raw, dept, college_id):
    did = dept["id"]
    G.add_node(did, node_type="Department",
               name=dept["name"],
               program_type=dept.get("program_type", "traditional_dept"),
               min_credits=dept.get("min_credits", 0))
    G.add_edge(college_id, did, relation="HAS_DEPARTMENT")
    add_rules(G, dept.get("graduation_rules", []), did)
    add_certs(G, dept.get("certifications", []), did)

    plan_id = make_plan(G, f"{did}::plan", f"{dept['name']}課程計畫",
                        dept.get("required_credits", 0))
    G.add_edge(did, plan_id, relation="HAS_CURRICULUM")

    for key in ("required_courses", "required_electives", "college_required_courses"):
        add_courses(G, raw, dept.get(key, []), plan_id, "REQUIRES")
    for i, eg in enumerate(dept.get("elective_groups", [])):
        add_elective_group(G, raw, eg, plan_id, i)
    for i, eg in enumerate(dept.get("core_elective_groups", [])):
        add_elective_group(G, raw, eg, plan_id, 100 + i)

    if dept.get("program_type") == "dept_with_groups":
        for grp in dept.get("groups", []):
            process_dept_group(G, raw, grp, did, "HAS_GROUP")
    for track in dept.get("tracks", []):
        process_dept_group(G, raw, {
            "id": track["id"], "name": track["name"],
            "group_label": track.get("group_label", track["name"]),
            "required_courses": track.get("required_courses", []),
            "elective_groups": track.get("elective_groups", []),
            "graduation_rules": track.get("graduation_rules", []),
        }, did, "HAS_TRACK")


def process_track(G, raw, track, parent_id, parent_rel="HAS_TRACK"):
    tid = track["id"]
    G.add_node(tid, node_type="SpecializationTrack",
               name=track["name"],
               min_credits=track.get("min_credits", 0))
    G.add_edge(parent_id, tid, relation=parent_rel)

    plan_id = make_plan(G, f"{tid}::plan", f"{track['name']}課程計畫")
    G.add_edge(tid, plan_id, relation="HAS_CURRICULUM")
    add_courses(G, raw, track.get("required_courses", []), plan_id, "REQUIRES")
    add_courses(G, raw, track.get("elective_courses", []), plan_id, "OFFERS_ELECTIVE")
    for i, eg in enumerate(track.get("elective_groups", [])):
        add_elective_group(G, raw, eg, plan_id, i)

    for sub in track.get("groups", []):
        sub_id = sub["id"]
        G.add_node(sub_id, node_type="SpecializationTrack",
                   name=sub["name"], parent_track=tid)
        G.add_edge(tid, sub_id, relation="HAS_TRACK")
        sub_plan = make_plan(G, f"{sub_id}::plan", f"{sub['name']}課程計畫")
        G.add_edge(sub_id, sub_plan, relation="HAS_CURRICULUM")
        add_courses(G, raw, sub.get("required_courses", []), sub_plan, "REQUIRES")
        add_courses(G, raw, sub.get("elective_courses", []), sub_plan, "OFFERS_ELECTIVE")
        for i, eg in enumerate(sub.get("elective_groups", [])):
            add_elective_group(G, raw, eg, sub_plan, i)


def process_cbp(G, raw, cbp, college_id):
    cid = cbp["id"]
    G.add_node(cid, node_type="CollegeBachelorProgram",
               name=cbp["name"],
               min_credits=cbp.get("min_credits", 0))
    G.add_edge(college_id, cid, relation="HAS_CBP")
    add_rules(G, cbp.get("graduation_rules", []), cid)

    main_plan_id = f"{cid}::base_plan"
    make_plan(G, main_plan_id, f"{cbp['name']}基礎課程計畫")
    G.add_edge(cid, main_plan_id, relation="HAS_CURRICULUM")

    for key in ("required_courses", "foundation_courses", "application_courses",
                "earth_system_courses", "cross_domain_required"):
        add_courses(G, raw, cbp.get(key, []), main_plan_id, "REQUIRES")
    for i, eg in enumerate(cbp.get("elective_groups", [])):
        add_elective_group(G, raw, eg, main_plan_id, i)
    for i, eg in enumerate(cbp.get("college_required_elective_groups", [])):
        add_elective_group(G, raw, eg, main_plan_id, 100 + i)

    for track in cbp.get("specialization_tracks", []):
        process_track(G, raw, track, cid, "HAS_TRACK")
    for track in cbp.get("tracks", []):
        process_dept_group(G, raw, {
            "id": track["id"], "name": track["name"],
            "group_label": track.get("name", ""),
            "required_courses": track.get("required_courses", []),
            "elective_groups": track.get("elective_groups", []),
            "graduation_rules": track.get("graduation_rules", []),
        }, cid, "HAS_TRACK")


def build_curriculum_layer(G: nx.DiGraph, raw: dict):
    print("  [1/3] curriculum_requirements...")
    data = json.loads(CURRICULUM_PATH.read_text(encoding="utf-8"))

    uni_id = "NCU"
    G.add_node(uni_id, node_type="University",
               name=data["metadata"]["university"],
               academic_year=data["metadata"]["academic_year"])

    for college in data["colleges"]:
        col_id = college["id"]
        G.add_node(col_id, node_type="College", name=college["name"])
        G.add_edge(uni_id, col_id, relation="HAS_COLLEGE")

        if college.get("college_required_courses"):
            common_id = f"{col_id}::common"
            make_plan(G, common_id, f"{college['name']}院訂必修")
            G.add_edge(col_id, common_id, relation="HAS_CURRICULUM")
            add_courses(G, raw, college["college_required_courses"], common_id, "REQUIRES")
            for i, eg in enumerate(college.get("college_required_elective_groups", [])):
                add_elective_group(G, raw, eg, common_id, i)

        if college.get("college_elective_courses"):
            elective_id = f"{col_id}::elective"
            G.add_node(elective_id, node_type="CurriculumPlan",
                       name=f"{college['name']}院訂必選")
            G.add_edge(col_id, elective_id, relation="HAS_CURRICULUM")
            add_courses(G, raw, college["college_elective_courses"],
                        elective_id, "OFFERS_ELECTIVE")

        for dept in college.get("departments", []):
            process_dept(G, raw, dept, col_id)
        for cbp in college.get("college_bachelor_programs", []):
            process_cbp(G, raw, cbp, col_id)


# ════════════════════════════════════════════════════════════
# Phase 3: credit_programs
# ════════════════════════════════════════════════════════════

def build_credit_programs_layer(G: nx.DiGraph, raw: dict):
    print("  [3/3] credit_programs...")
    for f in sorted(CP_DIR.glob("*.json")):
        programs = json.loads(f.read_text(encoding="utf-8"))
        for prog in programs:
            pid = f"cp::{prog['id']}"
            G.add_node(pid, node_type="CreditProgram",
                       name=prog.get("name", ""),
                       college=prog.get("college", ""),
                       min_credits=prog.get("min_credits", 0),
                       cross_school=prog.get("cross_school", False))

            # 連接到學院節點
            college_key = prog.get("college_id") or prog.get("college", "")
            if college_key and G.has_node(college_key):
                G.add_edge(college_key, pid, relation="HAS_CREDIT_PROGRAM")

            # 一般必修課程
            for c in prog.get("required_courses", []):
                if not c.get("code"):
                    continue
                ensure_course(G, raw, c["code"],
                              fallback_name=c.get("name", ""),
                              fallback_credits=c.get("credits", 0),
                              stub_source="cp_only")
                if not G.has_edge(pid, c["code"]):
                    G.add_edge(pid, c["code"], relation="PROGRAM_REQUIRES",
                               credits=c.get("credits", 0))

            # 必修 slots（由 same_as 轉換而來）
            for si, slot in enumerate(prog.get("required_slots", [])):
                slot_id = add_slot(G, raw, slot, pid, si, stub_source="cp_only")
                # 用 REQUIRES_SLOT 語意區分「必須從此 slot 選一門」
                G.edges[pid, slot_id]["relation"] = "REQUIRES_SLOT"

            # 選修群（含 slots）
            for i, grp in enumerate(prog.get("elective_groups", [])):
                eg_id = f"{pid}__eg{i}"
                G.add_node(eg_id, node_type="ElectiveGroup",
                           name=grp.get("name", f"選修群{i}"),
                           select=grp.get("select"),
                           select_credits=grp.get("select_credits"),
                           group_rule=grp.get("group_rule", ""))
                G.add_edge(pid, eg_id, relation="PROGRAM_OFFERS")

                # 直接課程
                for c in grp.get("courses", []):
                    if not c.get("code"):
                        continue
                    ensure_course(G, raw, c["code"],
                                  fallback_name=c.get("name", ""),
                                  fallback_credits=c.get("credits", 0),
                                  stub_source="cp_only")
                    if not G.has_edge(eg_id, c["code"]):
                        G.add_edge(eg_id, c["code"], relation="OFFERS_ELECTIVE")

                # Slots（含原 same_as 轉換而來）
                for si, slot in enumerate(grp.get("slots", [])):
                    add_slot(G, raw, slot, eg_id, si, stub_source="cp_only")


# ════════════════════════════════════════════════════════════
# Phase 4: 畢業必修學程邊（REQUIRES_PROGRAM / PROGRAM_CHOICE）
# ════════════════════════════════════════════════════════════

# 學程名稱關鍵字 → CreditProgram node id 對照表
_PROGRAM_NAME_TO_ID = {
    "創意與創業":       "cp::creativity_entrepreneurship",
    "地球科學資訊":     "cp::geoscience_informatics",
    "氣候與環境變遷":   "cp::climate_environmental_change",
    "企業資源規劃":     "cp::erp",
    "商業智慧與分析":   "cp::business_intelligence_analytics",
    "跨領域社會參與":   "cp::interdisciplinary_social_engagement",
    "社會企業與社會創新": "cp::social_enterprise_innovation",
    "社會企業":        "cp::social_enterprise",
}

def _match_program_id(name_text: str) -> str | None:
    for kw, pid in _PROGRAM_NAME_TO_ID.items():
        if kw in name_text:
            return pid
    return None


def build_program_requirement_edges(G: nx.DiGraph):
    """
    從 graduation_rules 解析學程必修/選擇邊：
      REQUIRES_PROGRAM : 系所/學士班 → CreditProgram（強制完成）
      PROGRAM_CHOICE   : 系所/學士班 → CreditProgram（N 選一）
      PROGRAM_ELECTIVE : 系所/學士班 → CreditProgram（選修性質）
    """
    print("  [4/4] 解析畢業必修學程邊...")

    data = json.loads(CURRICULUM_PATH.read_text(encoding="utf-8"))
    added = 0

    def scan(obj, owner_id: str):
        nonlocal added
        if not isinstance(obj, dict):
            return
        node_id = obj.get("id", owner_id)

        for rule in obj.get("graduation_rules", []):
            rtype = rule.get("type", "")
            desc  = rule.get("description", "")

            # ── 1. 強制完成單一學程 ──────────────────────────────
            if rtype == "special_requirement":
                pid = _match_program_id(desc)
                if pid and G.has_node(node_id) and G.has_node(pid):
                    if not G.has_edge(node_id, pid):
                        G.add_edge(node_id, pid,
                                   relation="REQUIRES_PROGRAM",
                                   description=desc)
                        added += 1

            # ── 2. N 選一學程（structured options） ─────────────
            elif rtype == "program_choice":
                select = rule.get("select", 1)
                for opt in rule.get("options", []):
                    pid = _match_program_id(opt.get("name", ""))
                    if pid and G.has_node(node_id) and G.has_node(pid):
                        if not G.has_edge(node_id, pid):
                            G.add_edge(node_id, pid,
                                       relation="PROGRAM_CHOICE",
                                       select=select,
                                       min_credits=opt.get("credits",
                                                           opt.get("credits_min", 0)))
                            added += 1

            # ── 3. 非結構化的一選一描述 ─────────────────────────
            elif rtype == "special_requirement_one_of":
                pids = [_match_program_id(part)
                        for part in desc.split("(")
                        if _match_program_id(part)]
                for pid in pids:
                    if G.has_node(node_id) and G.has_node(pid):
                        if not G.has_edge(node_id, pid):
                            G.add_edge(node_id, pid,
                                       relation="PROGRAM_CHOICE",
                                       select=1,
                                       description=desc)
                            added += 1

            # ── 4. 選修性質（鼓勵但非強制） ─────────────────────
            elif rtype == "program_elective":
                for kw, pid in _PROGRAM_NAME_TO_ID.items():
                    if kw in desc and G.has_node(node_id) and G.has_node(pid):
                        if not G.has_edge(node_id, pid):
                            G.add_edge(node_id, pid,
                                       relation="PROGRAM_ELECTIVE",
                                       description=desc)
                            added += 1

        # 遞迴處理子結構
        for key in ("departments", "college_bachelor_programs",
                    "groups", "tracks", "specialization_tracks"):
            for child in obj.get(key, []):
                scan(child, child.get("id", owner_id))

    for college in data["colleges"]:
        scan(college, college["id"])

    print(f"      → 新增 {added} 條學程邊")


# ════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════

def print_stats(G: nx.DiGraph):
    node_types = Counter(d.get("node_type", "?") for _, d in G.nodes(data=True))
    edge_types = Counter(d.get("relation", "?") for _, _, d in G.edges(data=True))
    stub_count = sum(1 for _, d in G.nodes(data=True)
                     if d.get("node_type") == "Course" and d.get("source") != "raw")
    raw_count  = sum(1 for _, d in G.nodes(data=True)
                     if d.get("node_type") == "Course" and d.get("source") == "raw")
    print(f"\n=== Knowledge Graph ===")
    print(f"Nodes: {G.number_of_nodes()}  Edges: {G.number_of_edges()}")
    print(f"\nCourse nodes:  {raw_count} 有完整資料  |  {stub_count} stub（課號不在 raw）")
    print("\nNode types:")
    for nt, cnt in sorted(node_types.items()):
        print(f"  {nt:35s} {cnt}")
    print("\nEdge relations:")
    for et, cnt in sorted(edge_types.items()):
        print(f"  {et:35s} {cnt}")


def main():
    # ── Phase 0: 載入 raw 課程 ──
    print("載入 raw 課程資料...")
    raw = load_raw_courses()
    print(f"  raw 課號：{len(raw)} 筆")

    G = nx.DiGraph()

    # ── Phase 1: curriculum_requirements ──
    build_curriculum_layer(G, raw)

    # ── Phase 2: 補充 Instructor / Domain / Competency ──
    print("  [2/3] 補充 Instructor / Domain / Competency 節點...")
    add_instructor_domain_competency(G, raw)

    # ── Phase 3: credit_programs ──
    build_credit_programs_layer(G, raw)

    # ── Phase 4: 畢業必修學程邊 ──
    build_program_requirement_edges(G)

    print_stats(G)

    # 輸出
    GRAPH_PKL.parent.mkdir(parents=True, exist_ok=True)
    with open(GRAPH_PKL, "wb") as f:
        pickle.dump(G, f)
    print(f"\nSaved pickle: {GRAPH_PKL}")

    graph_json = {
        "nodes": [{"id": n, **d} for n, d in G.nodes(data=True)],
        "edges": [{"source": u, "target": v, **d} for u, v, d in G.edges(data=True)],
    }
    with open(GRAPH_JSON, "w", encoding="utf-8") as f:
        json.dump(graph_json, f, ensure_ascii=False, indent=2)
    print(f"Saved JSON:   {GRAPH_JSON}")


if __name__ == "__main__":
    main()
