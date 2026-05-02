#!/usr/bin/env python3
"""
debug_agent.py — NCU Agent 行為檢驗工具

顯示每次問答的：
  • 每輪 Tool Call（名稱、參數、回傳摘要）
  • Course Pool（所有 tool 收集到的課程）
  • Course Cards（最終顯示給使用者的課程）
  • Pool 有但 Cards 沒有的課程（被 LLM 過濾）
  • 最終回答
  • Token 統計

用法：
  python scripts/debug_agent.py
  python scripts/debug_agent.py "Python 有哪些課？"
  python scripts/debug_agent.py "演算法相關課程" --save
  python scripts/debug_agent.py --batch scripts/test_questions.txt --save
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(ROOT / "backend" / ".env", override=False)

# Monkey-patch execute_tool to log all calls
from app.services import tools as _tools_module

_tool_log: list[dict] = []
_original_execute = _tools_module.execute_tool


def _result_summary(tool_name: str, result) -> str:
    if isinstance(result, list):
        names = [r.get("name_zh") or r.get("name") or r.get("program_name") or "?"
                 for r in result[:3] if isinstance(r, dict)]
        return f"list[{len(result)}]  範例：{', '.join(names)}" if names else f"list[{len(result)}]"
    if isinstance(result, dict):
        if result.get("found") is False:
            return f"dict  found=False  {result.get('message', '')[:60]}"
        if "courses" in result:
            courses = result["courses"]
            names = [c.get("name") or c.get("id", "?") for c in courses[:3]]
            return f"dict courses[{len(courses)}]  範例：{', '.join(names)}"
        if "description" in result:
            desc = result.get("description", "")[:60]
            return f"dict program_info  description={desc}…"
        return f"dict  keys={list(result.keys())[:6]}"
    if isinstance(result, str):
        preview = result[:120].replace("\n", " ")
        return f"str[{len(result)}]  {preview}…"
    return str(type(result).__name__)


def _patched_execute(tool_name: str, args: dict):
    result = _original_execute(tool_name, args)
    _tool_log.append({
        "tool":    tool_name,
        "args":    args,
        "summary": _result_summary(tool_name, result),
        "raw":     result,
    })
    return result


_tools_module.execute_tool = _patched_execute

from app.services import llm_service as llm

try:
    import colorama
    colorama.init()
    R = colorama.Fore.RED
    G = colorama.Fore.GREEN
    Y = colorama.Fore.YELLOW
    B = colorama.Fore.CYAN
    DIM = colorama.Style.DIM
    RST = colorama.Style.RESET_ALL
except ImportError:
    R = G = Y = B = DIM = RST = ""


def _hr(char="─", width=72):
    print(char * width)


def run_debug(question: str, save_log: bool = False) -> dict:
    global _tool_log
    _tool_log = []

    print()
    _hr("═")
    print(f"{B}問題：{RST}{question}")
    _hr("═")

    result = llm.generate_with_tools(question)

    # Tool Call 紀錄
    print(f"\n{Y}【Tool Call 紀錄】{RST}  共 {len(_tool_log)} 次")
    for i, t in enumerate(_tool_log, 1):
        args_str = json.dumps(t["args"], ensure_ascii=False)
        if len(args_str) > 100:
            args_str = args_str[:100] + "…"
        print(f"  {DIM}[{i}]{RST} {B}{t['tool']}{RST}")
        print(f"      args   : {args_str}")
        print(f"      result : {t['summary']}")

    # Course Pool（generate_with_tools 直接回傳 list）
    pool_list: list[dict] = result.get("course_pool", [])
    pool: dict[str, dict] = {c["name"]: c for c in pool_list if c.get("name")}
    print(f"\n{Y}【Course Pool】{RST}  共 {len(pool)} 門")
    for name, c in list(pool.items())[:25]:
        tag = c.get("dept", "")
        if c.get("credits"):
            tag += f" {c['credits']}學分"
        print(f"  {DIM}•{RST} {name}  {DIM}{tag}{RST}")
    if len(pool) > 25:
        print(f"  {DIM}… 還有 {len(pool)-25} 門{RST}")

    # Course Cards
    cards = result.get("course_cards", [])
    card_names = {c["name"] for c in cards}
    print(f"\n{Y}【Course Cards（最終推薦）】{RST}  共 {len(cards)} 門")
    for c in cards:
        in_pool = "(✓ pool)" if c["name"] in pool else f"{R}(⚠ 不在 pool 中，可能幻覺){RST}"
        print(f"  {G}✓{RST} {c['name']}  {DIM}{c.get('dept','')} {in_pool}{RST}")

    # Pool 有但 Cards 沒有
    filtered = [n for n in pool if n not in card_names]
    if filtered:
        print(f"\n{Y}【Pool 有但未納入推薦】{RST}  {len(filtered)} 門（LLM 自行過濾）")
        for n in filtered[:15]:
            print(f"  {R}×{RST} {n}  {DIM}{pool[n].get('dept','')}{RST}")
        if len(filtered) > 15:
            print(f"  {DIM}… 還有 {len(filtered)-15} 門{RST}")

    # 最終回答
    print(f"\n{Y}【最終回答】{RST}")
    print(result["answer"])

    # 統計
    tools_used = result.get("tools_used", [])
    print(f"\n{Y}【統計】{RST}")
    print(f"  tools_used    : {', '.join(tools_used) or '(無)'}")
    print(f"  pool_count    : {result.get('course_pool_count', 0)}")
    print(f"  input_tokens  : {result.get('input_tokens', '?')}")
    print(f"  output_tokens : {result.get('output_tokens', '?')}")
    print(f"  has_large     : {result.get('has_large_result', False)}")

    # 儲存 log
    if save_log:
        log_dir = ROOT / "logs"
        log_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_q = question[:20].replace(" ", "_").replace("/", "-")
        log_path = log_dir / f"debug_{ts}_{safe_q}.json"
        log_data = {
            "question":     question,
            "answer":       result["answer"],
            "tool_log": [
                {"tool": t["tool"], "args": t["args"], "summary": t["summary"]}
                for t in _tool_log
            ],
            "course_pool":  pool_list,
            "course_cards": cards,
            "filtered_out": filtered,
            "tools_used":   tools_used,
            "tokens": {
                "input":  result.get("input_tokens"),
                "output": result.get("output_tokens"),
            },
        }
        log_path.write_text(
            json.dumps(log_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n{G}📝 Log 已儲存：{log_path}{RST}")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="NCU Agent 行為檢驗工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""範例：
  python scripts/debug_agent.py
  python scripts/debug_agent.py "哪些課教 Python？" --save
  python scripts/debug_agent.py --batch scripts/test_questions.txt --save
""",
    )
    parser.add_argument("question", nargs="?", help="要測試的問題（省略則進入互動模式）")
    parser.add_argument("--save",  action="store_true", help="儲存 JSON log 到 logs/")
    parser.add_argument("--batch", metavar="FILE", help="批次測試：一行一個問題的 txt 檔")
    args = parser.parse_args()

    if args.batch:
        questions = Path(args.batch).read_text(encoding="utf-8").strip().splitlines()
        for q in questions:
            q = q.strip()
            if q and not q.startswith("#"):
                run_debug(q, save_log=args.save)
    elif args.question:
        run_debug(args.question, save_log=args.save)
    else:
        print("NCU Agent 行為檢驗工具（輸入 q 離開）")
        while True:
            try:
                q = input("\n問題> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if q.lower() in ("q", "quit", "exit"):
                break
            if q:
                run_debug(q, save_log=args.save)


if __name__ == "__main__":
    main()
