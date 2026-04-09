"""
run_agent1_tech.py  —  Agent 1：技術節點萃取

針對類型 FULL / PARTIAL 的課程，從課程目標和授課內容中萃取：
  - languages：程式語言
  - tools：框架/工具/軟體
  - concepts：核心學科概念

輸入：
  data/raw/courses/114_1/*.json
  data/raw/graduate_courses/**/*.json（若存在）

輸出：
  data/processed/nlp_tech_nodes.json

模型：Qwen3-14B (Q8_0)，via Ollama openai-compatible API
      預設端點：http://localhost:11434/v1
"""

import json
import re
import sys
import time
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    print("請先安裝 openai：pip install openai")
    sys.exit(1)

BASE      = Path(__file__).parent.parent.parent
RAW_DIRS  = [
    BASE / "data" / "raw" / "courses",
    BASE / "data" / "raw" / "graduate_courses",
]
OUT_PATH  = BASE / "data" / "processed" / "nlp_tech_nodes.json"

sys.path.insert(0, str(BASE / "scripts" / "nlp"))
from course_classifier import classify_course  # noqa: E402

# ── 後端設定（擇一）─────────────────────────────────────────
# Ollama（Q8_0，GGUF）：
#   ollama pull qwen3:14b
MODEL    = "qwen3:14b"
API_BASE = "http://localhost:11434/v1"
API_KEY  = "ollama"
BACKEND  = "ollama"   # "ollama" | "vllm"

# vLLM（FP8，速度約快 1.5-2x，需 Ada Lovelace GPU）：
#   pip install vllm
#   vllm serve Qwen/Qwen3-14B-FP8 --max-model-len 8192 --gpu-memory-utilization 0.9
# MODEL    = "Qwen/Qwen3-14B-FP8"
# API_BASE = "http://localhost:8000/v1"
# API_KEY  = "token-abc"
# BACKEND  = "vllm"
# ─────────────────────────────────────────────────────────────

# Ollama 需在每次 request 帶入 num_ctx；vLLM 於啟動時由 --max-model-len 決定
NUM_CTX       = 8192
BOOKS_MAX_LEN = 2000

PROMPT_TEMPLATE = """\
你是一個課程資訊萃取助手。
請從以下課程資料中，找出技術名詞，分成三類輸出 JSON。

開課系所：{dept}
課程名稱：{course_name}
課程目標：{objective}
授課內容：{content}
教科書/參考書：{books}

輸出格式（只輸出 JSON，不要有其他文字，不要有 markdown）：
{{
  "languages": [],
  "tools": [],
  "concepts": []
}}

說明：
- languages：程式語言，例如 Python, C++, Java, R, MATLAB, Julia
- tools：框架/工具/軟體，例如 PyTorch, TensorFlow, Docker, Git, SPSS, AutoCAD, Excel, ANSYS
- concepts：核心學科概念，例如 資料結構, 微積分, 傅立葉變換, 機率統計, 熱力學, 數值方法
- 教科書書名本身不算技術名詞，但書中提到的技術/語言/工具可以算
- 如果某一類沒有，輸出空陣列 []
- 不要包含人名、機構名、課程名"""



def load_courses() -> dict:
    """載入所有 raw 課程，回傳 code → course_dict。"""
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

            if isinstance(data, list):
                items = data
            elif isinstance(data, dict) and "courses" in data:
                items = data["courses"]
            else:
                continue

            for c in items:
                code_raw = c.get("課號-班別", "")
                code = sep.sub("", code_raw.strip())
                if not code:
                    continue
                if code in courses:
                    continue
                courses[code] = c

    return courses


def extract_tech(client: OpenAI, course: dict) -> dict | None:
    """呼叫 LLM 萃取技術節點，回傳 {languages, tools, concepts} 或 None。"""
    outline   = course.get("課程綱要", {}) or {}
    objective = (outline.get("課程目標", "") or course.get("課程目標", "") or "").strip()
    content   = (outline.get("授課內容", "") or course.get("授課內容", "") or "").strip()
    books     = (outline.get("教科書/參考書", "") or course.get("教科書/參考書", "") or "").strip()
    name      = course.get("課程名稱(中文)", "").strip()
    dept      = course.get("系所", course.get("department", "")).strip()

    # 若目標和內容都是空的，跳過
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
                  "temperature": 0.1}
        if BACKEND == "ollama":
            kwargs["extra_body"] = {"options": {"num_ctx": NUM_CTX}}
        resp = client.chat.completions.create(**kwargs)
        raw = resp.choices[0].message.content.strip()
        # 移除可能的 markdown code block
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
    except Exception as e:
        print(f"  LLM 錯誤：{e}")
        return None


def main():
    print("Agent 1：技術節點萃取")
    print(f"模型：{MODEL}  端點：{API_BASE}")

    # 若已有部分結果，從斷點繼續
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
        if code not in results
        and classify_course(c) == "FULL"
    ]
    print(f"待處理：{len(to_process)} 門（已跳過 SKIP/SEQUENCE_ONLY/TOPICS_ONLY 與已完成）")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    for i, (code, course) in enumerate(to_process, 1):
        name = course.get("課程名稱(中文)", code)
        result = extract_tech(client, course)

        if result is None:
            results[code] = {"languages": [], "tools": [], "concepts": [], "skipped": True}
        else:
            results[code] = result

        # 每 50 筆存一次（斷點恢復）
        if i % 50 == 0:
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"  [{i}/{len(to_process)}] 已存檔")

        if i % 10 == 0:
            print(f"  [{i}/{len(to_process)}] {name[:30]}")

        time.sleep(0.05)  # 避免過快打爆 Ollama

    # 最終存檔
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    non_empty = sum(
        1 for v in results.values()
        if not v.get("skipped") and (v.get("languages") or v.get("tools") or v.get("concepts"))
    )
    print(f"\n完成：共 {len(results)} 筆，其中 {non_empty} 筆有萃取結果")
    print(f"輸出：{OUT_PATH}")


if __name__ == "__main__":
    main()
