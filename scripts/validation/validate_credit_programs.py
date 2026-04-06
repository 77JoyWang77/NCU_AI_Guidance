"""
驗證 data/processed/credit_programs/*.json 與原始 PDF 的一致性
- 確認 PDF 中的課程都有被存入 JSON
- 確認學分數正確
- 輸出 data/processed/validation_credit_programs.json

使用方式：python scripts/validate_credit_programs.py
"""

import json
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("請安裝 pdfplumber: pip install pdfplumber")
    sys.exit(1)

BASE_DIR = Path(__file__).parent.parent.parent
CREDIT_PROGRAMS_DIR = BASE_DIR / "data" / "processed" / "credit_programs"
RAW_PROGRAMS_DIR    = BASE_DIR / "data" / "raw" / "學分學程"
OUTPUT_PATH         = BASE_DIR / "data" / "processed" / "validation" / "validation_credit_programs.json"

# 課號正規表達式（一般 NCU 格式：2-3 英文字母 + 4-5 數字，或 TC 開頭的 TAICA 課號）
COURSE_CODE_RE = re.compile(r'\b([A-Z]{2,4}\d{4,5}(?:-[A-Z0-9]+)?)\b')
CREDITS_RE     = re.compile(r'(\d+(?:\.\d+)?)\s*學分')
INT_CREDITS_RE = re.compile(r'^\d+$')


# ─── 工具函式 ───────────────────────────────────────────────────────────────

def normalize_name(name: str) -> str:
    """移除空格、括號、全形符號差異；NFKC 正規化消除 CJK 相容字形差異（如 U+F9B4 vs U+9818）"""
    import unicodedata
    name = unicodedata.normalize('NFKC', name)
    return re.sub(r'[\s\u3000「」【】()（）\-_・·]', '', name).lower()


def extract_book_name(pdf_name: str) -> str:
    """從 PDF 檔名取出「...」中的名稱作為比對關鍵字"""
    m = re.search(r'[「『](.*?)[」』]', pdf_name)
    return m.group(1) if m else pdf_name


def find_pdf_for_program(program_name: str, college: str) -> Path | None:
    """
    在 RAW_PROGRAMS_DIR 下找與 program_name 最匹配的 PDF。
    策略：
      1) 取「...」中的關鍵字做子字串比對
      2) 找不到時，嘗試學院子目錄中唯一的 PDF（如 TAICA 多學程共用一份 PDF）
    """
    key = normalize_name(extract_book_name(program_name))
    # 先找對應學院子目錄
    college_dirs = []
    for d in RAW_PROGRAMS_DIR.iterdir():
        if d.is_dir() and (college in d.name or d.name in college):
            college_dirs.append(d)
    search_dirs = college_dirs + [RAW_PROGRAMS_DIR]

    # 策略 1：以學程名稱關鍵字比對 PDF 檔名
    for search_dir in search_dirs:
        for pdf in search_dir.rglob("*.pdf"):
            pdf_key = normalize_name(extract_book_name(pdf.stem))
            if key in pdf_key or pdf_key in key:
                return pdf

    # 策略 2：學院子目錄只有一份 PDF → 多學程共用（如 TAICA）
    for d in college_dirs:
        pdfs = list(d.glob("*.pdf"))
        if len(pdfs) == 1:
            return pdfs[0]

    return None


def extract_pdf_text(pdf_path: Path) -> str:
    """用 pdfplumber 擷取 PDF 全文"""
    text = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            t = page.extract_text(x_tolerance=3, y_tolerance=3)
            if t:
                text.append(t)
    return "\n".join(text)


def extract_pdf_tables(pdf_path: Path) -> list[list[list[str]]]:
    """用 pdfplumber 擷取 PDF 所有表格"""
    tables = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                tables.append(table)
    return tables


def find_code_in_text(code: str, text: str) -> bool:
    """
    判斷課號是否出現在 PDF 文字中。
    不用 \b 以避免 Python 3 把中文字視為 \w 導致邊界失效
    （如 AP3031氣候學 中 \b 不會在 '1' 和 '氣' 之間成立）。
    改用 ASCII 字母數字的 lookbehind / lookahead。
    """
    pattern = re.compile(r'(?<![A-Za-z0-9])' + re.escape(code) + r'(?![A-Za-z0-9])')
    return bool(pattern.search(text))


def find_credit_near_code(code: str, text: str) -> int | None:
    """
    在 PDF 文字中找到課號所在行，再從課號位置之後的文字提取學分數字。
    只搜尋課號「之後」的文字，避免同行前方的數字（如學分總計）被誤判。

    優先嘗試：
      1. 課號後有 (N) 括號格式
      2. 課號後有 N/N 或 N / N 格式（alias 並列學分）→ 取第一個數字
      3. 同行有多個課號時（CODE1/CODE2 N1 N2），按位置索引取對應學分
      4. 課號後（去除 alias 課號）第一個獨立數字（排除選/擇/備/共後的數字）
      5. 課號後有「N學分」
      6. 緊接的下一行只有一個數字（學分換行）
    """
    code_pat = re.compile(r'(?<![A-Za-z0-9])' + re.escape(code) + r'(?![A-Za-z0-9])')
    lines = text.split('\n')
    for i, line in enumerate(lines):
        m = code_pat.search(line)
        if not m:
            continue
        after = line[m.end():]

        # 策略 1：括號格式 (N)
        bm = re.search(r'\((\d+)\)', after)
        if bm:
            return int(bm.group(1))
        # 策略 2：N/N 或 N / N（alias 並列學分），取第一個
        bm = re.search(r'\b([1-9]\d?)\s*/\s*\d+\s*$', after.strip())
        if bm:
            return int(bm.group(1))
        # 策略 3：同行多課號且為斜線連接的 alias 組，按位置索引取學分
        # 只在課號之間純為「/空格+課號」時使用（不含其他內容）
        line_codes = re.findall(r'(?<![A-Za-z0-9])[A-Z]{2,4}\d{4,5}(?![A-Za-z0-9])', line)
        if len(line_codes) > 1 and code in line_codes:
            code_idx = line_codes.index(code)
            first_m = re.search(r'(?<![A-Za-z0-9])' + re.escape(line_codes[0]) + r'(?![A-Za-z0-9])', line)
            last_m  = re.search(r'(?<![A-Za-z0-9])' + re.escape(line_codes[-1]) + r'(?![A-Za-z0-9])', line)
            between = line[first_m.end():last_m.start()]
            # 確認 codes 之間只有斜線/逗號/空格+課號（純 alias 組）
            if re.fullmatch(r'[/,\s]*(?:[A-Z]{2,4}\d{4,5}[/,\s]*)*', between):
                after_all = re.sub(r'\d+\.', '', line[last_m.end():])
                credit_nums = re.findall(r'(?<![/\d選擇共備])([1-9]\d?)(?!\d)', after_all)
                # 只有當學分數量 >= 課號數量時才能位置對應（否則為合計學分）
                if code_idx < len(credit_nums) and len(credit_nums) >= len(line_codes):
                    return int(credit_nums[code_idx])
        # 策略 4：去除 alias 課號（含逗號分隔）後，第一個獨立數字
        # 若發現數字 > 4 且同行有多課號，可能是合計學分，略過
        after_clean = re.sub(r'[/,\s]*[A-Z]{2,4}\d{4,5}', '', after)
        bm = re.search(r'(?<![/\d選擇共備])([1-9]\d?)(?!\d)', after_clean)
        if bm:
            val = int(bm.group(1))
            if val > 4 and len(line_codes) > 1:
                pass   # 合計學分，不用
            else:
                return val
        # 策略 5：「N學分」
        bm = re.search(r'([1-9]\d?)\s*學分', after)
        if bm:
            return int(bm.group(1))
        # 策略 6：下一行只有數字（學分換行）
        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            bm = re.fullmatch(r'([1-9]\d?)', next_line)
            if bm:
                return int(bm.group(1))
    return None


def collect_all_courses(program: dict) -> list[dict]:
    """從一個 program 物件中蒐集所有 course（含 required + elective）"""
    courses = []
    for c in program.get("required_courses", []):
        courses.append(c)
    for grp in program.get("elective_groups", []):
        for c in grp.get("courses", []):
            courses.append(c)
    return courses


# ─── 主要驗證邏輯 ────────────────────────────────────────────────────────────

def validate_program(program: dict) -> dict:
    result = {
        "program": program["name"],
        "pdf_found": False,
        "pdf_path": None,
        "matched": [],
        "json_only": [],
        "pdf_only": [],
        "credit_mismatch": [],
        "no_code": [],   # JSON 中 code 為空的課程
    }

    pdf_path = find_pdf_for_program(program["name"], program.get("college", ""))
    if pdf_path is None:
        result["note"] = "找不到對應的 PDF"
        return result

    result["pdf_found"] = True
    result["pdf_path"] = str(pdf_path.relative_to(BASE_DIR))

    try:
        pdf_text = extract_pdf_text(pdf_path)
    except Exception as e:
        result["note"] = f"PDF 讀取失敗：{e}"
        return result

    # 從 PDF 文字中找所有課號
    pdf_codes = set(COURSE_CODE_RE.findall(pdf_text))

    all_json_courses = collect_all_courses(program)
    json_codes = {}
    for c in all_json_courses:
        code = c.get("code", "").strip()
        if not code:
            result["no_code"].append({"name": c.get("name"), "credits": c.get("credits")})
            continue
        # 處理 alias
        primary = code.split("/")[0].strip()
        json_codes[primary] = c
        for alias in code.split("/")[1:]:
            json_codes[alias.strip()] = c
        # 也處理 alias 欄位
        for alias in c.get("alias", "").split("/"):
            a = alias.strip()
            if a:
                json_codes[a] = c

    checked_primary = set()

    for code, course in json_codes.items():
        primary = list(json_codes.keys())[list(json_codes.values()).index(course)]
        if primary in checked_primary:
            continue
        checked_primary.add(primary)

        in_pdf = find_code_in_text(code, pdf_text)
        if not in_pdf:
            # 試 alias
            aliases = [c.strip() for c in course.get("alias", "").split("/") if c.strip()]
            in_pdf = any(find_code_in_text(a, pdf_text) for a in aliases)

        entry = {"code": code, "name": course.get("name"), "credits": course.get("credits")}
        if not in_pdf:
            result["json_only"].append(entry)
        else:
            # 驗證學分
            pdf_credit = find_credit_near_code(code, pdf_text)
            json_credit = course.get("credits")
            if pdf_credit is not None and json_credit is not None and int(pdf_credit) != int(json_credit):
                result["credit_mismatch"].append({
                    **entry,
                    "pdf_credits": pdf_credit,
                    "json_credits": json_credit,
                })
            else:
                result["matched"].append(entry)

    # PDF 中有、JSON 沒有的課號（過濾掉常見非課號的數字字串）
    known_json_codes = set(json_codes.keys())
    for code in sorted(pdf_codes - known_json_codes):
        # 排除可能是年份或其他數字的假課號
        if re.match(r'^[A-Z]{2,4}\d{4,5}$', code):
            result["pdf_only"].append({"code": code})

    return result


def main():
    all_results = []

    json_files = sorted(CREDIT_PROGRAMS_DIR.glob("credit_programs_*.json"))
    print(f"找到 {len(json_files)} 個 credit_programs JSON 檔案")

    for jf in json_files:
        with open(jf, encoding="utf-8") as f:
            programs = json.load(f)

        print(f"\n── {jf.stem} ({len(programs)} 個學程) ──")
        for program in programs:
            r = validate_program(program)
            all_results.append(r)

            status = "✅" if r["pdf_found"] and not r["json_only"] and not r["credit_mismatch"] else "⚠️"
            print(f"  {status} {program['name']}")
            if not r["pdf_found"]:
                print(f"      ❌ 找不到 PDF")
            else:
                print(f"      PDF: {r['pdf_path']}")
                if r["matched"]:
                    print(f"      ✓ 吻合課程: {len(r['matched'])} 門")
                if r["json_only"]:
                    print(f"      ⚠ JSON 有但 PDF 找不到: {[c['code'] for c in r['json_only']]}")
                if r["credit_mismatch"]:
                    print(f"      ⚠ 學分不一致: {r['credit_mismatch']}")
                if r["pdf_only"]:
                    print(f"      ℹ PDF 有但 JSON 沒有: {[c['code'] for c in r['pdf_only'][:10]]}")
                if r["no_code"]:
                    print(f"      ℹ 無課號課程（不比對）: {len(r['no_code'])} 門")

    # 輸出 JSON
    summary = {
        "total_programs": len(all_results),
        "pdf_not_found": sum(1 for r in all_results if not r["pdf_found"]),
        "has_json_only": sum(1 for r in all_results if r["json_only"]),
        "has_credit_mismatch": sum(1 for r in all_results if r["credit_mismatch"]),
    }
    output = {"summary": summary, "results": all_results}

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 驗證報告已輸出至：{OUTPUT_PATH}")
    print(f"   總學程：{summary['total_programs']}，"
          f"找不到 PDF：{summary['pdf_not_found']}，"
          f"JSON 有 PDF 無：{summary['has_json_only']}，"
          f"學分不符：{summary['has_credit_mismatch']}")


if __name__ == "__main__":
    main()
