"""
test_depts_by_tech.py

專門測試 get_depts_by_tech 工具。
題目設計涵蓋：
  - 主流/熱門技術詞（Python、機器學習、GIS）
  - 英文/縮寫別名（GIS、SQL、fMRI）
  - 高中生問法（「哪個科系要學 X」）
  - 跨院概念（感測器、全球定位系統）
  - 必修 vs 選修區分（「哪些系是必修 X」）
  - 冷門稀疏技術（可能 0 筆，測試 fallback）
  - 語意相近但非精確命中（測試 score < 1.0 節點）
  - 反問型（「讀哪個系才能學到 X」）

執行方式：
  python scripts/test_depts_by_tech.py
  python scripts/test_depts_by_tech.py --url http://localhost:8000
  python scripts/test_depts_by_tech.py --cats exact,alias   # 只跑指定類別
  python scripts/test_depts_by_tech.py --nos 1,5,10         # 指定題號

輸出：
  data/test_results/<timestamp>_depts_by_tech.json
  data/test_results/<timestamp>_depts_by_tech.md
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT        = Path(__file__).parent.parent
RESULTS_DIR = ROOT / "data" / "test_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── 測試題目 ──────────────────────────────────────────────────────────────────
# 格式：(category, question)

QUESTIONS = [

    # ═══════════════════════════════════════════════════════════════════════
    # 精確命中：熱門/主流技術（預期 score=精確比對，多個系所）
    # ═══════════════════════════════════════════════════════════════════════
    ("exact", "哪些科系的課程有教 Python？"),
    ("exact", "中央大學哪些系所有在教機器學習？"),
    ("exact", "哪些系有開深度學習相關課程？"),
    ("exact", "哪些系所的課程會用到 PyTorch？"),
    ("exact", "GIS 地理資訊系統有哪些系所的課程在教？"),
    ("exact", "感測器相關課程在哪些系所有教？必修還是選修？"),
    ("exact", "哪些科系有必修的統計學課程？"),
    ("exact", "哪些系所的課有用到資料庫系統？"),

    # ═══════════════════════════════════════════════════════════════════════
    # 別名 / 英文縮寫（測試語意搜尋能否接受不同說法）
    # ═══════════════════════════════════════════════════════════════════════
    ("alias", "SQL 在哪些系有被教到？"),
    ("alias", "fMRI 腦影像分析在哪些科系的課程有用到？"),
    ("alias", "哪些系所的課程有教 Arduino 或微控制器？"),
    ("alias", "Matlab 或 MATLAB 在哪些系有開課？"),
    ("alias", "R 語言在哪些系有被教到？"),
    ("alias", "人工智慧（AI）有哪些科系把它列為必修或重要課程？"),

    # ═══════════════════════════════════════════════════════════════════════
    # 高中生問法（反問型：讀哪個系才能學到 X）
    # ═══════════════════════════════════════════════════════════════════════
    ("highschool", "我想學量子力學，讀哪個系比較有可能接觸到？"),
    ("highschool", "如果我對影像處理有興趣，哪個科系的課程最多？"),
    ("highschool", "我對語音辨識和自然語言處理有興趣，應該讀哪個系？"),
    ("highschool", "哪個科系最需要學微積分？是哪些課列為必修的？"),
    ("highschool", "我對基因體學或 DNA 定序有興趣，讀哪個系可以接觸到？"),
    ("highschool", "想學財務工程，哪些系所有相關課程？"),

    # ═══════════════════════════════════════════════════════════════════════
    # 必修 vs 選修明確區分（使用者想知道「哪些系列為必修」）
    # ═══════════════════════════════════════════════════════════════════════
    ("req_elec", "哪些系所把 C 語言或 C++ 列為必修？"),
    ("req_elec", "線性代數在哪些系是必修課？"),
    ("req_elec", "哪些系所的課程把訊號處理列為必修？"),
    ("req_elec", "時間序列分析在哪些系有教？是必修還是選修？"),

    # ═══════════════════════════════════════════════════════════════════════
    # 跨院/廣泛概念（預期多個系所，含理工、管理、社科）
    # ═══════════════════════════════════════════════════════════════════════
    ("cross_domain", "哪些系所的課程有涉及永續發展或碳排放？"),
    ("cross_domain", "物聯網（IoT）相關課程在哪些系有開？"),
    ("cross_domain", "哪些科系有用到遙測或衛星影像的課程？"),
    ("cross_domain", "資料視覺化在哪些系所的課程中有教到？"),
    ("cross_domain", "哪些系的課程有討論到區塊鏈或分散式帳本技術？"),

    # ═══════════════════════════════════════════════════════════════════════
    # 冷門 / 稀疏技術（可能 0 筆或語意命中，測試 fallback 品質）
    # ═══════════════════════════════════════════════════════════════════════
    ("sparse", "Rust 語言有哪些系所在教？"),
    ("sparse", "量子密碼學或量子通訊在哪些系有課？"),
    ("sparse", "哪些系所有在教 Kubernetes 或 Docker 容器技術？"),
    ("sparse", "腦機介面（BCI）相關課程在哪個系有？"),
    ("sparse", "哪些系所有教到 WebAssembly 或前端框架？"),

    # ═══════════════════════════════════════════════════════════════════════
    # 多技術組合（使用者一次問兩個技術，考驗 LLM 是否各別查詢）
    # ═══════════════════════════════════════════════════════════════════════
    ("multi_tech", "哪些系的課同時涵蓋機器學習和生物資訊學？"),
    ("multi_tech", "電磁學和天線設計相關課程在哪些系所有開？"),
    ("multi_tech", "哪些科系有教到財務模型和 VBA 或 Excel 試算表工具？"),
]

# ── 類別說明 ──────────────────────────────────────────────────────────────────
CAT_LABELS = {
    "exact":        "精確命中（熱門技術）",
    "alias":        "別名/英文縮寫",
    "highschool":   "高中生反問型",
    "req_elec":     "必修 vs 選修區分",
    "cross_domain": "跨院廣泛概念",
    "sparse":       "冷門/稀疏技術",
    "multi_tech":   "多技術組合",
}

TARGET_TOOL = "get_depts_by_tech"


# ── API 呼叫 ──────────────────────────────────────────────────────────────────
def ask_stream(base_url: str, question: str) -> dict:
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
        tool_results: list[dict] = []   # 捕捉 tool_result 事件

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
            elif t == "tool_result":
                tool_results.append({
                    "tool":   data.get("tool", ""),
                    "result": data.get("result", ""),
                })

        return {
            "answer":            "".join(answer_parts),
            "tools_used":        done_data.get("tools_used", []),
            "course_cards":      done_data.get("course_cards", []),
            "course_pool_count": done_data.get("course_pool_count", 0),
            "input_tokens":      done_data.get("input_tokens", 0),
            "output_tokens":     done_data.get("output_tokens", 0),
            "tool_calls":        done_data.get("debug_trace", {}).get("toolCalls", []),
            "tool_results":      tool_results,
        }
    except requests.exceptions.Timeout:
        return {"error": "timeout", "answer": "", "tools_used": [], "course_cards": [], "tool_calls": [], "tool_results": []}
    except Exception as e:
        return {"error": str(e), "answer": "", "tools_used": [], "course_cards": [], "tool_calls": [], "tool_results": []}


# ── 測試執行 ──────────────────────────────────────────────────────────────────
def run_tests(base_url: str, questions: list[tuple]) -> list[dict]:
    results = []
    total = len(questions)
    for i, (cat, q) in enumerate(questions, 1):
        label = CAT_LABELS.get(cat, cat)
        print(f"[{i:02d}/{total}] [{label}] {q}")
        t0 = time.time()
        resp = ask_stream(base_url, q)
        elapsed = round(time.time() - t0, 2)

        record = {
            "no":            i,
            "category":      cat,
            "question":      q,
            "answer":        resp.get("answer", ""),
            "tools_used":    resp.get("tools_used", []),
            "tool_calls":    resp.get("tool_calls", []),
            "tool_results":  resp.get("tool_results", []),
            "course_cards":  resp.get("course_cards", []),
            "course_pool_count": resp.get("course_pool_count", 0),
            "input_tokens":  resp.get("input_tokens", 0),
            "output_tokens": resp.get("output_tokens", 0),
            "elapsed_sec":   elapsed,
            "error":         resp.get("error", ""),
        }
        results.append(record)

        status    = "❌" if record["error"] else "✅"
        tools_str = ", ".join(record["tools_used"]) if record["tools_used"] else "—"
        cards_n   = len(record["course_cards"])
        hit = any(TARGET_TOOL in t for t in record["tools_used"])
        hit_mark = "✓" if hit else "△"
        print(f"  {status} {elapsed}s | {hit_mark} tools: {tools_str} | cards: {cards_n}")
        print()

    return results


# ── 格式化輸出 ────────────────────────────────────────────────────────────────
def _fmt_args(args: dict) -> str:
    s = json.dumps(args, ensure_ascii=False)
    return s[:160] + "…" if len(s) > 160 else s


def save_json(results: list[dict], path: Path) -> None:
    path.write_text(
        json.dumps({"results": results, "total": len(results)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_markdown(results: list[dict], path: Path) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 計算命中率（按類別）
    cat_stats: dict[str, dict] = {}
    for r in results:
        c = r["category"]
        if c not in cat_stats:
            cat_stats[c] = {"total": 0, "hit": 0, "errors": 0}
        cat_stats[c]["total"] += 1
        if r["error"]:
            cat_stats[c]["errors"] += 1
        if any(TARGET_TOOL in t for t in r.get("tools_used", [])):
            cat_stats[c]["hit"] += 1

    overall_hit = sum(s["hit"] for s in cat_stats.values())
    overall_total = sum(s["total"] for s in cat_stats.values())

    lines = [f"# get_depts_by_tech 測試報告\n\n"]
    lines.append(f"> 執行時間：{now}  \n")
    lines.append(f"> 總題數：{len(results)}　工具命中：{overall_hit}/{overall_total}  \n\n")

    # 摘要
    lines.append("## 摘要（按類別）\n\n")
    lines.append("| 類別 | 題數 | 工具命中 | 錯誤 |\n")
    lines.append("|------|------|---------|------|\n")
    for c, s in cat_stats.items():
        label = CAT_LABELS.get(c, c)
        lines.append(f"| {label} | {s['total']} | {s['hit']}/{s['total']} | {s['errors']} |\n")
    lines.append("\n---\n")

    # 詳細結果
    current_cat = None
    for r in results:
        if r["category"] != current_cat:
            current_cat = r["category"]
            lines.append(f"\n## {CAT_LABELS.get(current_cat, current_cat)}\n")

        status   = "❌" if r["error"] else "✅"
        cards    = r.get("course_cards", [])
        tcs      = r.get("tool_calls", [])
        hit      = any(TARGET_TOOL in t for t in r.get("tools_used", []))
        hit_badge = "✓" if hit else "△"

        lines.append(f"\n### {status} Q{r['no']}：{r['question']}\n\n")
        lines.append(
            f"**耗時：** {r['elapsed_sec']}s　"
            f"**in/out tokens：** {r.get('input_tokens',0)}/{r.get('output_tokens',0)}　"
            f"**Cards：** {len(cards)}　"
            f"**目標工具命中：** {hit_badge}  \n\n"
        )

        if r["error"]:
            lines.append(f"**錯誤：** {r['error']}\n\n")
            continue

        # 工具呼叫明細
        if tcs:
            lines.append("**工具呼叫：**\n\n")
            lines.append("| # | 工具 | 參數 | 回傳 | 前幾筆課程/節點 |\n")
            lines.append("|---|------|------|------|---------------|\n")
            for j, tc in enumerate(tcs, 1):
                tool      = tc.get("tool", "?")
                args_str  = _fmt_args(tc.get("args", {}))
                count     = tc.get("count")
                sc_type   = tc.get("scoreType") or ""
                count_str = (f"{count} 筆" if count is not None else "—") + (f"（{sc_type}）" if sc_type else "")
                courses   = tc.get("coursesFound", [])[:4]
                scores    = tc.get("scores", [])
                course_parts = []
                for k, c in enumerate(courses):
                    sc = f"[{scores[k]:.2f}]" if k < len(scores) and scores[k] else ""
                    course_parts.append(f"{c} {sc}".strip())
                course_str = "、".join(course_parts) if course_parts else "—"
                lines.append(f"| {j} | `{tool}` | `{args_str}` | {count_str} | {course_str} |\n")
            lines.append("\n")

        # 推薦課程卡片
        if cards:
            lines.append(f"**推薦課程（{len(cards)} 門）：**\n\n")
            for c in cards:
                name    = c.get("name", "?")
                dept    = c.get("dept", "")
                credits = c.get("credits") or ""
                ctype   = c.get("type", "")
                meta    = "　".join(filter(None, [dept, f"{credits}學分" if credits else "", ctype]))
                lines.append(f"- **{name}**　{meta}\n")
            lines.append("\n")
        else:
            lines.append("**推薦課程：** 無課程卡片（回答為系所資訊或查無結果）  \n\n")

        # 工具回傳內容（get_depts_by_tech 原始文字）
        tool_results = r.get("tool_results", [])
        dbt_results = [tr for tr in tool_results if tr.get("tool") == TARGET_TOOL]
        if dbt_results:
            lines.append("**工具回傳（get_depts_by_tech 前 600 字）：**\n\n")
            for tr in dbt_results:
                preview = tr.get("result", "")[:600]
                lines.append(f"```\n{preview}\n```\n\n")

        # 完整回答
        answer_quoted = r["answer"].replace("\n", "\n> ")
        lines.append(f"**回答：**\n> {answer_quoted}\n\n---\n")

    path.write_text("".join(lines), encoding="utf-8")


# ── 主流程 ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="get_depts_by_tech 工具測試")
    parser.add_argument("--url",  default="http://localhost:8000", help="API base URL")
    parser.add_argument("--cats", default=None,
                        help="只跑指定類別，逗號分隔：exact, alias, highschool, req_elec, cross_domain, sparse, multi_tech")
    parser.add_argument("--nos",  default=None, help="只跑指定題號，逗號分隔，例如 --nos 1,3,5")
    args = parser.parse_args()

    questions = list(QUESTIONS)

    if args.cats:
        allowed = {c.strip() for c in args.cats.split(",")}
        questions = [q for q in questions if q[0] in allowed]

    if args.nos:
        nos = {int(x.strip()) for x in args.nos.split(",")}
        questions = [q for i, q in enumerate(QUESTIONS, 1) if i in nos]

    print(f"目標：{args.url}")
    print(f"題數：{len(questions)}\n")

    results = run_tests(args.url, questions)

    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_out = RESULTS_DIR / f"{ts}_depts_by_tech.json"
    md_out   = RESULTS_DIR / f"{ts}_depts_by_tech.md"

    save_json(results, json_out)
    save_markdown(results, md_out)

    errors   = sum(1 for r in results if r["error"])
    avg_time = round(sum(r["elapsed_sec"] for r in results) / len(results), 2) if results else 0
    hits     = sum(1 for r in results if any(TARGET_TOOL in t for t in r.get("tools_used", [])))
    print(f"\n完成｜成功：{len(results)-errors}/{len(results)}｜工具命中：{hits}/{len(results)}｜平均耗時：{avg_time}s")
    print(f"JSON：{json_out}")
    print(f"報告：{md_out}")


if __name__ == "__main__":
    main()
