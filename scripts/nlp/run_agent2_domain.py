"""
run_agent2_domain.py  —  Agent 2：教授專長領域匹配

針對類型 FULL / PARTIAL 的課程，根據課程內容從該系所教授的研究領域詞彙表中
選出最相關的領域標籤（high / medium / low）。

LLM 只輸出「領域名稱 + 關聯強度」，不需要輸出教授姓名。
教授帶入由後處理函式 find_related_professors() 完成。

輸入：
  data/processed/dept_professor_map.json        （由 normalize_teacher_specialties.py 產生）
  data/raw/courses/114_1/*.json

輸出：
  data/processed/nlp_domain_tags.json
  data/processed/nlp_professor_links.json       （後處理：領域 → 相關教授）

模型：Qwen3-14B，via vLLM openai-compatible API
      預設端點：http://localhost:8000/v1
      啟動指令：vllm serve Qwen/Qwen3-14B-AWQ --max-model-len 8192 --gpu-memory-utilization 0.8
"""

import json
import re
import sys
from pathlib import Path

from openai import OpenAI

try:
    import opencc
    _S2T = opencc.OpenCC("s2tw")
except ImportError:
    _S2T = None

BASE          = Path(__file__).parent.parent.parent
RAW_DIRS      = [
    BASE / "data" / "raw" / "courses",
    BASE / "data" / "raw" / "graduate_courses",
]
DEPT_MAP_PATH  = BASE / "data" / "processed" / "nlp" / "dept_professor_map.json"
TECH_NODES_PATH = BASE / "data" / "processed" / "nlp" / "nlp_tech_nodes.json"
OUT_TAGS       = BASE / "data" / "processed" / "nlp" / "nlp_domain_tags.json"
OUT_LINKS      = BASE / "data" / "processed" / "nlp" / "nlp_professor_links.json"

# ── 後端設定（vLLM）─────────────────────────────────────────
# 啟動：vllm serve Qwen/Qwen3-14B-AWQ --max-model-len 8192 --gpu-memory-utilization 0.8
MODEL    = "Qwen/Qwen3-14B-AWQ"
API_BASE = "http://localhost:8000/v1"
API_KEY  = "token-abc"
BACKEND  = "vllm"
# ─────────────────────────────────────────────────────────────

NUM_CTX  = 8192   # Ollama 用；vLLM 由 --max-model-len 8192 決定

# 教科書欄有少數極端異常值（最大 64K），設合理上限避免爆 context
# p99 正常課程約 2000 字元，2000 已足夠
BOOKS_MAX_LEN = 2000

SKIP_KW          = ["體育", "軍訓"]
SEQUENCE_ONLY_KW = ["語言中心", "服務學習", "職涯"]
TOPICS_ONLY_KW   = ["通識", "核心通識"]

PROMPT_TEMPLATE = """\
你是一個課程分析助手。
請根據課程資訊，從以下「可選領域詞彙表」中挑選最符合的領域標籤。
所有輸出的文字必須使用繁體中文，不得使用簡體中文。

開課系所：{dept}
課程名稱：{course_name}
課程目標：{objective}
授課內容（節錄）：{content}
教科書/參考書：{books}
{tech_section}
本系所教授的研究領域詞彙表（只能從這裡面選，不要自己創造新詞）：
{vocab}

請先思考：這門課用到哪些技術/工具/概念？這些技術屬於哪些學術研究領域？詞彙表中哪些領域和這些技術最相關？
然後選出 1-15 個最相關的領域，並為每個領域標記關聯強度。

輸出格式（只輸出 JSON，不要有其他文字，不要有 markdown）：
{{
  "domain_tags": [
    {{"field": "領域名稱", "relevance": "high"}}
  ]
}}

關聯強度定義：
- high：這門課的核心內容就是這個領域
- medium：這門課會用到或涉及這個領域
- low：這門課的背景知識需要這個領域

規則：
- 只從詞彙表中選，不要自己創造新詞
- 不確定時寧可少選，不要強行填滿 15 個
- 若詞彙表中沒有符合的，輸出 {{"domain_tags": []}}
- 所有輸出的文字必須使用繁體中文，不得使用簡體中文，請務必確認輸出 JSON 中的領域名稱與詞彙表完全一致（不需要自己翻譯或改寫）"""


def classify_course(dept: str) -> str:
    if any(kw in dept for kw in SKIP_KW):
        return "SKIP"
    if any(kw in dept for kw in SEQUENCE_ONLY_KW):
        return "SEQUENCE_ONLY"
    if any(kw in dept for kw in TOPICS_ONLY_KW):
        return "TOPICS_ONLY"
    return "FULL"


def load_courses() -> dict:
    courses = {}
    sep = re.compile(r"-[A-Z0-9*]+$")
    for raw_dir in RAW_DIRS:
        if not raw_dir.exists():
            continue
        for json_file in sorted(raw_dir.rglob("*.json")):
            try:
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            items = data if isinstance(data, list) else data.get("courses", [])
            for c in items:
                code = sep.sub("", c.get("課號-班別", "").strip())
                if code and code not in courses:
                    courses[code] = c
    return courses


def get_dept_vocab(course: dict, dept_map: dict) -> list[str]:
    """取得課程所屬系所的教授研究領域詞彙表。"""
    dept = course.get("系所", course.get("department", "")).strip()
    # 直接命中
    if dept in dept_map:
        return dept_map[dept]["specialty_vocab"]
    # 模糊匹配：系所名稱包含關係
    for key in dept_map:
        if key in dept or dept in key:
            return dept_map[key]["specialty_vocab"]
    return []


def build_tech_section(tech: dict | None) -> str:
    """將 Agent 1 的輸出格式化成 prompt 片段。若無資料則回傳空字串。"""
    if not tech:
        return ""
    parts = []
    if tech.get("languages"):
        parts.append("程式語言：" + "、".join(tech["languages"]))
    if tech.get("tools"):
        parts.append("使用工具/框架：" + "、".join(tech["tools"]))
    if tech.get("concepts"):
        parts.append("涉及概念：" + "、".join(tech["concepts"]))
    if not parts:
        return ""
    return "Agent 1 已識別的技術資訊（供參考）：\n" + "\n".join(parts) + "\n\n"


def match_domains(client: OpenAI, course: dict, vocab: list[str],
                  tech: dict | None = None) -> list[dict] | None:
    """呼叫 LLM，從 vocab 中選出與課程相關的領域標籤。
    tech：Agent 1 的輸出（languages/tools/concepts），作為 CoT 線索。
    """
    outline   = course.get("課程綱要", {}) or {}
    objective = (outline.get("課程目標", "") or course.get("課程目標", "") or "").strip()
    content   = (outline.get("授課內容", "") or course.get("授課內容", "") or "").strip()
    books     = (outline.get("教科書/參考書", "") or course.get("教科書/參考書", "") or "").strip()
    name      = course.get("課程名稱(中文)", "").strip()
    dept      = course.get("系所", course.get("department", "")).strip()

    if not objective and not content:
        return None
    if not vocab:
        return None

    # 詞彙表太長時截斷（避免超過 context window）
    vocab_str = "、".join(vocab[:80])

    prompt = PROMPT_TEMPLATE.format(
        dept=dept,
        course_name=name,
        objective=objective,                   # 完整送入（p99 約 650 字元）
        content=content,                       # 完整送入（p99 約 1700 字元）
        books=books[:BOOKS_MAX_LEN],           # 僅教科書需截斷（有 64K 異常值）
        tech_section=build_tech_section(tech),
        vocab=vocab_str,
    )

    try:
        kwargs = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0}
        if BACKEND == "ollama":
            kwargs["extra_body"] = {"options": {"num_ctx": NUM_CTX}}
        resp = client.chat.completions.create(**kwargs)
        raw = resp.choices[0].message.content.strip()
        # 寫入 debug log
        with open(BASE / "logs" / "agent2_llm_debug.txt", "a", encoding="utf-8") as dbg:
            dbg.write(f"\n{'='*60}\n[{course.get('課程名稱(中文)','')}]\n{raw}\n")
        # 移除 Qwen3 thinking block
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        parsed = json.loads(raw)
        tags = parsed.get("domain_tags", [])
        if _S2T is not None:
            for tag in tags:
                if "field" in tag:
                    tag["field"] = _S2T.convert(tag["field"])
        return tags
    except json.JSONDecodeError as e:
        print(f"  JSON 解析失敗：{e}，raw={repr(raw[:100])}")
        return "error"
    except Exception as e:
        print(f"  LLM 錯誤：{e}")
        return "error"


def find_related_professors(domain_tags: list[dict], course: dict, dept_map: dict) -> list[dict]:
    """
    後處理：根據領域標籤，從 dept_professor_map 反查相關教授。
    回傳 [{"field": "機器學習", "professors": ["陳某某"], "relevance": "high"}]
    """
    dept = course.get("系所", course.get("department", "")).strip()
    prof_list = []
    if dept in dept_map:
        prof_list = dept_map[dept]["professors"]
    else:
        for key in dept_map:
            if key in dept or dept in key:
                prof_list = dept_map[key]["professors"]
                break

    result = []
    for tag in domain_tags:
        field = tag.get("field", "")
        matched = [p["name"] for p in prof_list if field in p["specialties"]]
        if matched:
            result.append({
                "field": field,
                "professors": matched,
                "relevance": tag.get("relevance", "medium"),
            })
    return result


def main():
    print("Agent 2：教授專長領域匹配")
    print(f"模型：{MODEL}  端點：{API_BASE}")

    if not DEPT_MAP_PATH.exists():
        print(f"找不到 dept_professor_map.json，請先執行 normalize_teacher_specialties.py")
        sys.exit(1)

    with open(DEPT_MAP_PATH, encoding="utf-8") as f:
        dept_map = json.load(f)
    print(f"載入 dept_professor_map：{len(dept_map)} 個系所")

    # 載入 Agent 1 輸出（可選，若尚未執行則繼續但無 tech 線索）
    tech_nodes: dict = {}
    if TECH_NODES_PATH.exists():
        with open(TECH_NODES_PATH, encoding="utf-8") as f:
            tech_nodes = json.load(f)
        non_empty = sum(1 for v in tech_nodes.values() if not v.get("skipped")
                        and (v.get("languages") or v.get("tools") or v.get("concepts")))
        print(f"載入 nlp_tech_nodes：{len(tech_nodes)} 筆，其中 {non_empty} 筆有技術資訊")
    else:
        print("未找到 nlp_tech_nodes.json，將不使用 Agent 1 技術線索（建議先執行 run_agent1_tech.py）")

    # 斷點續跑
    if OUT_TAGS.exists():
        with open(OUT_TAGS, encoding="utf-8") as f:
            domain_results: dict = json.load(f)
        print(f"載入已有結果：{len(domain_results)} 筆，從斷點繼續")
    else:
        domain_results: dict = {}

    courses = load_courses()
    print(f"載入課程：{len(courses)} 門")

    client = OpenAI(base_url=API_BASE, api_key=API_KEY)

    to_process = [
        (code, c) for code, c in courses.items()
        if (code not in domain_results or domain_results[code].get("error"))
        and classify_course(c.get("系所", c.get("department", ""))) in ("FULL", "PARTIAL")
    ]
    print(f"待處理：{len(to_process)} 門")

    OUT_TAGS.parent.mkdir(parents=True, exist_ok=True)

    for i, (code, course) in enumerate(to_process, 1):
        name  = course.get("課程名稱(中文)", code)
        vocab = get_dept_vocab(course, dept_map)
        tech  = tech_nodes.get(code)  # Agent 1 的輸出，若無則 None
        tags  = match_domains(client, course, vocab, tech=tech)

        if tags is None:
            domain_results[code] = {"domain_tags": [], "skipped": True}
        elif tags == "error":
            domain_results[code] = {"domain_tags": [], "error": True}
        else:
            domain_results[code] = {"domain_tags": tags}

        if i % 50 == 0:
            with open(OUT_TAGS, "w", encoding="utf-8") as f:
                json.dump(domain_results, f, ensure_ascii=False, indent=2)
            print(f"  [{i}/{len(to_process)}] 已存檔")

        if i % 10 == 0:
            print(f"  [{i}/{len(to_process)}] {name[:30]}")

    # 最終存檔 domain_tags
    with open(OUT_TAGS, "w", encoding="utf-8") as f:
        json.dump(domain_results, f, ensure_ascii=False, indent=2)

    # 後處理：帶入教授資訊
    print("\n後處理：帶入相關教授...")
    professor_links: dict = {}
    prof_error_count = 0
    for code, data in domain_results.items():
        if data.get("skipped") or data.get("error"):
            continue
        course = courses.get(code, {})
        links = find_related_professors(data["domain_tags"], course, dept_map)
        if links:
            professor_links[code] = links
        elif data.get("domain_tags"):
            # 有領域標籤但完全沒匹配到教授 → 標記 error 讓下次重跑
            domain_results[code]["error"] = True
            prof_error_count += 1

    # 後處理後重新存檔（含 error 標記）
    with open(OUT_TAGS, "w", encoding="utf-8") as f:
        json.dump(domain_results, f, ensure_ascii=False, indent=2)

    with open(OUT_LINKS, "w", encoding="utf-8") as f:
        json.dump(professor_links, f, ensure_ascii=False, indent=2)

    non_empty = sum(1 for v in domain_results.values() if v.get("domain_tags"))
    print(f"\n完成：{len(domain_results)} 筆，其中 {non_empty} 筆有領域標籤")
    print(f"標記為 error（無教授匹配）：{prof_error_count} 筆，下次重跑時會重試")
    print(f"相關教授連結：{len(professor_links)} 門課有對應教授")
    print(f"輸出：{OUT_TAGS}")
    print(f"輸出：{OUT_LINKS}")


if __name__ == "__main__":
    main()
