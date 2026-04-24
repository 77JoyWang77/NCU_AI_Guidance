"""
build_vector_index.py

建立 ChromaDB 向量索引，涵蓋五個 collection：
  ncu_courses_ug    — 大學部課程（含 NLP 萃取結果、教師專長、應修學期）
  ncu_courses_grad  — 研究所課程
  ncu_credit_programs — 學分學程
  ncu_departments   — 系所介紹（Collego）
  ncu_teachers      — 教師官方專長（114_ulistteacher.csv）

執行方式：
  cd <project_root>
  python scripts/rag/build_vector_index.py

環境變數（.env）：
  AZURE_OPENAI_API_KEY=...
  AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
  AZURE_OPENAI_API_VERSION=2024-02-01
  AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
"""

import argparse
import json
import csv
import os
import re
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import AzureOpenAI
import chromadb
from tqdm import tqdm

# ── 路徑設定 ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_PROC = ROOT / "data" / "processed"
CHROMA_DIR = DATA_PROC / "chroma_db"

COURSE_ELIGIBILITY = DATA_PROC / "course_eligibility.json"
COURSES_114_1 = DATA_RAW / "courses" / "114_1"
COURSES_114_2 = DATA_RAW / "courses" / "114_2"
GRAD_114_1 = DATA_RAW / "graduate_courses" / "114_1"
GRAD_114_2 = DATA_RAW / "graduate_courses" / "114_2"
SCRAPED_MISSING = DATA_RAW / "scraped_missing" / "courses.json"
COLLEGO = DATA_RAW / "collego_ncu.json"
TEACHER_CSV = DATA_RAW / "114_ulistteacher.csv"

NLP_DIR = DATA_PROC / "nlp"
SCHEDULE_DIR = DATA_PROC / "schedule_draft"
CREDIT_PROGRAMS_DIR = DATA_PROC / "credit_programs"
PROGRAM_DESC = DATA_PROC / "program_descriptions.json"

# ── 嵌入配置 ────────────────────────────────────────────────────────────────
EMBED_BATCH = 50   # 每批送給 Azure OpenAI 的文件數

# ── 工具函式 ────────────────────────────────────────────────────────────────

def clean_code(raw: str) -> str:
    """CE1001-* → CE1001"""
    return raw.split("-")[0].strip() if raw else ""


_YEAR_MAP = {"一": 1, "二": 2, "三": 3, "四": 4}
_SEM_MAP  = {"上": 1, "下": 2}

# 全部學期的順序表，用於展開範圍
_ALL_SEMS: list[tuple[int, int]] = [
    (1, 1), (1, 2), (2, 1), (2, 2),
    (3, 1), (3, 2), (4, 1), (4, 2),
]


def _parse_single(token: str) -> tuple[Optional[int], Optional[int]]:
    """'大二下' → (2, 2)；解析失敗回傳 (None, None)"""
    m = re.search(r"大([一二三四])([上下])?", token.strip())
    if not m:
        return None, None
    return _YEAR_MAP.get(m.group(1)), _SEM_MAP.get(m.group(2)) if m.group(2) else None


def parse_when(when_str: str) -> dict:
    """
    解析 when 字串，回傳完整 metadata dict。

    支援：
      ""                → 全空
      "大一上"           → 單學期
      "大一上~大二下"    → 跨學期範圍

    回傳 keys：
      when_raw, when_year_start, when_year_end,
      when_sem_start, when_sem_end, when_semesters
    """
    result: dict = {
        "when_raw": when_str or "",
        "when_year_start": 0,
        "when_year_end": 0,
        "when_sem_start": 0,
        "when_sem_end": 0,
        "when_semesters": "",
    }
    if not when_str:
        return result

    parts = [p.strip() for p in when_str.split("~")]
    y_s, s_s = _parse_single(parts[0])
    if y_s is None:
        return result

    y_e, s_e = (_parse_single(parts[1]) if len(parts) > 1 else (y_s, s_s))
    if y_e is None:
        y_e, s_e = y_s, s_s

    result["when_year_start"] = y_s
    result["when_sem_start"]  = s_s or 1
    result["when_year_end"]   = y_e
    result["when_sem_end"]    = s_e or 2

    # 展開範圍成 "y_s" 代碼列表，供 $contains 過濾
    try:
        idx_s = _ALL_SEMS.index((y_s, result["when_sem_start"]))
        idx_e = _ALL_SEMS.index((y_e, result["when_sem_end"]))
        result["when_semesters"] = ",".join(f"{y}_{s}" for y, s in _ALL_SEMS[idx_s:idx_e + 1])
    except ValueError:
        pass

    return result


def load_json(path: Path) -> dict | list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def join_list(items: list[str], sep=",") -> str:
    return sep.join(str(i) for i in items if i)


# ── 載入 NLP 萃取資料 ────────────────────────────────────────────────────────

def load_nlp_data() -> dict:
    """回傳 {course_code: {simplified, domain_tags, tech_nodes, topic_tags, prof_links}}"""
    tech = load_json(NLP_DIR / "nlp_tech_nodes.json")
    simplified = load_json(NLP_DIR / "nlp_simplified_concepts.json")
    domain = load_json(NLP_DIR / "nlp_domain_tags.json")
    topic = load_json(NLP_DIR / "nlp_topic_tags.json")
    prof = load_json(NLP_DIR / "nlp_professor_links.json")

    combined: dict = {}
    all_codes = set(tech) | set(simplified) | set(domain) | set(topic) | set(prof)
    for code in all_codes:
        # domain_tags 結構是 [{"field": "...", "relevance": "..."}]
        raw_domain = domain.get(code, {}).get("domain_tags", [])
        domain_fields = [
            tag["field"] for tag in raw_domain
            if isinstance(tag, dict) and tag.get("field")
        ] if raw_domain else []
        domain_rich = "||".join(
            f"{t['field']}::{t.get('relevance', 'medium')}"
            for t in raw_domain
            if isinstance(t, dict) and t.get("field")
        ) if raw_domain else ""

        combined[code] = {
            "tech": tech.get(code, {}),
            "simplified": simplified.get(code, {}).get("simplified_concepts", []),
            "domain_tags": domain_fields,
            "domain_tags_rich": domain_rich,
            "topic_tags": topic.get(code, {}).get("topic_tags", []),
            "core_questions": topic.get(code, {}).get("core_questions", []),
            "prof_links": prof.get(code, []),
        }
    print(f"[NLP] 載入 {len(combined)} 筆課程 NLP 資料")
    return combined


def load_teacher_csv() -> dict[str, str]:
    """回傳 {教師名稱: '專長1,專長2,...'}"""
    result: dict[str, str] = {}
    with open(TEACHER_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row["教師名稱"].strip()
            spec = row["教師專長"].strip()
            if name:
                result[name] = spec
    print(f"[Teacher CSV] 載入 {len(result)} 位教師")
    return result


def load_eligibility_lookup() -> dict[str, dict]:
    """
    回傳 {course_code: {eligibility fields, course_relations fields}}
    支援 v3 格式（access_rules list）與舊格式（v2：eligibility 巢狀 / 頂層扁平）。
    """
    lookup: dict[str, dict] = {}
    if not COURSE_ELIGIBILITY.exists():
        return lookup
    data = load_json(COURSE_ELIGIBILITY)
    if not isinstance(data, list):
        return lookup
    for entry in data:
        code = entry.get("course_code", "").strip()
        if not code:
            continue

        access_rules = entry.get("access_rules")
        if access_rules is not None:
            # v3 格式：從 access_rules 聚合供 ChromaDB metadata 使用的欄位
            rels = entry.get("course_relations") or {}
            dept_union    = sorted({d for r in access_rules for d in r.get("dept_include", [])})
            college_union = sorted({c for r in access_rules for c in r.get("college_include", [])})
            open_to_minor        = any(r.get("open_to_minor")        for r in access_rules)
            open_to_double_major = any(r.get("open_to_double_major") for r in access_rules)
            open_to_credit_prog  = any(r.get("open_to_credit_prog")  for r in access_rules)
            open_to_cross_school = any(r.get("open_to_cross_school") for r in access_rules)
            # 大學部可修年級：取所有非研究所 rule 的年級聯集
            _GRAD = {"master", "phd", "master_inservice", "master_industry"}
            undergrad_years: set[int] = set()
            for r in access_rules:
                if not r.get("program_types") or any(pt not in _GRAD for pt in r["program_types"]):
                    undergrad_years.update(r.get("years", []))
            lookup[code] = {
                "access_rules":        access_rules,
                "eligible_years":      sorted(undergrad_years),
                "dept_include":        dept_union,
                "college_include":     college_union,
                "open_to_minor":       open_to_minor,
                "open_to_double_major":open_to_double_major,
                "open_to_credit_prog": open_to_credit_prog,
                "open_to_cross_school":open_to_cross_school,
                "is_unrestricted":     entry.get("is_unrestricted", False),
                "is_grad_only":        entry.get("is_grad_only", False),
                "is_undergrad_open":   entry.get("is_undergrad_open", True),
                "has_special_condition":entry.get("has_special_condition", False),
                "prereq_codes":        rels.get("prereq_codes", []),
                "coreq_codes":         rels.get("coreq_codes", []),
                "conflict_codes":      rels.get("conflict_codes", []),
            }
        else:
            # 舊格式 fallback（v2：eligibility 巢狀 / 頂層扁平）
            elig = entry.get("eligibility") or entry
            rels = entry.get("course_relations") or entry
            lookup[code] = {
                "eligible_years":       elig.get("eligible_years", []),
                "dept_include":         elig.get("dept_include", []),
                "college_include":      elig.get("college_include", []),
                "open_to_minor":        elig.get("open_to_minor", False),
                "open_to_double_major": elig.get("open_to_double_major", False),
                "open_to_credit_prog":  elig.get("open_to_credit_prog", False),
                "open_to_cross_school": elig.get("open_to_cross_school", False),
                "is_unrestricted":      elig.get("is_unrestricted", False),
                "is_grad_only":         False,
                "is_undergrad_open":    True,
                "has_special_condition":elig.get("has_special_condition", False),
                "prereq_codes":         rels.get("prereq_codes", []),
                "coreq_codes":          rels.get("coreq_codes", []),
                "conflict_codes":       rels.get("conflict_codes", []),
            }

    print(f"[Eligibility] 載入 {len(lookup)} 筆修課條件")
    return lookup


def load_schedule_lookup() -> dict[str, dict]:
    """
    回傳 {course_code: {when_raw, when_year_start, ..., when_semesters, verified}}
    從所有 schedule_draft 的 required_courses 建立
    """
    lookup: dict = {}
    if not SCHEDULE_DIR.exists():
        return lookup
    for college_dir in SCHEDULE_DIR.iterdir():
        if not college_dir.is_dir():
            continue
        for dept_file in college_dir.glob("*.json"):
            try:
                data = load_json(dept_file)
                for rc in data.get("required_courses", []):
                    code = rc.get("code", "").strip()
                    when = rc.get("when", "")
                    verified = rc.get("verified", False)
                    if code:
                        parsed = parse_when(when)
                        parsed["verified"] = verified
                        lookup[code] = parsed
            except Exception:
                pass
    print(f"[Schedule] 載入 {len(lookup)} 筆必修學期資訊")
    return lookup


# ── 嵌入 ────────────────────────────────────────────────────────────────────

class Embedder:
    def __init__(self, client: AzureOpenAI, deployment: str):
        self.client = client
        self.deployment = deployment

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批次取得向量，自動重試"""
        results = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i : i + EMBED_BATCH]
            for attempt in range(3):
                try:
                    resp = self.client.embeddings.create(model=self.deployment, input=batch)
                    results.extend([item.embedding for item in resp.data])
                    break
                except Exception as e:
                    if attempt == 2:
                        raise
                    print(f"  Embedding 重試 {attempt+1}/3：{e}")
                    time.sleep(2 ** attempt)
        return results


# ── 組裝課程文件 ─────────────────────────────────────────────────────────────

def build_course_doc(
    course: dict,
    nlp: dict,
    teacher_lookup: dict[str, str],
    schedule_lookup: dict,
    eligibility_lookup: dict,
    is_grad: bool = False,
) -> tuple[str, str, dict]:
    """
    回傳 (doc_id, document_text, metadata)
    """
    syllabus = course.get("課程綱要") or {}
    if isinstance(syllabus, str):
        syllabus = {}

    code_raw = course.get("課號-班別", "")
    code = clean_code(code_raw)
    semester = int(course.get("學期") or 0)
    year = course.get("學年度", "114")
    serial = course.get("流水號", "")

    name_zh = syllabus.get("課程名稱(中文)") or course.get("課程名稱(中文)", "")
    name_en = syllabus.get("課程名稱(英文)") or course.get("課程名稱(英文)", "")
    objective = syllabus.get("課程目標", "") or ""
    content = syllabus.get("授課內容", "") or ""
    dept = course.get("系所", "") or syllabus.get("開課單位", "")
    college = course.get("學院", "")
    credits_raw = syllabus.get("學分") or course.get("學分", "0")
    credits = int(credits_raw) if str(credits_raw).isdigit() else 0
    type_ = course.get("選修別", "")
    teacher = course.get("授課教師", "")

    # NLP 萃取
    nlp_data = nlp.get(code, {})
    tech = nlp_data.get("tech", {})
    languages = tech.get("languages", [])
    tools = tech.get("tools", [])
    concepts = tech.get("concepts", [])
    domain_tags = nlp_data.get("domain_tags", [])
    topic_tags = nlp_data.get("topic_tags", [])

    # 白話概念解釋（加入 embedding 文字）
    simplified = nlp_data.get("simplified", [])
    simplified_text = " ".join(
        sc.get("display", "") for sc in simplified if sc.get("display")
    )

    # 教師官方專長
    teacher_spec = teacher_lookup.get(teacher, "")

    # 應修學期
    sched = schedule_lookup.get(code, {})

    # 修課條件（v2 格式：elig 含 eligibility + course_relations 欄位）
    elig = eligibility_lookup.get(code, {})
    eligible_years = elig.get("eligible_years", [])
    prereq_codes = elig.get("prereq_codes", [])
    coreq_codes = elig.get("coreq_codes", [])
    conflict_codes = elig.get("conflict_codes", [])

    # core_questions（通識課，加入 embedding 文字提升語意命中率）
    core_qs = nlp_data.get("core_questions", [])

    # 教授研究領域（從 prof_links 萃取，補充語意）
    prof_links = nlp_data.get("prof_links", [])
    prof_fields = list({
        link["field"] for link in prof_links
        if isinstance(link, dict) and link.get("field")
    })[:5]

    # 參考書目
    textbook = syllabus.get("教科書/參考書", "") or ""
    # 核心能力名稱列表
    core_abilities = syllabus.get("核心能力", []) or []
    ability_names = [a.get("能力名稱", "") for a in core_abilities if isinstance(a, dict) and a.get("能力名稱")]

    # ── document text ──
    parts = []
    if name_zh:
        header = name_zh
        if name_en:
            header += f"（{name_en}）"
        parts.append(header)
    if dept:
        parts.append(f"開課系所：{dept}")
    if teacher:
        parts.append(f"授課教師：{teacher}")
    if teacher_spec:
        parts.append(f"教師專長：{teacher_spec}")
    if type_:
        parts.append(f"修課性質：{type_}")
    if sched.get("when_raw"):
        parts.append(f"建議修習：{sched['when_raw']}")
    if objective:
        parts.append(f"課程目標：{objective}")
    if content:
        parts.append(f"授課內容：{content}")
    if simplified_text:
        parts.append(f"相關概念：{simplified_text}")
    if languages or tools:
        parts.append(f"使用技術：{', '.join(languages + tools)}")
    if domain_tags:
        parts.append(f"課程領域：{', '.join(domain_tags)}")
    if topic_tags:
        parts.append(f"主題：{', '.join(topic_tags)}")
    if core_qs:
        parts.append(f"核心議題：{' '.join(core_qs[:3])}")
    if prof_fields:
        parts.append(f"相關研究領域：{', '.join(prof_fields)}")
    if ability_names:
        parts.append(f"核心能力：{', '.join(ability_names)}")
    if textbook:
        parts.append(f"參考書目：{textbook}")
    document = "\n".join(parts)

    # ── metadata（ChromaDB 只接受 str/int/float/bool）──
    meta: dict = {
        "course_code": code,
        "name_zh": name_zh,
        "name_en": name_en,
        "dept": dept,
        "college": college,
        "credits": credits,
        "type": type_,
        "semester": semester,
        "academic_year": year,
        "teacher": teacher,
        "is_grad": is_grad,
        "languages": join_list(languages),
        "tools": join_list(tools),
        "concepts": join_list(concepts),
        "domain_tags": join_list(domain_tags),
        "domain_tags_rich": nlp_data.get("domain_tags_rich", ""),
        "topic_tags":           join_list(topic_tags),
        "core_questions":       " | ".join(core_qs) if core_qs else "",
        "simplified_concepts":  "||".join(
            f"{c.get('original','')}::{c.get('display','')}"
            for c in nlp_data.get("simplified", [])
            if c.get("original") and c.get("display")
        ),
        "teacher_specialties": teacher_spec,
        # 修課資格（eligibility）
        "eligible_years":        join_list(eligible_years),
        "dept_include":          join_list(elig.get("dept_include", [])),
        "college_include":       join_list(elig.get("college_include", [])),
        "open_to_minor":         elig.get("open_to_minor", False),
        "open_to_double_major":  elig.get("open_to_double_major", False),
        "open_to_credit_prog":   elig.get("open_to_credit_prog", False),
        "open_to_cross_school":  elig.get("open_to_cross_school", False),
        "is_unrestricted":       elig.get("is_unrestricted", False),
        "is_grad_only":          elig.get("is_grad_only", False),
        "is_undergrad_open":     elig.get("is_undergrad_open", True),
        "has_special_condition": elig.get("has_special_condition", False),
        # 課程關係（course_relations）
        "prereq_codes":          join_list(prereq_codes),
        "coreq_codes":           join_list(coreq_codes),
        "conflict_codes":        join_list(conflict_codes),
        "has_prereq":            len(prereq_codes) > 0,
        # 應修學期（完整範圍資訊）
        "when_raw":          sched.get("when_raw", ""),
        "when_year_start":   sched.get("when_year_start", 0),
        "when_year_end":     sched.get("when_year_end", 0),
        "when_sem_start":    sched.get("when_sem_start", 0),
        "when_sem_end":      sched.get("when_sem_end", 0),
        "when_semesters":    sched.get("when_semesters", ""),
        "schedule_verified": sched.get("verified", False),
        # 課程大綱詳細欄位
        "objective": objective,
        "content":   content,
        "textbook":  textbook,
        # 課程附加資訊
        "course_domain":     syllabus.get("課程領域", "") or "",
        "class_time":        course.get("上課時間", "") or "",
        "capacity":          int(course.get("人數限制", 0) or 0) if str(course.get("人數限制", "0") or "0").isdigit() else 0,
    }

    doc_id = f"{year}{semester}_{serial}_{code}"
    return doc_id, document, meta


def load_all_courses(dirs: list[Path]) -> list[dict]:
    courses = []
    for d in dirs:
        if not d.exists():
            continue
        for fp in d.glob("*.json"):
            try:
                data = load_json(fp)
                if isinstance(data, list):
                    courses.extend(data)
            except Exception as e:
                print(f"  [WARN] {fp.name}: {e}")
    return courses


# ── 建立各 Collection ─────────────────────────────────────────────────────────

def build_courses_collection(
    client: chromadb.PersistentClient,
    embedder: Embedder,
    nlp: dict,
    teacher_lookup: dict,
    schedule_lookup: dict,
    eligibility_lookup: dict,
    name: str,
    dirs: list[Path],
    is_grad: bool,
):
    print(f"\n=== 建立 {name} ===")
    col = client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )

    raw = load_all_courses(dirs)

    # scraped_missing 只補到大學部
    if not is_grad and SCRAPED_MISSING.exists():
        try:
            extra = load_json(SCRAPED_MISSING)
            if isinstance(extra, list):
                raw.extend(extra)
                print(f"  scraped_missing 補充 {len(extra)} 筆")
        except Exception as e:
            print(f"  [WARN] scraped_missing: {e}")

    print(f"  原始課程數：{len(raw)}")

    # 去重：同 (course_code, semester) 只留一筆（114_2 優先，因後讀覆蓋前）
    seen: dict[str, dict] = {}
    for c in raw:
        code = clean_code(c.get("課號-班別", ""))
        sem = c.get("學期", "")
        key = f"{code}_{sem}"
        seen[key] = c  # 後讀的同 key 自然覆蓋（dirs 順序：114_1 → 114_2）
    deduped = list(seen.values())
    print(f"  去重後：{len(deduped)} 筆")

    ids, docs, metas = [], [], []
    skipped = 0
    for c in deduped:
        doc_id, doc_text, meta = build_course_doc(
            c, nlp, teacher_lookup, schedule_lookup, eligibility_lookup, is_grad
        )
        if not doc_text.strip():
            skipped += 1
            continue
        ids.append(doc_id)
        docs.append(doc_text)
        metas.append(meta)

    print(f"  略過空白文件：{skipped}，準備嵌入：{len(ids)}")

    # 已存在的不重複嵌入
    existing = set(col.get(ids=ids)["ids"]) if ids else set()
    new_mask = [i for i, did in enumerate(ids) if did not in existing]
    if not new_mask:
        print("  所有文件已在索引中，跳過。")
        return

    new_ids = [ids[i] for i in new_mask]
    new_docs = [docs[i] for i in new_mask]
    new_metas = [metas[i] for i in new_mask]
    print(f"  新增嵌入：{len(new_ids)} 筆")

    embeddings = []
    for i in tqdm(range(0, len(new_docs), EMBED_BATCH), desc=f"  Embedding {name}"):
        batch = new_docs[i : i + EMBED_BATCH]
        embeddings.extend(embedder.embed_batch(batch))

    # 分批寫入 ChromaDB（避免一次太大）
    for i in range(0, len(new_ids), 500):
        col.add(
            ids=new_ids[i : i + 500],
            documents=new_docs[i : i + 500],
            embeddings=embeddings[i : i + 500],
            metadatas=new_metas[i : i + 500],
        )
    print(f"  完成，collection 總數：{col.count()}")


def build_programs_collection(
    client: chromadb.PersistentClient,
    embedder: Embedder,
):
    print("\n=== 建立 ncu_credit_programs ===")
    col = client.get_or_create_collection(
        name="ncu_credit_programs",
        metadata={"hnsw:space": "cosine"},
    )

    # 載入 program_descriptions（自由文字）
    desc_map: dict[str, str] = {}
    if PROGRAM_DESC.exists():
        raw = load_json(PROGRAM_DESC)
        if isinstance(raw, dict):
            desc_map = {k: v.get("description", "") for k, v in raw.items()}

    # 載入 credit_programs（結構化課程列表）
    programs: list[dict] = []
    if CREDIT_PROGRAMS_DIR.exists():
        for fp in CREDIT_PROGRAMS_DIR.glob("*.json"):
            try:
                data = load_json(fp)
                if isinstance(data, list):
                    programs.extend(data)
            except Exception:
                pass

    print(f"  載入 {len(programs)} 個學分學程")

    ids, docs, metas = [], [], []
    for p in programs:
        pid = p.get("id", "")
        pname = p.get("name", "")
        college = p.get("college", "")
        min_credits = p.get("min_credits", 0)
        description = desc_map.get(pname, p.get("description", ""))

        # 課程名稱清單
        course_names = []
        for rc in p.get("required_courses", []):
            course_names.append(rc.get("name", ""))
        for eg in p.get("elective_groups", []):
            for c in eg.get("courses", []):
                course_names.append(c.get("name", ""))
        course_names = [n for n in course_names if n]

        parts = [f"{pname}（{college}，最低 {min_credits} 學分）"]
        if description:
            parts.append(description)
        if course_names:
            parts.append(f"包含課程：{', '.join(course_names[:30])}")
        doc_text = "\n".join(parts)

        if not doc_text.strip() or not pid:
            continue

        ids.append(pid)
        docs.append(doc_text)
        metas.append({
            "program_id": pid,
            "program_name": pname,
            "college": college,
            "min_credits": int(min_credits) if str(min_credits).isdigit() else 0,
        })

    existing = set(col.get(ids=ids)["ids"]) if ids else set()
    new_mask = [i for i, did in enumerate(ids) if did not in existing]
    if not new_mask:
        print("  所有學程已在索引中，跳過。")
        return

    new_ids = [ids[i] for i in new_mask]
    new_docs = [docs[i] for i in new_mask]
    new_metas = [metas[i] for i in new_mask]

    embeddings = embedder.embed_batch(new_docs)
    col.add(ids=new_ids, documents=new_docs, embeddings=embeddings, metadatas=new_metas)
    print(f"  完成，collection 總數：{col.count()}")


def build_departments_collection(
    client: chromadb.PersistentClient,
    embedder: Embedder,
):
    print("\n=== 建立 ncu_departments ===")
    col = client.get_or_create_collection(
        name="ncu_departments",
        metadata={"hnsw:space": "cosine"},
    )

    if not COLLEGO.exists():
        print(f"  [WARN] 找不到 {COLLEGO}")
        return

    depts = load_json(COLLEGO)
    if not isinstance(depts, list):
        print("  [WARN] collego_ncu.json 格式異常")
        return

    ids, docs, metas = [], [], []
    for d in depts:
        dept_id = d.get("dept_id", "")
        dept_name = d.get("dept_name", "")
        intro: dict = d.get("學系介紹", {}) or {}

        parts = [dept_name]
        for field in ["學系特色", "學科意涵", "生涯進路", "能力特質"]:
            val = intro.get(field, "")
            if val:
                parts.append(f"{field}：{val}")
        learn = intro.get("學習方法", [])
        if isinstance(learn, list) and learn:
            parts.append(f"學習方法：{'；'.join(learn)}")
        elif isinstance(learn, str) and learn:
            parts.append(f"學習方法：{learn}")

        course_info = d.get("課程資訊", "")
        if course_info:
            parts.append(f"課程資訊：{course_info}")

        doc_text = "\n".join(parts)
        if not doc_text.strip() or not dept_id:
            continue

        ids.append(dept_id)
        docs.append(doc_text)
        metas.append({"dept_id": dept_id, "dept_name": dept_name})

    existing = set(col.get(ids=ids)["ids"]) if ids else set()
    new_mask = [i for i, did in enumerate(ids) if did not in existing]
    if not new_mask:
        print("  所有系所已在索引中，跳過。")
        return

    new_ids = [ids[i] for i in new_mask]
    new_docs = [docs[i] for i in new_mask]
    new_metas = [metas[i] for i in new_mask]

    embeddings = embedder.embed_batch(new_docs)
    col.add(ids=new_ids, documents=new_docs, embeddings=embeddings, metadatas=new_metas)
    print(f"  完成，collection 總數：{col.count()}")


def build_teachers_collection(
    client: chromadb.PersistentClient,
    embedder: Embedder,
    teacher_lookup: dict[str, str],
):
    print("\n=== 建立 ncu_teachers ===")
    col = client.get_or_create_collection(
        name="ncu_teachers",
        metadata={"hnsw:space": "cosine"},
    )

    if not TEACHER_CSV.exists():
        print(f"  [WARN] 找不到 {TEACHER_CSV}")
        return

    rows = []
    with open(TEACHER_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)

    # 同名教師可能在多系所任職，全部保留（用 dept+name 作 ID）
    ids, docs, metas = [], [], []
    for row in rows:
        name = row["教師名稱"].strip()
        dept = row["系所名稱"].strip()
        rank = row["聘書職級"].strip()
        type_ = row["專兼任"].strip()
        spec = row["教師專長"].strip()

        if not name:
            continue

        spec_list = [s.strip() for s in re.split(r"[,，、]", spec) if s.strip()]
        doc_text = (
            f"{name}（{dept}，{rank}，{type_}）\n"
            f"專長：{chr(10).join(spec_list)}"
        )
        doc_id = f"teacher_{dept}_{name}"

        ids.append(doc_id)
        docs.append(doc_text)
        metas.append({
            "name": name,
            "dept": dept,
            "rank": rank,
            "type": type_,
            "specialties": spec,
        })

    existing = set(col.get(ids=ids)["ids"]) if ids else set()
    new_mask = [i for i, did in enumerate(ids) if did not in existing]
    if not new_mask:
        print("  所有教師已在索引中，跳過。")
        return

    new_ids = [ids[i] for i in new_mask]
    new_docs = [docs[i] for i in new_mask]
    new_metas = [metas[i] for i in new_mask]

    embeddings = embedder.embed_batch(new_docs)
    col.add(ids=new_ids, documents=new_docs, embeddings=embeddings, metadatas=new_metas)
    print(f"  完成，collection 總數：{col.count()}")


# ── 主程式 ───────────────────────────────────────────────────────────────────

def update_metadata_only(chroma: chromadb.PersistentClient) -> None:
    """
    只更新課程 collection 的 eligibility metadata（is_grad_only / is_undergrad_open / eligible_years）。
    不重新 embed，不需要 API key。
    """
    eligibility_lookup = load_eligibility_lookup()

    for col_name in ["ncu_courses_ug", "ncu_courses_grad"]:
        try:
            col = chroma.get_collection(col_name)
        except Exception:
            print(f"[跳過] {col_name} 不存在")
            continue

        result = col.get(include=["metadatas"])
        ids: list[str] = result["ids"]
        metadatas: list[dict] = result["metadatas"]

        update_ids, update_metas = [], []
        for doc_id, meta in zip(ids, metadatas):
            code = meta.get("course_code", "")
            elig = eligibility_lookup.get(code)
            if not elig:
                continue

            new_grad_only     = elig.get("is_grad_only", False)
            new_ug_open       = elig.get("is_undergrad_open", True)
            new_years         = join_list(elig.get("eligible_years", []))

            if (meta.get("is_grad_only")      != new_grad_only
                    or meta.get("is_undergrad_open") != new_ug_open
                    or meta.get("eligible_years")    != new_years):
                update_ids.append(doc_id)
                update_metas.append({**meta,
                    "is_grad_only":      new_grad_only,
                    "is_undergrad_open": new_ug_open,
                    "eligible_years":    new_years,
                })

        if not update_ids:
            print(f"[{col_name}] 無需更新（共 {len(ids)} 筆）")
            continue

        batch = 500
        for i in range(0, len(update_ids), batch):
            col.update(ids=update_ids[i:i+batch], metadatas=update_metas[i:i+batch])
        print(f"[{col_name}] 更新 {len(update_ids)} / {len(ids)} 筆 metadata")


def main():
    parser = argparse.ArgumentParser(description="建立或更新 ChromaDB 向量索引")
    parser.add_argument(
        "--metadata-only", action="store_true",
        help="只更新 eligibility metadata（不重新 embed，不需要 API key）"
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    chroma = chromadb.PersistentClient(path=str(CHROMA_DIR))

    if args.metadata_only:
        update_metadata_only(chroma)
        return

    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
    embed_deployment = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")

    if not api_key or not endpoint:
        raise EnvironmentError("請在 .env 設定 AZURE_OPENAI_API_KEY 和 AZURE_OPENAI_ENDPOINT")

    oai = AzureOpenAI(
        api_key=api_key,
        azure_endpoint=endpoint,
        api_version=api_version,
    )
    embedder = Embedder(oai, embed_deployment)
    chroma = chromadb.PersistentClient(path=str(CHROMA_DIR))

    nlp = load_nlp_data()
    teacher_lookup = load_teacher_csv()
    schedule_lookup = load_schedule_lookup()
    eligibility_lookup = load_eligibility_lookup()

    # 大學部課程
    build_courses_collection(
        chroma, embedder, nlp, teacher_lookup, schedule_lookup, eligibility_lookup,
        name="ncu_courses_ug",
        dirs=[COURSES_114_1, COURSES_114_2],
        is_grad=False,
    )

    # 研究所課程
    build_courses_collection(
        chroma, embedder, nlp, teacher_lookup, schedule_lookup, eligibility_lookup,
        name="ncu_courses_grad",
        dirs=[GRAD_114_1, GRAD_114_2],
        is_grad=True,
    )

    # 學分學程
    build_programs_collection(chroma, embedder)

    # 系所介紹
    build_departments_collection(chroma, embedder)

    # 教師專長
    build_teachers_collection(chroma, embedder, teacher_lookup)

    print("\n✓ 所有 collection 建立完成")
    print(f"  儲存位置：{CHROMA_DIR}")
    for col_name in ["ncu_courses_ug", "ncu_courses_grad", "ncu_credit_programs",
                     "ncu_departments", "ncu_teachers"]:
        try:
            col = chroma.get_collection(col_name)
            print(f"  {col_name}: {col.count()} 筆")
        except Exception:
            pass


if __name__ == "__main__":
    main()
