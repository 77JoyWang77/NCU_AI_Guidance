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

# 測試題目版本：v5（2026-05-09）
# 調整方向：縮減資工/理工題數，擴充人文/語言、經濟金融、社科/客家、通識（加量）、學程介紹、系所側寫
DEFAULT_QUESTIONS = [
    # ── P0 修正回歸 ────────────────────────────────────────────────────────
    ("regression",  "人工智慧技術應用學程要修哪些課？"),
    ("regression",  "GIS 是哪些系的課程有教到？"),
    ("regression",  "地科系有哪些課程可以選？"),
    ("regression",  "資工系有哪些必修課？"),

    # ── 系所別名 ──────────────────────────────────────────────────────────
    ("alias",       "大氣系的畢業規定是什麼？"),
    ("alias",       "化材系在教哪些課程？"),
    ("alias",       "資管系的系所介紹是什麼？"),

    # ── 修課資格 ──────────────────────────────────────────────────────────
    ("eligibility", "外系學生可以修客語教學這門課嗎？有沒有什麼限制？"),
    ("eligibility", "大一新生可以修資料結構嗎？修課資格是什麼？"),
    ("eligibility", "外系生可以修機率與統計嗎？先修條件是什麼？"),

    # ── 人文 / 語言系所 ────────────────────────────────────────────────────
    ("humanities",  "中國文學學系有哪些必修課？"),
    ("humanities",  "英美語文學系適合什麼人讀？有什麼特色課程？"),
    ("humanities",  "中央大學有法語課程嗎？語言中心或系所都算。"),
    ("humanities",  "通識有沒有哲學或倫理學相關的課程？"),
    ("humanities",  "歷史研究所有什麼特色，和其他人文系所有何不同？"),

    # ── 經濟 / 財務 / 管理 ────────────────────────────────────────────────
    ("econ_fin",    "經濟學系有哪些必修課？"),
    ("econ_fin",    "財務金融學系適合什麼人讀？主要培養哪些能力？"),
    ("econ_fin",    "中央大學有沒有投資或股票相關的課程？"),
    ("econ_fin",    "管理學院有哪些學分學程？"),
    ("econ_fin",    "企業管理學系畢業需要幾學分？有哪些必修課？"),

    # ── 社會科學 / 客家 ───────────────────────────────────────────────────
    ("social_sci",  "客家語文學系有哪些必修課？"),
    ("social_sci",  "客家文化連到哪些老師、課程和系所？"),
    ("social_sci",  "法律與政府研究所的課程方向是什麼？"),
    ("social_sci",  "通識有沒有和性別、族群或社會議題相關的課？"),

    # ── 生醫 / 生命科學 ───────────────────────────────────────────────────
    ("life_sci",    "生物醫學工程學系有哪些必修課？"),
    ("life_sci",    "生命科學學系主要在研究什麼？適合什麼背景的人？"),
    ("life_sci",    "有哪些課程和分子生物學或基因體學相關？"),

    # ── 自然科學 / 數學 ───────────────────────────────────────────────────
    ("natural_sci", "物理學系有哪些必修課？"),
    ("natural_sci", "數學學系的課程以哪些領域為主？"),
    ("natural_sci", "中央大學有沒有統計或數據科學相關的系所和課程？"),

    # ── 通識 ──────────────────────────────────────────────────────────────
    ("general",     "語言中心有沒有日文或西班牙文課？"),
    ("general",     "通識有沒有法律相關的課？"),
    ("general",     "有哪些和環境永續相關的課程，不限系所？"),
    ("general_adv", "通識有沒有藝術欣賞或音樂相關的課程？"),
    ("general_adv", "通識裡有哪些課程和法律、公民社會相關？"),
    ("general_adv", "通識有沒有和科技倫理、數位社會或 AI 影響相關的課？"),
    ("general_adv", "通識裡有沒有介紹台灣歷史或文化的課？"),

    # ── 學分學程 ──────────────────────────────────────────────────────────
    ("program",     "永續發展學分學程有哪些課？請介紹一下學程內容。"),
    ("program",     "中央大學有沒有和語言、文化相關的學分學程？"),
    ("program",     "財務工程學分學程要修哪些課？"),

    # ── 系所介紹 / 知識側寫 ───────────────────────────────────────────────
    ("dept_info",   "資訊工程學系適合什麼人讀？"),
    ("dept_info",   "地球科學學系的課程以哪些領域為主？"),
    ("dept_info",   "大氣科學學系適合對什麼感興趣的學生？"),

    # ── 基礎工具覆蓋 ──────────────────────────────────────────────────────
    ("tech",        "中央大學哪些課程有教 Python？"),
    ("dept_req",    "大氣科學學系有哪些必修課？"),
    ("dept_elec",   "通識教育中心有哪些選修課可以選？"),
    ("course_det",  "統計學這門課在教什麼？"),
    ("graduation",  "中文學系的畢業規定是什麼？需要幾學分？"),
    ("teacher",     "哪位教授專長是自然語言處理？"),
    ("teacher",     "中央大學江振瑞教授開了哪些課？"),
    ("similar",     "有沒有和生物統計概念相近的課？不限系所。"),

    # ── PPR overview ──────────────────────────────────────────────────────
    ("ppr_overview","AI 在中央大學有哪些相關課程、教授和系所？給我一個全貌。"),
    ("ppr_overview","影像處理和電腦視覺在中央大學連結到哪些課程、教師和系所？"),

    # ── 系所比較 ──────────────────────────────────────────────────────────
    ("dept_compare","大氣科學系和地球科學系有什麼不同？各有什麼代表課程？"),
    ("dept_compare","資訊工程學系和電機工程學系的課程方向有什麼差異？"),
    ("dept_compare","財務金融學系和經濟學系有什麼不同？適合不同興趣的人嗎？"),
    ("dept_compare","生命科學學系和生物醫學工程學系分別在學什麼？有何差異？"),

    # ── 多工具 ────────────────────────────────────────────────────────────
    ("multi",       "我對土木工程有興趣，中央大學土木系特色是什麼？有哪些必修課？"),
    ("multi",       "我高中讀社會組，對資料分析有興趣，有不需要強程式基礎的課程或學程嗎？"),

    # ── Fallback ──────────────────────────────────────────────────────────
    ("fallback",    "有沒有和「全球環境變遷」概念最相近的課程？"),
    ("fallback",    "中央大學有沒有「區塊鏈與 Web3 應用」這門課？"),
    ("fallback_name","「深度學習概論」這門課的先修條件是什麼？"),
    ("fallback_name","「機率統計」這門課外系可以修嗎？修課資格是什麼？"),

    # ── 語意豐富化 ────────────────────────────────────────────────────────
    ("enrich",      "有哪些課程有教 Docker 或容器化技術？這些課主要在學什麼概念？"),

    # ── 分班去重 ──────────────────────────────────────────────────────────
    ("dedup",       "數學學系有哪些必修課？同一門課有幾個班？"),

    # ── 學士班 ────────────────────────────────────────────────────────────
    ("special_prog","管理學院學士班是什麼？和一般管理系所有什麼不同？"),
    ("special_prog","中央大學有哪些跨領域的學院學士班或整合型學位學程？"),

    # ── v4 回歸 ───────────────────────────────────────────────────────────
    ("v4_regression", "總體經濟學有開課嗎？"),
    ("v4_regression", "自然語言處理這門課是什麼系開的？"),
    ("v4_regression", "張家凱老師開了哪些課？"),
    ("v4_regression", "投資學這門課在哪些系有開？"),
]

CAT_LABELS = {
    "regression":    "P0 回歸測試",
    "alias":         "系所別名",
    "eligibility":   "修課資格",
    "humanities":    "人文/語言系所",
    "econ_fin":      "經濟/財務/管理",
    "social_sci":    "社科/客家",
    "life_sci":      "生醫/生命科學",
    "natural_sci":   "自然科學/數學",
    "general":       "通識/語言",
    "general_adv":   "通識進階",
    "program":       "學分學程",
    "dept_info":     "系所介紹/側寫",
    "tech":          "技術找課",
    "dept_req":      "系所必修",
    "dept_elec":     "系所選修",
    "course_det":    "課程詳情",
    "graduation":    "畢業規定",
    "teacher":       "教師查詢",
    "similar":       "相似課推薦",
    "ppr_overview":  "PPR Overview 模式",
    "dept_compare":  "系所比較",
    "multi":         "多工具",
    "fallback":      "Fallback",
    "fallback_name": "課程名稱 Fallback",
    "enrich":        "語意豐富化欄位",
    "dedup":         "分班去重",
    "special_prog":  "學士班/特殊班制",
    "v4_regression": "v4 修正回歸",
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
    lines.append(f"> 版本：v5（2026-05-09）  \n")
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
