"""
run_agent3_topics.py  —  Agent 3：通識課程主題分類與核心議題萃取

針對類型 TOPICS_ONLY 的課程（通識教育中心、核心通識課程）：
  1. 主題分類：人文/社會/自然科學/應用科技/跨域通識
  2. 核心議題：這門課想讓學生思考什麼問題（2-4 個，存為課程屬性）

輸入：
  data/raw/courses/114_1/*.json

輸出：
  data/processed/nlp_topic_tags.json

格式：
{
  "課號": {
    "topic_tags": ["哲學", "倫理學"],
    "core_questions": ["什麼是幸福？", "道德判斷有客觀標準嗎？"]
  }
}

模型：Qwen3-14B，via vLLM openai-compatible API
      預設端點：http://localhost:8000/v1
      啟動指令：vllm serve Qwen/Qwen3-14B-AWQ --max-model-len 8192 --gpu-memory-utilization 0.8
"""

import json
import re
from pathlib import Path

from openai import OpenAI

BASE     = Path(__file__).parent.parent.parent
RAW_DIRS = [
    BASE / "data" / "raw" / "courses",
]
OUT_PATH = BASE / "data" / "processed" / "nlp_topic_tags.json"

# ── 後端設定（vLLM）─────────────────────────────────────────
# 啟動：vllm serve Qwen/Qwen3-14B-AWQ --max-model-len 8192 --gpu-memory-utilization 0.8
MODEL    = "Qwen/Qwen3-14B-AWQ"
API_BASE = "http://localhost:8000/v1"
API_KEY  = "token-abc"
BACKEND  = "vllm"
# ─────────────────────────────────────────────────────────────

NUM_CTX       = 8192
BOOKS_MAX_LEN = 2000

# 通識課程的系所關鍵字
TOPICS_ONLY_KW = ["通識", "核心通識"]

PROMPT_TEMPLATE = """\
請分析以下通識課程，萃取出主題分類與核心議題。
所有輸出的文字必須使用繁體中文，不得使用簡體中文。

開課系所：{dept}
課程名稱：{course_name}
課程目標：{objective}
授課內容（節錄）：{content}
教科書/參考書：{books}

可選主題標籤（最多選 3 個）：
人文領域：哲學、歷史、文學、語言學、藝術、音樂
社會領域：社會學、心理學、法律、政治、經濟
自然科學：物理、化學、生物、環境科學、數學
應用科技：資訊科技、工程、醫學
跨域通識：倫理學、性別研究、族群文化、全球化、永續發展

輸出格式（只輸出 JSON，不要有其他文字，不要有 markdown）：
{{
  "topic_tags": ["主題標籤1"],
  "core_questions": ["這門課探討的核心問題1", "問題2"]
}}

說明：
- topic_tags：從上方可選標籤中選 1-3 個，只選最符合的
- core_questions：用一句問句描述這門課的核心探討問題，2-4 個，要具體不要太抽象
- 若課程目標太短或不足以判斷，topic_tags 仍要填，core_questions 可為 []
- 所有輸出的文字必須使用繁體中文，不得使用簡體中文

core_questions 範例：
- 「什麼是幸福？幸福能被追求嗎？」（哲學課）
- 「全球化如何影響在地文化認同？」（社會學課）
- 「氣候變遷對台灣生態系有哪些具體衝擊？」（環境課）
- 「人工智慧的發展會帶來哪些倫理困境？」（科技倫理課）"""


def is_topics_only(dept: str) -> bool:
    return any(kw in dept for kw in TOPICS_ONLY_KW)


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


def extract_topics(client: OpenAI, course: dict) -> dict | None:
    outline   = course.get("課程綱要", {}) or {}
    objective = (outline.get("課程目標", "") or course.get("課程目標", "") or "").strip()
    content   = (outline.get("授課內容", "") or course.get("授課內容", "") or "").strip()
    books     = (outline.get("教科書/參考書", "") or course.get("教科書/參考書", "") or "").strip()
    name      = course.get("課程名稱(中文)", "").strip()
    dept      = course.get("系所", course.get("department", "")).strip()

    if not objective and not content:
        return None

    prompt = PROMPT_TEMPLATE.format(
        dept=dept,
        course_name=name,
        objective=objective,
        content=content,
        books=books[:BOOKS_MAX_LEN],
    )

    try:
        kwargs = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0}
        if BACKEND == "ollama":
            kwargs["extra_body"] = {"options": {"num_ctx": NUM_CTX}}
        resp = client.chat.completions.create(**kwargs)
        raw = resp.choices[0].message.content.strip()
        # 寫入 debug log
        with open(BASE / "logs" / "agent3_llm_debug.txt", "a", encoding="utf-8") as dbg:
            dbg.write(f"\n{'='*60}\n[{course.get('課程名稱(中文)','')}]\n{raw}\n")
        # 移除 Qwen3 thinking block
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  JSON 解析失敗：{e}，raw={repr(raw[:100])}")
        return {"topic_tags": [], "core_questions": [], "error": True}
    except Exception as e:
        print(f"  LLM 錯誤：{e}")
        return {"topic_tags": [], "core_questions": [], "error": True}


def main():
    print("Agent 3：通識課程主題分類與核心議題萃取")
    print(f"模型：{MODEL}  端點：{API_BASE}")

    if OUT_PATH.exists():
        with open(OUT_PATH, encoding="utf-8") as f:
            results: dict = json.load(f)
        print(f"載入已有結果：{len(results)} 筆，從斷點繼續")
    else:
        results: dict = {}

    courses = load_courses()
    print(f"載入課程：{len(courses)} 門")

    client = OpenAI(base_url=API_BASE, api_key=API_KEY)

    to_process = [
        (code, c) for code, c in courses.items()
        if (code not in results or results[code].get("error"))
        and is_topics_only(c.get("系所", c.get("department", "")))
    ]
    print(f"待處理通識課程：{len(to_process)} 門")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    for i, (code, course) in enumerate(to_process, 1):
        name   = course.get("課程名稱(中文)", code)
        result = extract_topics(client, course)

        if result is None:
            results[code] = {"topic_tags": [], "core_questions": [], "skipped": True}
        elif result.get("error"):
            results[code] = {"topic_tags": [], "core_questions": [], "error": True}
        else:
            results[code] = {
                "topic_tags": result.get("topic_tags", []),
                "core_questions": result.get("core_questions", []),
            }

        if i % 20 == 0:
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"  [{i}/{len(to_process)}] 已存檔")

        if i % 5 == 0:
            print(f"  [{i}/{len(to_process)}] {name[:30]}")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    non_empty = sum(1 for v in results.values() if not v.get("skipped") and v.get("topic_tags"))
    print(f"\n完成：{len(results)} 筆，其中 {non_empty} 筆有主題標籤")
    print(f"輸出：{OUT_PATH}")


if __name__ == "__main__":
    main()
