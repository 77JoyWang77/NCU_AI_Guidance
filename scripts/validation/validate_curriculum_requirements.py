"""
驗證 data/processed/curriculum_requirements_114.json 與應修科目表 PDF 的一致性
- 對每個系所，找對應的 PDF，比對 required_courses 的課號與學分
- 輸出 data/processed/validation_curriculum_requirements.json

使用方式：python scripts/validate_curriculum_requirements.py
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

try:
    import fitz as pymupdf   # pymupdf
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

BASE_DIR         = Path(__file__).parent.parent.parent
CURRICULUM_JSON  = BASE_DIR / "data" / "processed" / "curriculum_requirements_114.json"
REQUIREMENTS_DIR = BASE_DIR / "data" / "raw" / "應修科目表"
OUTPUT_PATH      = BASE_DIR / "data" / "processed" / "validation" / "validation_curriculum_requirements.json"

COURSE_CODE_RE = re.compile(r'\b([A-Z]{2,4}\d{4,5})\b')


# ─── 工具函式 ───────────────────────────────────────────────────────────────

def normalize(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize('NFKC', s or "")
    return re.sub(r'[\s\u3000「」【】()（）\-_]', '', s).lower()


def find_pdf_for_dept(dept_name: str) -> list[Path]:
    """
    找到 dept_name 對應的 PDF（可能有多個：主檔 + 分組）。
    搜尋路徑：REQUIREMENTS_DIR/<學院>/*.pdf（遞迴）
    """
    key = normalize(dept_name)
    found = []
    for pdf in REQUIREMENTS_DIR.rglob("*.pdf"):
        stem_norm = normalize(pdf.stem.replace("_114", "").replace("_113", ""))
        if key in stem_norm or stem_norm in key:
            found.append(pdf)
    # 若找到多個，優先回傳與名稱最接近的
    found.sort(key=lambda p: abs(len(normalize(p.stem)) - len(key)))
    return found


_CID_OFFSET = 0x101   # 地球科學系 PDF 使用 ASCII+0x101 偏移字型


def _decode_cid_font(text: str) -> str:
    """
    解碼 CID-keyed 字型偏移：U+0121–U+017F → ASCII 0x20–0x7E。
    此字型將每個 ASCII 可見字元加上 0x101 偏移，導致課號變成拉丁延伸字母。
    例：GP2031 → ňőĳıĴĲ（ň=G, ő=P, ĳ=2, ı=0, Ĵ=3, Ĳ=1）
    """
    result = []
    for c in text:
        cp = ord(c)
        if 0x0121 <= cp <= 0x017F:
            decoded = chr(cp - _CID_OFFSET)
            if 0x20 <= ord(decoded) <= 0x7E:
                result.append(decoded)
                continue
        result.append(c)
    return ''.join(result)


def _needs_cid_decode(text: str) -> bool:
    """
    偵測是否為 CID 字型無法讀取的 PDF。
    pdfplumber 遇到 CID-keyed 字型時輸出 (cid:XXXX) 亂碼；
    pymupdf 能讀出字元但使用 ASCII+0x101 偏移，可再解碼還原。
    判斷條件：pdfplumber 文字中幾乎沒有 ASCII 課號（2–4 大寫字母+4–5 位數），
              且含有 (cid:XXXX) 模式。
    """
    has_cid = bool(re.search(r'\(cid:\d+\)', text))
    has_codes = bool(re.search(r'[A-Z]{2,4}\d{4,5}', text))
    return has_cid and not has_codes


def extract_pdf_text(pdf_path: Path) -> str:
    text_parts = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            t = page.extract_text(x_tolerance=3, y_tolerance=3)
            if t:
                text_parts.append(t)
    raw = "\n".join(text_parts)

    # 若 pdfplumber 讀出的文字含有大量 CID 偏移字元，改用 pymupdf 並解碼
    if _needs_cid_decode(raw):
        if HAS_PYMUPDF:
            try:
                doc = pymupdf.open(str(pdf_path))
                mupdf_text = "\n".join(doc[i].get_text() for i in range(len(doc)))
                return _decode_cid_font(mupdf_text)
            except Exception:
                pass
        # 退路：直接對 pdfplumber 的文字解碼
        return _decode_cid_font(raw)

    return raw


def find_code_in_text(code: str, text: str) -> bool:
    # 不用 \b：Python 3 把中文字視為 \w，導致「課號氣候學」中邊界失效
    return bool(re.search(r'(?<![A-Za-z0-9])' + re.escape(code) + r'(?![A-Za-z0-9])', text))


def find_credit_near_code(code: str, text: str) -> int | None:
    """
    逐行搜尋課號所在行，只從課號位置之後提取學分，避免同行前方數字誤判。

    優先順序：(N) 括號 > N/N alias並列取第一 > 同行多課號按位置索引
            > 去除alias後第一個獨立數字（排除選/擇後數字）> N學分 > 下一行純數字
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
        # 策略 3：同行多課號且為斜線/逗號連接的 alias 組，按位置索引取學分
        line_codes = re.findall(r'(?<![A-Za-z0-9])[A-Z]{2,4}\d{4,5}(?![A-Za-z0-9])', line)
        if len(line_codes) > 1 and code in line_codes:
            code_idx = line_codes.index(code)
            first_m = re.search(r'(?<![A-Za-z0-9])' + re.escape(line_codes[0]) + r'(?![A-Za-z0-9])', line)
            last_m  = re.search(r'(?<![A-Za-z0-9])' + re.escape(line_codes[-1]) + r'(?![A-Za-z0-9])', line)
            between = line[first_m.end():last_m.start()]
            if re.fullmatch(r'[/,\s]*(?:[A-Z]{2,4}\d{4,5}[/,\s]*)*', between):
                after_all = re.sub(r'\d+\.', '', line[last_m.end():])
                credit_nums = re.findall(r'(?<![/\d選擇共備])([1-9]\d?)(?!\d)', after_all)
                if code_idx < len(credit_nums) and len(credit_nums) >= len(line_codes):
                    return int(credit_nums[code_idx])
        # 策略 4：去除 alias 課號（含逗號分隔）後，第一個獨立數字
        after_clean = re.sub(r'[/,\s]*[A-Z]{2,4}\d{4,5}', '', after)
        bm = re.search(r'(?<![/\d選擇共備])([1-9]\d?)(?!\d)', after_clean)
        if bm:
            val = int(bm.group(1))
            if val > 4 and len(line_codes) > 1:
                pass   # 可能為合計學分，略過
            else:
                return val
        # 策略 5：N學分
        bm = re.search(r'([1-9]\d?)\s*學分', after)
        if bm:
            return int(bm.group(1))
        # 策略 6：下一行只有數字
        if i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if re.fullmatch(r'[1-9]\d?', nxt):
                return int(nxt)
    return None


def get_all_required_courses(dept: dict) -> list[dict]:
    """
    從 department（或 group/track）物件遞迴取出所有必修課程。
    """
    courses = []
    courses.extend(dept.get("required_courses", []))
    courses.extend(dept.get("required_electives", []))
    courses.extend(dept.get("college_required_courses", []))
    courses.extend(dept.get("cross_group_required", []))
    courses.extend(dept.get("common_required_courses", []))
    for grp in dept.get("groups", []):
        courses.extend(get_all_required_courses(grp))
    for trk in dept.get("tracks", []):
        courses.extend(get_all_required_courses(trk))
    return courses


def validate_dept(dept_name: str, courses: list[dict], combined_text: str, pdf_paths: list[Path]) -> dict:
    result = {
        "dept": dept_name,
        "pdfs_found": [str(p.relative_to(BASE_DIR)) for p in pdf_paths],
        "matched": [],
        "json_only": [],
        "credit_mismatch": [],
        "no_code": [],
    }

    seen = set()
    for course in courses:
        code = course.get("code", "").strip()
        if not code:
            result["no_code"].append({"name": course.get("name"), "credits": course.get("credits")})
            continue
        # 主課號（去掉 alias 欄位中的斜線）
        primary = code.split("/")[0].strip()
        if primary in seen:
            continue
        seen.add(primary)

        # 蒐集所有等同課號
        aliases = [primary]
        for a in code.split("/")[1:]:
            aliases.append(a.strip())
        for a in course.get("alias", "").split("/"):
            a = a.strip()
            if a:
                aliases.append(a)

        in_pdf = any(find_code_in_text(a, combined_text) for a in aliases)
        entry = {"code": primary, "name": course.get("name"), "credits": course.get("credits")}

        if not in_pdf:
            result["json_only"].append(entry)
        else:
            # 找有出現的那個課號去抓學分
            active_code = next((a for a in aliases if find_code_in_text(a, combined_text)), primary)
            pdf_credit = find_credit_near_code(active_code, combined_text)
            json_credit = course.get("credits")
            if pdf_credit is not None and json_credit is not None and int(pdf_credit) != int(json_credit):
                result["credit_mismatch"].append({
                    **entry,
                    "pdf_credits": pdf_credit,
                    "json_credits": int(json_credit),
                })
            else:
                result["matched"].append(entry)

    return result


# ─── 遍歷 curriculum JSON ────────────────────────────────────────────────────

def iter_departments(data: dict):
    """
    yield (display_name, dept_object) for every leaf department/group/CBP.
    """
    for college in data.get("colleges", []):
        # 一般系所
        for dept in college.get("departments", []):
            yield dept["name"], dept
        # 學士班
        for cbp in college.get("college_bachelor_programs", []):
            yield cbp["name"], cbp


def main():
    with open(CURRICULUM_JSON, encoding="utf-8") as f:
        data = json.load(f)

    all_results = []
    depts = list(iter_departments(data))
    print(f"共 {len(depts)} 個系所/學士班需要驗證")

    for dept_name, dept_obj in depts:
        courses = get_all_required_courses(dept_obj)
        pdf_paths = find_pdf_for_dept(dept_name)

        if not pdf_paths:
            result = {
                "dept": dept_name,
                "pdfs_found": [],
                "matched": [],
                "json_only": [],
                "credit_mismatch": [],
                "no_code": [],
                "note": "找不到對應的 PDF，略過",
            }
            print(f"  ⚠ {dept_name}: 找不到 PDF")
            all_results.append(result)
            continue

        # 合併所有 PDF 文字
        combined_text = ""
        for pdf_path in pdf_paths:
            try:
                combined_text += extract_pdf_text(pdf_path) + "\n"
            except Exception as e:
                print(f"  ❌ {pdf_path.name} 讀取失敗：{e}")

        result = validate_dept(dept_name, courses, combined_text, pdf_paths)
        all_results.append(result)

        status = "✅" if not result["json_only"] and not result["credit_mismatch"] else "⚠️"
        print(f"  {status} {dept_name} "
              f"(✓{len(result['matched'])} / "
              f"⚠json_only={len(result['json_only'])} / "
              f"⚠credit={len(result['credit_mismatch'])})")

        if result["json_only"]:
            for c in result["json_only"]:
                print(f"      JSON 有 PDF 無: {c['code']} {c['name']}")
        if result["credit_mismatch"]:
            for c in result["credit_mismatch"]:
                print(f"      學分不符: {c['code']} JSON={c['json_credits']} PDF={c['pdf_credits']}")

    # 彙總
    summary = {
        "total_depts": len(all_results),
        "pdf_not_found": sum(1 for r in all_results if not r["pdfs_found"]),
        "has_json_only": sum(1 for r in all_results if r["json_only"]),
        "has_credit_mismatch": sum(1 for r in all_results if r["credit_mismatch"]),
        "fully_matched": sum(
            1 for r in all_results
            if r["pdfs_found"] and not r["json_only"] and not r["credit_mismatch"]
        ),
    }
    output = {"summary": summary, "results": all_results}

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 驗證報告已輸出至：{OUTPUT_PATH}")
    print(f"   總系所：{summary['total_depts']}，"
          f"無 PDF：{summary['pdf_not_found']}，"
          f"完整吻合：{summary['fully_matched']}，"
          f"JSON 有 PDF 無：{summary['has_json_only']}，"
          f"學分不符：{summary['has_credit_mismatch']}")


if __name__ == "__main__":
    main()
