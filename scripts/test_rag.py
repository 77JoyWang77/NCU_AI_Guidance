"""
test_rag.py

自動測試 /api/chat/stream，將每題的工具呼叫細節、推薦課程、完整回答
記錄成 JSON + 易讀 Markdown 報告。

每題都會呼叫 /api/chat/stream（SSE），因此 session 也會存入後端，
可在前端歷史對話中查看。

執行方式：
  python scripts/test_rag.py
  python scripts/test_rag.py --url http://localhost:8000
  python scripts/test_rag.py --cats program,graduation     # 只跑指定類別
  python scripts/test_rag.py --nos 1,3,5                   # 只跑指定題號
  python scripts/test_rag.py --questions scripts/my.txt    # 自訂題目 txt

輸出：
  data/test_results/<timestamp>.json  — 完整結果（含工具細節）
  data/test_results/<timestamp>.md    — 易讀報告（工具呼叫 + 推薦課程 + 回答）
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
RESULTS_DIR = ROOT / "data" / "test_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# 對齊 docs/05-prompt-design/test-questions.md（14 工具版）
DEFAULT_QUESTIONS = [
    # ── 基礎工具覆蓋 ─────────────────────────────────────────────────────────
    ("tech",        "中央大學哪些課程有教 Python？"),
    ("tech",        "有哪些課有教 PyTorch？"),
    ("dept_req",    "大氣科學學系有哪些必修課？"),
    ("dept_elec",   "通識教育中心有哪些選修課可以選？"),
    ("course_det",  "化學學系的普通化學這門課用哪本教科書？"),
    ("course_det",  "統計學這門課在教什麼？"),                    # 消歧義
    ("program",     "永續發展學分學程有哪些課？請介紹一下學程內容。"),
    ("program",     "人工智慧技術應用學程要修哪些課？"),
    ("search_prog", "中央大學有沒有和語言、文化相關的學分學程？"),
    ("graduation",  "中文學系的畢業規定是什麼？需要幾學分？"),
    ("dept_info",   "資訊工程學系適合什麼人讀？"),
    ("teacher",     "哪位教授專長是自然語言處理？"),
    ("teacher",     "中央大學江振瑞教授開了哪些課？"),
    ("tech_dept",   "GIS 是哪些系的課程有教到？"),
    ("similar",     "有沒有和生物統計概念相近的課？不限系所。"),
    ("knowledge",   "「有機化學」這門課在學哪些概念？"),
    ("ppr",         "客家文化連到哪些老師、課程和系所？"),
    # ── 多工具並行 / 串行 ──────────────────────────────────────────────────
    ("multi",       "機器學習在中央大學哪些地方有開課？從課程到系所分布都想了解。"),
    ("multi",       "我對土木工程有興趣，中央大學土木系特色是什麼？有哪些必修課？"),
    ("multi",       "哪些教授在研究地球科學或板塊構造？他們的研究方向是什麼？"),
    ("multi",       "高中學了微積分，大學可以往哪些方向延伸？"),
    ("multi",       "我對生醫相關的跨領域學程有興趣，有哪些可以選？"),
    ("multi",       "外系學生想修機器學習，先修條件是什麼？有替代課程嗎？"),
    ("multi",       "大氣科學系和地球科學系有什麼不同？各有什麼代表課程？"),
    # ── 通識 / 語言 / 非理工 ──────────────────────────────────────────────
    ("general",     "語言中心有沒有日文或西班牙文課？"),
    ("general",     "通識有沒有法律相關的課？"),
    ("general",     "有哪些和環境永續相關的課程，不限系所？"),
    ("general",     "管理學院有哪些和行銷或消費者行為相關的課？"),
    # ── 工具選用壓力測試 ──────────────────────────────────────────────────
    ("pressure",    "外系學生可以修客語教學相關的課嗎？"),
    ("pressure",    "土木工程學系要畢業需要修幾學分？有哪些認證要求？"),
    # ── Fallback ──────────────────────────────────────────────────────────
    ("fallback",    "有沒有和「全球環境變遷」概念最相近的課程？"),
    ("fallback",    "中央大學有沒有「區塊鏈與 Web3 應用」這門課？"),
    ("fallback",    "中央大學有沒有跨文化溝通相關的課程？"),
    # ── 高複雜度 ──────────────────────────────────────────────────────────
    ("complex",     "我高中讀社會組，對資料分析有興趣，有不需要強程式基礎的課程或學程嗎？"),
    ("complex",     "我高中很喜歡化學，中央大學哪些系所和課程跟化學有關？"),
    ("complex",     "我想同時了解土木工程和環境工程，有哪些課程和學程可以搭配規劃？"),
]

CAT_LABELS = {
    "tech":        "技術找課",
    "dept_req":    "系所必修",
    "dept_elec":   "系所選修",
    "course_det":  "課程詳情",
    "program":     "學程查詢",
    "search_prog": "學程搜尋",
    "graduation":  "畢業規定",
    "dept_info":   "系所介紹",
    "teacher":     "教師查詢",
    "tech_dept":   "技術系所分布",
    "similar":     "相似課推薦",
    "knowledge":   "知識地圖",
    "ppr":         "PPR 探索",
    "multi":       "多工具",
    "general":     "通識/語言",
    "pressure":    "工具選用壓測",
    "fallback":    "Fallback",
    "complex":     "高複雜度",
}


def ask_stream(base_url: str, question: str) -> dict:
    """呼叫 /api/chat/stream，解析 SSE 事件，回傳完整結果（含工具呼叫細節）。"""
    try:
        resp = requests.post(
            f"{base_url}/api/chat/stream",
            json={"question": question},
            timeout=120,
            stream=True,
        )
        resp.raise_for_status()

        answer_parts: list[str] = []
        done_data: dict = {}

        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line or not raw_line.startswith("data: "):
                continue
            try:
                data = json.loads(raw_line[6:])
            except Exception:
                continue

            t = data.get("type")
            if t == "token":
                answer_parts.append(data.get("text", ""))
            elif t == "done":
                done_data = data

        answer = "".join(answer_parts)
        trace_calls = done_data.get("debug_trace", {}).get("toolCalls", [])

        return {
            "answer":            answer,
            "tools_used":        done_data.get("tools_used", []),
            "course_cards":      done_data.get("course_cards", []),
            "course_pool_count": done_data.get("course_pool_count", 0),
            "has_large_result":  done_data.get("has_large_result", False),
            "input_tokens":      done_data.get("input_tokens", 0),
            "output_tokens":     done_data.get("output_tokens", 0),
            # 每個工具呼叫的細節：{tool, args, coursesFound, count, scores, scoreType}
            "tool_calls":        trace_calls,
        }
    except requests.exceptions.Timeout:
        return {"error": "timeout",   "answer": "", "tools_used": [], "course_cards": [], "tool_calls": []}
    except Exception as e:
        return {"error": str(e),      "answer": "", "tools_used": [], "course_cards": [], "tool_calls": []}


def run_tests(base_url: str, questions: list[tuple[str, str]]) -> list[dict]:
    results = []
    total = len(questions)
    for i, (category, q) in enumerate(questions, 1):
        label = CAT_LABELS.get(category, category)
        print(f"[{i:02d}/{total}] [{label}] {q}")
        t0 = time.time()
        resp = ask_stream(base_url, q)
        elapsed = round(time.time() - t0, 2)

        record = {
            "no":            i,
            "category":      category,
            "question":      q,
            "answer":        resp.get("answer", ""),
            "tools_used":    resp.get("tools_used", []),
            "tool_calls":    resp.get("tool_calls", []),
            "course_cards":  resp.get("course_cards", []),
            "course_pool_count": resp.get("course_pool_count", 0),
            "has_large_result":  resp.get("has_large_result", False),
            "input_tokens":  resp.get("input_tokens", 0),
            "output_tokens": resp.get("output_tokens", 0),
            "elapsed_sec":   elapsed,
            "error":         resp.get("error", ""),
        }
        results.append(record)

        status = "❌" if record["error"] else "✅"
        tools_str = ", ".join(record["tools_used"]) if record["tools_used"] else "—"
        cards_n = len(record["course_cards"])
        print(f"  {status} {elapsed}s | tools: {tools_str} | cards: {cards_n}")
        print()

    return results


def _fmt_args(args: dict) -> str:
    s = json.dumps(args, ensure_ascii=False)
    return s[:120] + "…" if len(s) > 120 else s


def save_json(results: list[dict], path: Path) -> None:
    path.write_text(
        json.dumps({"results": results, "total": len(results)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_markdown(results: list[dict], path: Path) -> None:
    lines = ["# RAG 測試報告\n\n"]
    lines.append(f"> 執行時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}  \n")
    lines.append(f"> 題目數：{len(results)}  \n\n---\n")

    current_cat = None
    for r in results:
        if r["category"] != current_cat:
            current_cat = r["category"]
            label = CAT_LABELS.get(current_cat, current_cat)
            lines.append(f"\n## {label}\n")

        status = "❌" if r["error"] else "✅"
        cards = r.get("course_cards", [])
        tcs   = r.get("tool_calls", [])

        lines.append(f"### {status} Q{r['no']}：{r['question']}\n\n")
        lines.append(f"**耗時：** {r['elapsed_sec']}s　"
                     f"**in/out tokens：** {r.get('input_tokens',0)}/{r.get('output_tokens',0)}　"
                     f"**Cards：** {len(cards)}　**Pool：** {r.get('course_pool_count',0)}  \n\n")

        if r["error"]:
            lines.append(f"**錯誤：** {r['error']}\n\n")
            continue

        # ── 工具呼叫明細 ────────────────────────────────────────────────────
        if tcs:
            lines.append("**工具呼叫：**\n\n")
            lines.append("| # | 工具 | 參數 | 回傳 | 範例課程 |\n")
            lines.append("|---|------|------|------|---------|\n")
            for j, tc in enumerate(tcs, 1):
                tool      = tc.get("tool", "?")
                args_str  = _fmt_args(tc.get("args", {}))
                count     = tc.get("count")
                sc_type   = tc.get("scoreType") or ""
                count_str = f"{count} 筆" if count is not None else "—"
                if sc_type:
                    count_str += f"（{sc_type}）"
                courses   = tc.get("coursesFound", [])[:4]
                scores    = tc.get("scores", [])
                course_parts = []
                for k, c in enumerate(courses):
                    sc = f"[{scores[k]:.2f}]" if k < len(scores) and scores[k] else ""
                    course_parts.append(f"{c} {sc}".strip())
                course_str = "、".join(course_parts) if course_parts else "—"
                lines.append(f"| {j} | `{tool}` | `{args_str}` | {count_str} | {course_str} |\n")
            lines.append("\n")

        # ── 推薦課程卡片 ────────────────────────────────────────────────────
        if cards:
            lines.append(f"**推薦課程（{len(cards)} 門）：**\n\n")
            for c in cards:
                name    = c.get("name", "?")
                dept    = c.get("dept", "")
                credits = c.get("credits") or ""
                ctype   = c.get("type", "")
                teacher = c.get("teacher", "")
                meta    = "　".join(filter(None, [dept, f"{credits}學分" if credits else "", ctype, teacher]))
                lines.append(f"- **{name}**　{meta}\n")
            lines.append("\n")
        else:
            lines.append("**推薦課程：** 無課程卡片（非課程類回答）  \n\n")

        # ── 完整回答 ────────────────────────────────────────────────────────
        answer_quoted = r["answer"].replace("\n", "\n> ")
        lines.append(f"**回答：**\n> {answer_quoted}\n\n---\n")

    path.write_text("".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="NCU RAG 自動測試工具")
    parser.add_argument("--url",       default="http://localhost:8000", help="API base URL")
    parser.add_argument("--questions", default=None, help="每行一題的 txt 檔（不填則用內建題目）")
    parser.add_argument("--nos",  default=None, help="只跑指定題號，逗號分隔，例如 --nos 1,3,5")
    parser.add_argument("--cats", default=None, help="只跑指定類別，逗號分隔，例如 --cats program,graduation")
    args = parser.parse_args()

    questions = DEFAULT_QUESTIONS
    if args.questions:
        txt = Path(args.questions).read_text(encoding="utf-8")
        questions = [("custom", line.strip()) for line in txt.splitlines()
                     if line.strip() and not line.startswith("#")]

    if args.nos:
        nos = {int(x.strip()) for x in args.nos.split(",")}
        questions = [(cat, q) for i, (cat, q) in enumerate(questions, 1) if i in nos]

    if args.cats:
        cats = {c.strip() for c in args.cats.split(",")}
        questions = [(cat, q) for cat, q in questions if cat in cats]

    print(f"目標：{args.url}")
    print(f"題數：{len(questions)}\n")

    results = run_tests(args.url, questions)

    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = RESULTS_DIR / f"{ts}.json"
    md_path   = RESULTS_DIR / f"{ts}.md"

    save_json(results, json_path)
    save_markdown(results, md_path)

    errors   = sum(1 for r in results if r["error"])
    avg_time = round(sum(r["elapsed_sec"] for r in results) / len(results), 2)
    print(f"\n完成｜成功：{len(results) - errors}/{len(results)}｜平均耗時：{avg_time}s")
    print(f"JSON：{json_path}")
    print(f"報告：{md_path}")


if __name__ == "__main__":
    main()
