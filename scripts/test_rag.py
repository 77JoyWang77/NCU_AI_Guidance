"""
test_rag.py

自動測試 /api/chat，將每題的回答、工具呼叫、來源記錄成 JSON。

執行方式：
  python scripts/test_rag.py
  python scripts/test_rag.py --url http://localhost:8000  # 自訂 base URL
  python scripts/test_rag.py --questions scripts/test_questions.txt  # 自訂題目

輸出：
  data/test_results/<timestamp>.json  — 完整結果
  data/test_results/<timestamp>.md    — 易讀 markdown 報告
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
RESULTS_DIR = ROOT / "data" / "test_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_QUESTIONS = [
    # 語意搜尋
    ("semantic",    "有什麼和機器學習相關的課？"),
    ("semantic",    "我想學網頁開發，有哪些課可以選？"),
    ("semantic",    "有沒有教資料視覺化的課？"),
    # 技術找課
    ("tech_filter", "有哪些課會教 PyTorch？"),
    ("tech_filter", "哪些課用到 Python？"),
    # 系所必修/選修
    ("dept_req",    "資訊工程學系必修有哪些？"),
    ("dept_elv",    "資工系有哪些選修課？"),
    # 年次規劃
    ("schedule",    "大一上有哪些課？"),
    ("schedule",    "大二下有什麼必修？"),
    # 學分學程
    ("program",     "人工智慧技術應用學程要修哪些課？"),
    ("program",     "有哪些學程和資安有關？"),
    # 教師
    ("teacher",     "哪位教授專長是自然語言處理？"),
    ("teacher",     "資工系有哪些專任教授？"),
    # 系所介紹
    ("dept_info",   "資訊工程學系在學什麼？適合什麼人？"),
    ("dept_info",   "電機系和資工系有什麼差別？"),
    # 畢業規定
    ("graduation",  "資訊工程學系要幾學分才能畢業？"),
    ("graduation",  "資工系有哪些畢業規定？"),
    # 先修
    ("prereq",      "修機器學習要先修什麼？"),
    ("prereq",      "資料結構有哪些先修課？"),
    # 修課資格
    ("eligibility", "大一可以修哪些課？"),
    ("eligibility", "演算法這門課外系可以選嗎？"),
    # 複合查詢
    ("compound",    "資工系大一必修中，有哪些課和程式設計相關？"),
    ("compound",    "我是資工系大二，下學期有哪些必修要修？"),
    ("compound",    "人工智慧學程的課裡，有沒有教 Python 的？"),
    ("compound",    "修深度學習之前，我大一大二應該先修哪些課？"),
]


def ask(base_url: str, question: str, session_id: str = None) -> dict:
    payload = {"question": question}
    if session_id:
        payload["session_id"] = session_id
    try:
        resp = requests.post(f"{base_url}/api/chat", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        return {"error": "timeout", "answer": "", "tools_used": [], "sources": []}
    except Exception as e:
        return {"error": str(e), "answer": "", "tools_used": [], "sources": []}


def run_tests(base_url: str, questions: list[tuple[str, str]]) -> list[dict]:
    results = []
    total = len(questions)
    for i, (category, q) in enumerate(questions, 1):
        print(f"[{i:02d}/{total}] {category}: {q}")
        t0 = time.time()
        resp = ask(base_url, q)
        elapsed = round(time.time() - t0, 2)

        record = {
            "no":          i,
            "category":    category,
            "question":    q,
            "answer":      resp.get("answer", ""),
            "tools_used":  resp.get("tools_used", []),
            "sources":     resp.get("sources", []),
            "session_id":  resp.get("session_id", ""),
            "input_tokens":  resp.get("input_tokens", 0),
            "output_tokens": resp.get("output_tokens", 0),
            "elapsed_sec": elapsed,
            "error":       resp.get("error", ""),
        }
        results.append(record)

        status = "❌" if record["error"] else "✅"
        tools_str = ", ".join(record["tools_used"]) if record["tools_used"] else "—"
        print(f"  {status} {elapsed}s | tools: {tools_str}")
        print()

    return results


def save_json(results: list[dict], path: Path) -> None:
    path.write_text(
        json.dumps({"results": results, "total": len(results)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_markdown(results: list[dict], path: Path) -> None:
    lines = ["# RAG 測試報告\n"]
    lines.append(f"> 執行時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    lines.append(f"> 題目數：{len(results)}\n\n---\n")

    current_cat = None
    cat_labels = {
        "semantic": "語意搜尋", "tech_filter": "技術找課",
        "dept_req": "系所必修", "dept_elv": "系所選修",
        "schedule": "年次規劃", "program": "學分學程",
        "teacher": "教師查詢", "dept_info": "系所介紹",
        "graduation": "畢業規定", "prereq": "先修查詢",
        "eligibility": "修課資格", "compound": "複合查詢",
    }

    for r in results:
        if r["category"] != current_cat:
            current_cat = r["category"]
            label = cat_labels.get(current_cat, current_cat)
            lines.append(f"\n## {label}\n")

        status = "❌" if r["error"] else "✅"
        tools = ", ".join(r["tools_used"]) if r["tools_used"] else "—"
        lines.append(f"### {status} Q{r['no']}：{r['question']}\n")
        lines.append(f"**工具：** `{tools}`  \n")
        lines.append(f"**耗時：** {r['elapsed_sec']}s  \n")
        if r["error"]:
            lines.append(f"**錯誤：** {r['error']}\n\n")
        else:
            answer = r["answer"].replace("\n", "\n> ")
            lines.append(f"**回答：**\n> {answer}\n\n")

    path.write_text("".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--questions", default=None, help="每行一題的 txt 檔（不填則用內建題目）")
    args = parser.parse_args()

    questions = DEFAULT_QUESTIONS
    if args.questions:
        txt = Path(args.questions).read_text(encoding="utf-8")
        questions = [("custom", line.strip()) for line in txt.splitlines() if line.strip()]

    print(f"目標：{args.url}")
    print(f"題數：{len(questions)}\n")

    results = run_tests(args.url, questions)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = RESULTS_DIR / f"{ts}.json"
    md_path   = RESULTS_DIR / f"{ts}.md"

    save_json(results, json_path)
    save_markdown(results, md_path)

    errors = sum(1 for r in results if r["error"])
    avg_time = round(sum(r["elapsed_sec"] for r in results) / len(results), 2)
    print(f"完成｜成功：{len(results) - errors}/{len(results)}｜平均耗時：{avg_time}s")
    print(f"JSON：{json_path}")
    print(f"報告：{md_path}")


if __name__ == "__main__":
    main()
