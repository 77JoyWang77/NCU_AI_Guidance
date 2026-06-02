"""
test_course_tools.py

專門測試 search_courses、ppr_explore、find_similar_courses 三個找課工具。
題目設計涵蓋：
  - 高中生模糊問法、大概念探索、多領域交叉
  - 小眾冷門領域、具體技術工具名
  - 從現有課程/概念採樣設計的精準題目
  - topic_tag 通識過濾

每題記錄：實際呼叫的工具、傳入參數、回傳課程數、前幾筆課程名稱、完整回答。
可用 --tools 參數只跑特定工具的題組。

執行方式：
  python scripts/test_course_tools.py
  python scripts/test_course_tools.py --url http://localhost:8000
  python scripts/test_course_tools.py --tools search          # 只跑 search_courses 題組
  python scripts/test_course_tools.py --tools ppr,similar     # 跑多個題組
  python scripts/test_course_tools.py --nos 3,7,12            # 指定題號

輸出：
  data/test_results/<timestamp>_course_tools.json
  data/test_results/<timestamp>_course_tools.md
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT        = Path(__file__).parent.parent.parent
RESULTS_DIR = ROOT / "data" / "test_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── 測試題目 ──────────────────────────────────────────────────────────────────
# 格式：(tool_group, category_label, question)
# tool_group: "search" | "ppr" | "similar" | "mixed"

QUESTIONS = [

    # ═══════════════════════════════════════════════════════════════════════
    # search_courses：找課
    # ═══════════════════════════════════════════════════════════════════════

    # ── 高中生大概念模糊問法 ─────────────────────────────────────────────────
    ("search", "模糊大概念",
     "我高中對物理和數學都還不錯，想在大學繼續延伸，有什麼課推薦？"),

    ("search", "模糊大概念",
     "我對環境保護和氣候變遷有興趣，大學有哪些課可以學這些？"),

    ("search", "模糊大概念",
     "想學怎麼分析資料、做統計，不一定要很深的程式，有推薦的課嗎？"),

    ("search", "模糊大概念",
     "我對腦科學和心理學都有興趣，有課可以同時接觸這兩塊嗎？"),

    ("search", "模糊大概念",
     "想了解太空和宇宙，有哪些課程可以入門？"),

    # ── 跨院/跨領域搜尋 ─────────────────────────────────────────────────────
    ("search", "跨院探索",
     "有哪些課程在教資料視覺化或資訊圖表？不限系所。"),

    ("search", "跨院探索",
     "哪些課有用到機器學習來解決工程或科學問題，不限系所？"),

    ("search", "跨院探索",
     "有關地震預測或地震工程的課程有哪些？"),

    ("search", "跨院探索",
     "有沒有和影像辨識或電腦視覺相關的課，涵蓋各系？"),

    # ── 技術工具導向（從採樣 Technology 節點出發）─────────────────────────────
    ("search", "技術工具",
     "哪些課有教 Scikit-Learn 或機器學習工具庫？"),

    ("search", "技術工具",
     "Node-RED 或物聯網相關課程有哪些？"),

    ("search", "技術工具",
     "哪些課有用到 fMRIPrep 或腦影像分析工具？"),

    ("search", "技術工具",
     "有沒有課教統一建模語言（UML）或軟體設計方法？"),

    # ── 小眾冷門領域（從採樣 Concept/Field 節點出發）──────────────────────────
    ("search", "小眾冷門",
     "震測勘探或地震波探勘有開課嗎？"),

    ("search", "小眾冷門",
     "無人機控制或自主飛行相關課程有哪些？"),

    ("search", "小眾冷門",
     "有沒有課程在講鋼橋設計或橋梁工程？"),

    ("search", "小眾冷門",
     "語言哲學或語言學理論相關的課有哪些？"),

    ("search", "小眾冷門",
     "有沒有關於美術史研究或藝術史的課程？"),

    # ── topic_tag 通識過濾（25 個固定 tag）────────────────────────────────────
    ("search", "通識 topic_tag",
     "通識課裡有哪些是醫學主題的課程？"),

    ("search", "通識 topic_tag",
     "通識有沒有工程類的課？想了解工程在社會的應用。"),

    ("search", "通識 topic_tag",
     "通識裡有什麼環境科學主題的課程？"),

    ("search", "通識 topic_tag",
     "通識有哪些哲學或倫理學的課？"),

    ("search", "通識 topic_tag",
     "通識有沒有宗教或靈性相關的課程？"),

    # ── 研究所/進階課程 ──────────────────────────────────────────────────────
    ("search", "研究所課程",
     "研究所有哪些和財務風險或衍生性商品相關的課？"),

    ("search", "研究所課程",
     "有哪些研究所課程在教量子力學或量子計算的進階應用？"),

    # ═══════════════════════════════════════════════════════════════════════
    # ppr_explore：多概念跨域探索
    # ═══════════════════════════════════════════════════════════════════════

    # ── 高中生想跨域探索 ─────────────────────────────────────────────────────
    ("ppr", "PPR 跨域",
     "我同時對 AI 和醫學都有興趣，中央大學有哪些課程在這兩個領域的交界？"),

    ("ppr", "PPR 跨域",
     "對統計學和金融都有熱情，有什麼課可以同時學這兩塊？"),

    ("ppr", "PPR 跨域",
     "對法律和科技的交叉議題有興趣，例如數位法律或隱私權，有相關課嗎？"),

    ("ppr", "PPR 跨域",
     "喜歡生態學和資料分析，想找兩者都有的課程，有推薦嗎？"),

    ("ppr", "PPR 跨域",
     "對影像處理和材料科學都有興趣，中央大學有哪些課連結這兩個領域？"),

    # ── 冷門/異質跨域 ────────────────────────────────────────────────────────
    ("ppr", "PPR 冷門跨域",
     "太空物理和電磁學有沒有什麼交叉課程？"),

    ("ppr", "PPR 冷門跨域",
     "地質學和永續能源有相關的課嗎？想了解地熱或碳封存。"),

    ("ppr", "PPR 冷門跨域",
     "音樂或聲音和訊號處理有交集的課程嗎？"),

    # ── PPR Overview（圖譜全貌）───────────────────────────────────────────────
    ("ppr", "PPR Overview",
     "中央大學機器人技術的完整生態是什麼？有哪些課程、老師和系所？"),

    ("ppr", "PPR Overview",
     "量子計算在中央大學連結到哪些課程、教師和系所？給我一個全貌。"),

    ("ppr", "PPR Overview",
     "自然語言處理在中央大學有哪些相關研究和課程？"),

    # ── 教師/系所網絡探索 ─────────────────────────────────────────────────────
    ("ppr", "PPR 教師/系所",
     "影像處理和電腦視覺領域有哪些教授和課程？給我一個概觀。"),

    ("ppr", "PPR 教師/系所",
     "哪些系所有在研究永續能源或儲能技術？"),

    # ═══════════════════════════════════════════════════════════════════════
    # find_similar_courses：相似課推薦
    # ═══════════════════════════════════════════════════════════════════════

    # ── 從採樣課程出發（具有 concept 節點的課程）──────────────────────────────
    ("similar", "相似課-採樣課程",
     "有沒有和水文地質學類似的課程？想了解地下水或水資源相關的。"),

    ("similar", "相似課-採樣課程",
     "迴歸分析這門課有沒有類似的課？想找統計方法相近的課程。"),

    ("similar", "相似課-採樣課程",
     "儲能原理與技術這門課有沒有類似的課，想繼續學能源相關的？"),

    ("similar", "相似課-採樣課程",
     "遙測影像處理與分析有沒有類似的課？想學更多遙感探測的應用。"),

    ("similar", "相似課-採樣課程",
     "機器人特論這門課有沒有類似的課程推薦？"),

    # ── 高中生問法（不知道精確課名）──────────────────────────────────────────
    ("similar", "相似課-高中生問法",
     "有沒有和機器學習類似但不同系所的課？想比較看看各系的切入角度。"),

    ("similar", "相似課-高中生問法",
     "微積分學完之後，有沒有類似的進階課程可以接著修？"),

    ("similar", "相似課-高中生問法",
     "統計學有沒有在不同系所開的類似課程，內容或角度稍微不同的？"),

    ("similar", "相似課-高中生問法",
     "想找和計算機概論類似的入門課，有哪些選擇？"),

    # ── 稀疏概念課程（圖中 concept 節點少，考驗 2-hop）──────────────────────
    ("similar", "相似課-稀疏課程",
     "和刑事訴訟法專題研究類似的法律相關課程有哪些？"),

    ("similar", "相似課-稀疏課程",
     "太空電離層資料同化導論有沒有類似的大氣或太空物理課程？"),

    ("similar", "相似課-稀疏課程",
     "有沒有和動力學（機械系）類似的課程？"),

    ("similar", "相似課-稀疏課程",
     "電磁學（機械工程學系）有沒有類似的課，想找接近的物理課？"),

    # ── 混合情境（可能同時用 find_similar + search）──────────────────────────
    ("mixed", "混合工具",
     "我修過機率與統計，想繼續往資料科學方向深入，有推薦的相似或進階課程嗎？"),

    ("mixed", "混合工具",
     "衛星遙測概論修完後可以接什麼課？有沒有類似的或進階的？"),

    ("mixed", "混合工具",
     "對都市防災有興趣，有沒有類似主題的課，或者相關的進一步課程？"),
]

# ── 標籤說明 ──────────────────────────────────────────────────────────────────
CAT_LABELS = {
    "search":  "search_courses",
    "ppr":     "ppr_explore",
    "similar": "find_similar_courses",
    "mixed":   "混合工具",
}

TOOL_GROUP_KEYS = {
    "search":  "search",
    "ppr":     "ppr",
    "similar": "similar",
    "mixed":   "mixed",
}


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

        return {
            "answer":            "".join(answer_parts),
            "tools_used":        done_data.get("tools_used", []),
            "course_cards":      done_data.get("course_cards", []),
            "course_pool_count": done_data.get("course_pool_count", 0),
            "has_large_result":  done_data.get("has_large_result", False),
            "input_tokens":      done_data.get("input_tokens", 0),
            "output_tokens":     done_data.get("output_tokens", 0),
            "tool_calls":        done_data.get("debug_trace", {}).get("toolCalls", []),
        }
    except requests.exceptions.Timeout:
        return {"error": "timeout", "answer": "", "tools_used": [], "course_cards": [], "tool_calls": []}
    except Exception as e:
        return {"error": str(e), "answer": "", "tools_used": [], "course_cards": [], "tool_calls": []}


# ── 測試執行 ──────────────────────────────────────────────────────────────────
def run_tests(base_url: str, questions: list[tuple]) -> list[dict]:
    results = []
    total = len(questions)
    for i, (tool_group, cat_label, q) in enumerate(questions, 1):
        group_display = CAT_LABELS.get(tool_group, tool_group)
        print(f"[{i:02d}/{total}] [{group_display}／{cat_label}] {q}")
        t0 = time.time()
        resp = ask_stream(base_url, q)
        elapsed = round(time.time() - t0, 2)

        record = {
            "no":            i,
            "tool_group":    tool_group,
            "cat_label":     cat_label,
            "question":      q,
            "answer":        resp.get("answer", ""),
            "tools_used":    resp.get("tools_used", []),
            "tool_calls":    resp.get("tool_calls", []),
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
        print(f"  {status} {elapsed}s | tools: {tools_str} | cards: {cards_n}")
        # 顯示期待工具是否被呼叫
        if tool_group != "mixed":
            expected_map = {
                "search":  "search_courses",
                "ppr":     "ppr_explore",
                "similar": "find_similar_courses",
            }
            expected = expected_map.get(tool_group, "")
            hit = expected and any(expected in t for t in record["tools_used"])
            print(f"  {'✓' if hit else '△'} 期待工具「{expected}」{'已呼叫' if hit else '未呼叫（可能改用其他工具）'}")
        print()

    return results


# ── 格式化輸出 ────────────────────────────────────────────────────────────────
def _fmt_args(args: dict) -> str:
    s = json.dumps(args, ensure_ascii=False)
    return s[:150] + "…" if len(s) > 150 else s


def save_json(results: list[dict], path: Path) -> None:
    path.write_text(
        json.dumps({"results": results, "total": len(results)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_markdown(results: list[dict], path: Path) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 計算各工具命中率
    group_stats: dict[str, dict] = {}
    for r in results:
        g = r["tool_group"]
        if g not in group_stats:
            group_stats[g] = {"total": 0, "hit": 0, "errors": 0}
        group_stats[g]["total"] += 1
        if r["error"]:
            group_stats[g]["errors"] += 1
        expected_map = {"search": "search_courses", "ppr": "ppr_explore", "similar": "find_similar_courses"}
        expected = expected_map.get(g, "")
        if expected and any(expected in t for t in r.get("tools_used", [])):
            group_stats[g]["hit"] += 1

    lines = [f"# 課程工具測試報告（search_courses / ppr_explore / find_similar_courses）\n\n"]
    lines.append(f"> 執行時間：{now}  \n")
    lines.append(f"> 總題數：{len(results)}  \n\n")

    # 摘要表格
    lines.append("## 摘要\n\n")
    lines.append("| 工具組 | 題數 | 期待工具命中 | 錯誤 |\n")
    lines.append("|--------|------|------------|------|\n")
    for g, s in group_stats.items():
        label = CAT_LABELS.get(g, g)
        hit_str = f"{s['hit']}/{s['total']}" if g != "mixed" else "—"
        lines.append(f"| {label} | {s['total']} | {hit_str} | {s['errors']} |\n")
    lines.append("\n---\n")

    # 依工具組分群輸出
    current_group = None
    for r in results:
        if r["tool_group"] != current_group:
            current_group = r["tool_group"]
            label = CAT_LABELS.get(current_group, current_group)
            lines.append(f"\n## {label}\n")

        status = "❌" if r["error"] else "✅"
        cards  = r.get("course_cards", [])
        tcs    = r.get("tool_calls", [])

        # 期待命中標記
        expected_map = {"search": "search_courses", "ppr": "ppr_explore", "similar": "find_similar_courses"}
        expected = expected_map.get(r["tool_group"], "")
        hit = expected and any(expected in t for t in r.get("tools_used", []))
        hit_badge = "✓" if hit else ("—" if r["tool_group"] == "mixed" else "△")

        lines.append(f"\n### {status} Q{r['no']}：{r['question']}\n\n")
        lines.append(
            f"**類別：** {r['cat_label']}　"
            f"**耗時：** {r['elapsed_sec']}s　"
            f"**in/out tokens：** {r.get('input_tokens',0)}/{r.get('output_tokens',0)}　"
            f"**Cards：** {len(cards)}　**Pool：** {r.get('course_pool_count',0)}　"
            f"**期待工具：** {hit_badge}  \n\n"
        )

        if r["error"]:
            lines.append(f"**錯誤：** {r['error']}\n\n")
            continue

        # 工具呼叫明細
        if tcs:
            lines.append("**工具呼叫：**\n\n")
            lines.append("| # | 工具 | 參數 | 回傳 | 前幾筆課程 |\n")
            lines.append("|---|------|------|------|----------|\n")
            for j, tc in enumerate(tcs, 1):
                tool     = tc.get("tool", "?")
                args_str = _fmt_args(tc.get("args", {}))
                count    = tc.get("count")
                sc_type  = tc.get("scoreType") or ""
                count_str = (f"{count} 筆" if count is not None else "—") + (f"（{sc_type}）" if sc_type else "")
                courses  = tc.get("coursesFound", [])[:4]
                scores   = tc.get("scores", [])
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
            lines.append("**推薦課程：** 無課程卡片  \n\n")

        # 完整回答
        answer_quoted = r["answer"].replace("\n", "\n> ")
        lines.append(f"**回答：**\n> {answer_quoted}\n\n---\n")

    path.write_text("".join(lines), encoding="utf-8")


# ── 主流程 ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="課程工具測試（search / ppr / similar）")
    parser.add_argument("--url",   default="http://localhost:8000", help="API base URL")
    parser.add_argument("--tools", default=None,
                        help="只跑指定工具組，逗號分隔：search, ppr, similar, mixed")
    parser.add_argument("--nos",   default=None,
                        help="只跑指定題號，逗號分隔，例如 --nos 1,3,5")
    args = parser.parse_args()

    questions = list(QUESTIONS)

    if args.tools:
        allowed = {t.strip() for t in args.tools.split(",")}
        questions = [q for q in questions if q[0] in allowed]

    if args.nos:
        nos = {int(x.strip()) for x in args.nos.split(",")}
        # 先給所有題目編號，再過濾
        questions = [q for i, q in enumerate(QUESTIONS, 1) if i in nos]

    print(f"目標：{args.url}")
    print(f"題數：{len(questions)}\n")

    results = run_tests(args.url, questions)

    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_out = RESULTS_DIR / f"{ts}_course_tools.json"
    md_out   = RESULTS_DIR / f"{ts}_course_tools.md"

    save_json(results, json_out)
    save_markdown(results, md_out)

    errors   = sum(1 for r in results if r["error"])
    avg_time = round(sum(r["elapsed_sec"] for r in results) / len(results), 2) if results else 0
    print(f"\n完成｜成功：{len(results) - errors}/{len(results)}｜平均耗時：{avg_time}s")
    print(f"JSON：{json_out}")
    print(f"報告：{md_out}")


if __name__ == "__main__":
    main()
