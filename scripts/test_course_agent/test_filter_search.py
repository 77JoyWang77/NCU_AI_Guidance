"""
test_filter_search.py

針對 tool_search_courses 的過濾條件與跨域搜尋能力測試。
重點驗證：
  - student_college（可修課程過濾）
  - college（開課學院過濾）
  - dept（開課系所過濾）
  - 無 filter 的跨域搜尋能力
  - exact_match 欄位是否正確標記
  - [已停開] 課程是否被過濾

執行方式：
  python scripts/test_filter_search.py              # 全部執行
  python scripts/test_filter_search.py 機器學習     # 只跑含此關鍵字的測試
  python scripts/test_filter_search.py --validate   # 只跑驗證型測試（CC0328 等已知案例）
"""

import sys
import io
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

try:
    from app.services.tools import tool_search_courses
except ImportError as e:
    print(f"[錯誤] 無法 import 模組：{e}")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# 測試案例定義
# 格式：(query, label, kwargs, expected_hints)
#   expected_hints: dict，可選鍵：
#     must_contain   - list[str] course_code，結果中必須出現
#     must_not_contain - list[str] course_code，結果中不得出現
#     min_results    - int，最少要幾筆
#     expect_exact_match - bool，是否預期有 exact_match 欄位
# ─────────────────────────────────────────────────────────────────────────────

TEST_CASES = [

    # ══════════════════════════════════════════════════════════════════════════
    # 群組 1：無 filter 基本跨域搜尋
    # ══════════════════════════════════════════════════════════════════════════
    ("機器學習",   "無filter | AI核心",   {},   {"min_results": 8, "expect_exact_match": True}),
    ("深度學習",   "無filter | AI核心",   {},   {"min_results": 8, "expect_exact_match": True}),
    ("程式設計",   "無filter | 跨院廣泛", {},   {"min_results": 8}),
    ("資料科學",   "無filter | 跨院",     {},   {"min_results": 6}),
    ("統計學",     "無filter | 精確名稱", {},   {"min_results": 4, "expect_exact_match": True}),

    # ══════════════════════════════════════════════════════════════════════════
    # 群組 2：文學院學生可修的課（student_college）
    # CC0328 機器學習（全體可修但排除資電學院）應出現
    # ══════════════════════════════════════════════════════════════════════════
    ("經濟學",   "文學院可修",
     {"student_college": "文學院"},
     {"min_results": 3}),

    ("機器學習", "文學院可修 | CC0328應出現",
     {"student_college": "文學院"},
     {"min_results": 4, "must_contain": ["CC0328"], "expect_exact_match": True}),

    ("程式設計", "文學院可修",
     {"student_college": "文學院"},
     {"min_results": 2}),

    ("創業",     "文學院可修 | 跨域",
     {"student_college": "文學院"},
     {}),

    # ══════════════════════════════════════════════════════════════════════════
    # 群組 3：資訊電機學院學生可修的課
    # CC0328 機器學習應「不出現」（資電學院被排除）
    # ══════════════════════════════════════════════════════════════════════════
    ("機器學習", "資訊電機學院可修 | CC0328應消失",
     {"student_college": "資訊電機學院"},
     {"must_not_contain": ["CC0328"], "min_results": 5}),

    ("管理學",   "資訊電機學院可修 | 跨域管理",
     {"student_college": "資訊電機學院"},
     {}),

    ("投資學",   "資訊電機學院可修 | 跨域財金",
     {"student_college": "資訊電機學院"},
     {}),

    # ══════════════════════════════════════════════════════════════════════════
    # 群組 4：理學院學生可修的課（數學系所在學院）
    # ══════════════════════════════════════════════════════════════════════════
    ("心理學",   "理學院可修 | 跨文理域",
     {"student_college": "理學院"},
     {}),

    ("行為分析", "理學院可修 | 極冷門跨域",
     {"student_college": "理學院"},
     {}),

    ("資訊安全", "理學院可修 | 跨資工域",
     {"student_college": "理學院"},
     {}),

    ("半導體",   "理學院可修 | 跨工程域",
     {"student_college": "理學院"},
     {}),

    ("機器手臂", "理學院可修 | 跨機械域",
     {"student_college": "理學院"},
     {}),

    ("空間資訊", "理學院可修 | 跨地科域",
     {"student_college": "理學院"},
     {}),

    # ══════════════════════════════════════════════════════════════════════════
    # 群組 5：管理學院學生可修的課
    # ══════════════════════════════════════════════════════════════════════════
    ("機器學習", "管理學院可修",
     {"student_college": "管理學院"},
     {"min_results": 3}),

    ("投資學",   "管理學院可修 | 本院課程應優先",
     {"student_college": "管理學院"},
     {"min_results": 3}),

    # ══════════════════════════════════════════════════════════════════════════
    # 群組 6：指定開課學院（college filter）
    # ══════════════════════════════════════════════════════════════════════════
    ("機器學習", "生醫理工學院開設",
     {"college": "生醫理工學院"},
     {}),

    ("程式設計", "資訊電機學院開設",
     {"college": "資訊電機學院"},
     {"min_results": 3}),

    ("統計",     "理學院開設",
     {"college": "理學院"},
     {"min_results": 2}),

    # ══════════════════════════════════════════════════════════════════════════
    # 群組 7：指定開課系所（dept filter）
    # ══════════════════════════════════════════════════════════════════════════
    ("機器學習", "資訊工程學系開設",
     {"dept": "資訊工程學系"},
     {"min_results": 2}),

    ("機器學習", "機械工程學系開設",
     {"dept": "機械工程學系"},
     {}),

    # ══════════════════════════════════════════════════════════════════════════
    # 群組 8：冷門 / 奇怪領域（無 filter，測試搜尋能力邊界）
    # 有些預期找很少或找不到——都是正常的
    # ══════════════════════════════════════════════════════════════════════════
    ("水文學",   "無filter | 地科",  {},  {}),
    ("奈米",     "無filter | 材料",  {},  {}),
    ("微生物",   "無filter | 生物",  {},  {}),
    ("飲茶文化", "無filter | 文化",  {},  {}),
    ("AR",       "無filter | 縮寫",  {},  {}),
    ("解剖學",   "無filter | 醫學",  {},  {}),
    ("植物",     "無filter | 生態",  {},  {}),
    ("電磁學",   "無filter | 物理",  {},  {}),
    ("衛星",     "無filter | 太空",  {},  {}),
    ("生醫影像", "無filter | 跨域",  {},  {}),
    ("雷射",     "無filter | 光電",  {},  {}),
]

# ─────────────────────────────────────────────────────────────────────────────
# 格式化輸出
# ─────────────────────────────────────────────────────────────────────────────

def _divider(title: str, char: str = "=", width: int = 70):
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}")


def _fmt_filter(kwargs: dict) -> str:
    parts = []
    if kwargs.get("student_college"):
        parts.append(f"student_college={kwargs['student_college']}")
    if kwargs.get("college"):
        parts.append(f"college={kwargs['college']}")
    if kwargs.get("dept"):
        parts.append(f"dept={kwargs['dept']}")
    if kwargs.get("course_type"):
        parts.append(f"type={kwargs['course_type']}")
    return ", ".join(parts) if parts else "（無 filter）"


def _print_course_row(i: int, r: dict, kwargs: dict, prefix: str = ""):
    flags = []
    if "[已停開]" in r.get("name_zh", ""):
        flags.append("⚠停開")
    if kwargs.get("college") and r.get("college") != kwargs["college"]:
        flags.append(f"?college={r.get('college','?')}")
    if kwargs.get("dept") and r.get("dept") != kwargs["dept"]:
        flags.append(f"?dept={r.get('dept','?')}")
    flag_str = " ".join(flags)
    name    = r.get("name_zh", "")[:24]
    dept    = r.get("dept", "")[:20]
    college = r.get("college", "")[:10]
    print(f"  {prefix}{i:<3} {r.get('course_code',''):<10} {name:<26} {dept:<22} {college:<12} {flag_str}")


def run_case(query: str, label: str, kwargs: dict, expected: dict):
    filter_str = _fmt_filter(kwargs)
    _divider(f"Query: 「{query}」  [{label}]")
    print(f"  Filter: {filter_str}")

    try:
        results = tool_search_courses(query, **kwargs)
    except Exception as e:
        print(f"\n  ❌ 執行失敗：{e}")
        return

    exact    = [r for r in results if r.get("exact_match")]
    semantic = [r for r in results if not r.get("exact_match")]
    stopped  = [r for r in results if "[已停開]" in r.get("name_zh", "")]
    total    = len(results)

    print(f"\n  回傳：{total} 筆  |  ★exact: {len(exact)} 筆  |  語意: {len(semantic)} 筆  |  [已停開] 洩漏: {len(stopped)} 筆")
    if stopped:
        print(f"  ⚠️  已停開課程洩漏：{[r['name_zh'] for r in stopped]}")

    col_header = f"  {'#':<3} {'課號':<10} {'課名':<26} {'系所':<22} {'學院':<12} {'flags'}"
    col_sep    = f"  {'-'*3} {'-'*10} {'-'*26} {'-'*22} {'-'*12} {'-'*10}"

    # ── ★ exact_match 區（名稱完全符合）
    if exact:
        print(f"\n  ★ exact_match（{len(exact)} 筆）")
        print(col_header)
        print(col_sep)
        for i, r in enumerate(exact, 1):
            _print_course_row(i, r, kwargs)

    # ── 語意搜尋區
    if semantic:
        print(f"\n  語意結果（{len(semantic)} 筆）")
        print(col_header)
        print(col_sep)
        for i, r in enumerate(semantic, 1):
            _print_course_row(i, r, kwargs)
    elif not exact:
        print(f"\n  （無結果）")

    # ── 驗證 expected_hints
    print()
    passed = True

    if expected.get("min_results") and total < expected["min_results"]:
        print(f"  ⚠️  [WARN] 回傳僅 {total} 筆，預期 ≥ {expected['min_results']} 筆")
        passed = False
    elif total == 0:
        print(f"  ℹ️  找不到課程（若為冷門領域屬正常）")
    else:
        print(f"  ✓  回傳 {total} 筆（{'符合' if not expected.get('min_results') else '≥'+str(expected['min_results'])+' ✓'}）")

    for code in expected.get("must_contain", []):
        found = any(r.get("course_code") == code for r in results)
        status = "✓" if found else "❌"
        print(f"  {status}  must_contain: {code}  {'找到' if found else '【未找到！】'}")
        if not found:
            passed = False

    for code in expected.get("must_not_contain", []):
        found = any(r.get("course_code") == code for r in results)
        status = "❌" if found else "✓"
        print(f"  {status}  must_not_contain: {code}  {'【不應出現！】' if found else '正確排除'}")
        if found:
            passed = False

    if expected.get("expect_exact_match") and not exact:
        print(f"  ⚠️  [WARN] 預期有 exact_match 課程但未找到")

    if stopped:
        print(f"  ❌  [已停開] 洩漏：應被 Signal C 過濾")
        passed = False

    if passed and total > 0:
        print(f"  ✅ 通過")
    elif total == 0:
        pass  # 找不到視為資訊性輸出，不標記失敗


# ─────────────────────────────────────────────────────────────────────────────
# 主程式
# ─────────────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    validate_only = "--validate" in args
    if validate_only:
        args.remove("--validate")

    # 過濾測試案例
    keyword = args[0] if args else None
    if validate_only:
        cases = [c for c in TEST_CASES if c[3].get("must_contain") or c[3].get("must_not_contain")]
    elif keyword:
        cases = [c for c in TEST_CASES if keyword in c[0] or keyword in c[1]]
    else:
        cases = TEST_CASES

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(__file__).parent.parent.parent / "data" / "test_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{timestamp}_filter_search.md"

    buf = io.StringIO()

    class _Tee:
        def __init__(self, *streams):
            self._streams = streams
        def write(self, data):
            for s in self._streams:
                s.write(data)
        def flush(self):
            for s in self._streams:
                s.flush()

    original_stdout = sys.stdout
    sys.stdout = _Tee(original_stdout, buf)

    try:
        mode = "驗證型" if validate_only else (f"關鍵字={keyword!r}" if keyword else "全部")
        print(f"# tool_search_courses 過濾條件 & 跨域搜尋測試")
        print(f"執行時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"模式：{mode}，共 {len(cases)} 個測試案例")
        print(f"\n★ = exact_match（名稱完全符合）  ⚠ = 已停開洩漏  ? = filter 不符")
        print(f"注意：student_college 為學院層級過濾（如「電機系」需用「資訊電機學院」）")
        print(f"      無 filter 的冷門領域查詢找不到課程為正常現象")

        for query, label, kwargs, expected in cases:
            run_case(query, label, kwargs, expected)

        print(f"\n{'=' * 70}")
        print(f"  完成：共 {len(cases)} 個測試案例")
        print(f"{'=' * 70}")

    finally:
        sys.stdout = original_stdout

    content = buf.getvalue()
    out_path.write_text(f"```\n{content}\n```\n", encoding="utf-8")
    print(f"\n[輸出已儲存] {out_path}")


if __name__ == "__main__":
    main()
