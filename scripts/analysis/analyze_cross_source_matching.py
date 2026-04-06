"""
跨資料源課程比對分析
分析 raw/courses + raw/graduate_courses、curriculum_requirements_114.json、credit_programs/*.json
三源之間的課號與課名吻合情況。

使用方式：python scripts/analysis/analyze_cross_source_matching.py
輸出：data/processed/validation/cross_source_matching.json
"""

import json
import re
import unicodedata
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent.parent.parent


# ─── 標準化函式 ─────────────────────────────────────────────────────────────

def norm_name(s: str) -> str:
    """
    正規化課程名稱，用於模糊比對：
    - NFKC Unicode 正規化（消除全形/半形、CJK 相容字形差異）
    - 移除空格、括號、符號
    - 移除上/下學期後綴（上、下、I~X、Ⅰ~Ⅹ、(一)~(十)）
    - 移除 [已停開] 標記
    """
    s = unicodedata.normalize('NFKC', s or '')
    s = re.sub(r'\[已停開\]', '', s)
    s = re.sub(r'[\s\u3000「」【】()（）\-_·・]', '', s)
    # 學期後綴（須在移除括號後再處理）
    s = re.sub(r'[上下]$', '', s)
    s = re.sub(r'[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹ]$', '', s)
    s = re.sub(r'[一二三四五六七八九十]$', '', s)
    s = re.sub(r'[IVX]+$', '', s)
    return s.strip().lower()


def dept_prefix(code: str) -> str:
    """提取課號的系所英文前綴，如 CE2001 → CE"""
    m = re.match(r'^([A-Za-z]+)', code)
    return m.group(1).upper() if m else ''


def strip_section(raw_code: str) -> str:
    """移除課號班別後綴：CE2001-A → CE2001，CE1001-* → CE1001"""
    return re.sub(r'-[A-Z0-9*]+$', '', raw_code.strip())


# ─── 載入資料 ────────────────────────────────────────────────────────────────

def load_raw_courses() -> tuple[dict, dict, dict]:
    """
    載入 data/raw/courses/、data/raw/graduate_courses/（兩學期）
    以及 data/raw/scraped_missing/courses.json（補爬資料）。
    回傳：
      raw_by_code        : code → {'name': str, 'norm': str, 'level': 'ugrad'|'grad'|'scraped'}
      raw_by_prefix_norm : (prefix, norm_name) → [code]
      raw_by_norm        : norm_name → [code]
    """
    raw_by_code = {}
    raw_by_prefix_norm = defaultdict(list)
    raw_by_norm = defaultdict(list)

    def register(code, name, level):
        if not code or code in raw_by_code:
            return
        n = norm_name(name)
        raw_by_code[code] = {'name': name, 'norm': n, 'level': level}
        raw_by_prefix_norm[(dept_prefix(code), n)].append(code)
        raw_by_norm[n].append(code)

    # 原始課程資料（114_1 / 114_2）
    for subdir, level in [('courses', 'ugrad'), ('graduate_courses', 'grad')]:
        for sem in ['114_1', '114_2']:
            d = BASE / 'data' / 'raw' / subdir / sem
            if not d.exists():
                continue
            for f in d.glob('*.json'):
                for c in json.loads(f.read_text(encoding='utf-8')):
                    register(
                        strip_section(c.get('課號-班別', '')),
                        c.get('課程名稱(中文)', '').strip(),
                        level,
                    )

    # 補爬資料（scraped_missing）
    scraped_path = BASE / 'data' / 'raw' / 'scraped_missing' / 'courses.json'
    if scraped_path.exists():
        for c in json.loads(scraped_path.read_text(encoding='utf-8')):
            if c.get('_not_found') or c.get('_error'):
                continue
            code = strip_section(c.get('課號-班別', ''))
            # 依課號數字判斷大學部/研究所
            num_m = re.search(r'(\d+)', code)
            num = int(num_m.group(1)) if num_m else 0
            level = 'scraped_grad' if num >= 5000 else 'scraped_ugrad'
            register(code, c.get('課程名稱(中文)', '').strip(), level)

    return raw_by_code, dict(raw_by_prefix_norm), dict(raw_by_norm)


def load_curriculum() -> dict:
    """
    載入 curriculum_requirements_114.json
    回傳 code → {'name': str, 'source_dept': str, 'source_college': str}
    """
    path = BASE / 'data' / 'processed' / 'curriculum_requirements_114.json'
    data = json.loads(path.read_text(encoding='utf-8'))

    def iter_courses(obj, college_name, dept_name):
        for key in ['required_courses', 'required_electives', 'college_required_courses',
                    'cross_group_required', 'common_required_courses']:
            for c in obj.get(key, []):
                yield c, college_name, dept_name
        for g in obj.get('groups', []) + obj.get('tracks', []):
            yield from iter_courses(g, college_name, dept_name)

    result = {}
    for col in data.get('colleges', []):
        col_name = col.get('name', '')
        for dept in col.get('departments', []) + col.get('college_bachelor_programs', []):
            dept_name = dept.get('name', '')
            for c, cn, dn in iter_courses(dept, col_name, dept_name):
                code = c.get('code', '').strip().split('/')[0].strip()
                if code and code not in result:
                    result[code] = {
                        'name': c.get('name', '').strip(),
                        'source_dept': dn,
                        'source_college': cn,
                    }
    return result


def load_credit_programs() -> dict:
    """
    載入 credit_programs/*.json
    回傳 code → {'name': str, 'source_program': str, 'source_college': str}
    """
    result = {}
    for f in (BASE / 'data' / 'processed' / 'credit_programs').glob('*.json'):
        programs = json.loads(f.read_text(encoding='utf-8'))
        for prog in programs:
            prog_name = prog.get('name', '')
            prog_college = prog.get('college', '')
            for c in prog.get('required_courses', []):
                code = c.get('code', '').strip().split('/')[0].strip()
                if code and code not in result:
                    result[code] = {
                        'name': c.get('name', '').strip(),
                        'source_program': prog_name,
                        'source_college': prog_college,
                    }
            for grp in prog.get('elective_groups', []):
                grp_name = grp.get('name', '')
                for c in grp.get('courses', []):
                    code = c.get('code', '').strip().split('/')[0].strip()
                    if code and code not in result:
                        result[code] = {
                            'name': c.get('name', '').strip(),
                            'source_program': prog_name,
                            'source_college': prog_college,
                            'source_group': grp_name,
                        }
                for slot in grp.get('slots', []):
                    for c in slot.get('courses', []):
                        code = c.get('code', '').strip().split('/')[0].strip()
                        if code and code not in result:
                            result[code] = {
                                'name': c.get('name', '').strip(),
                                'source_program': prog_name,
                                'source_college': prog_college,
                                'source_group': grp_name,
                            }
    return result


# ─── 課名比對 ────────────────────────────────────────────────────────────────

def find_by_name(src_code: str, src_name: str,
                 raw_by_prefix_norm: dict, raw_by_norm: dict) -> tuple[list, str]:
    """
    嘗試以正規化課名在 raw/courses 中找對應課號。
    優先：同系所前綴 + 課名完全吻合
    次選：任何前綴課名完全吻合
    回傳 (matching_codes, method)
    """
    n = norm_name(src_name)
    prefix = dept_prefix(src_code)
    same_prefix = raw_by_prefix_norm.get((prefix, n), [])
    if same_prefix:
        return same_prefix, 'same_prefix'
    any_prefix = raw_by_norm.get(n, [])
    if any_prefix:
        return any_prefix, 'any_prefix'
    return [], 'none'


# ─── 分類函式 ────────────────────────────────────────────────────────────────

def classify_unmatched(code: str, name: str,
                        raw_by_prefix_norm: dict, raw_by_norm: dict) -> dict:
    matches, how = find_by_name(code, name, raw_by_prefix_norm, raw_by_norm)
    num_m = re.search(r'(\d+)', code)
    num = int(num_m.group(1)) if num_m else 0
    level = 'grad' if num >= 5000 else 'undergrad'

    return {
        'code': code,
        'name': name,
        'level': level,
        'name_match': how,
        'name_match_codes': matches,
    }


# ─── 主程式 ─────────────────────────────────────────────────────────────────

def main():
    print("載入資料中...")
    raw_by_code, raw_by_prefix_norm, raw_by_norm = load_raw_courses()
    curr_courses = load_curriculum()
    cp_courses = load_credit_programs()

    ugrad_cnt  = sum(1 for v in raw_by_code.values() if v['level'] == 'ugrad')
    grad_cnt   = sum(1 for v in raw_by_code.values() if v['level'] == 'grad')
    sc_u_cnt   = sum(1 for v in raw_by_code.values() if v['level'] == 'scraped_ugrad')
    sc_g_cnt   = sum(1 for v in raw_by_code.values() if v['level'] == 'scraped_grad')
    print(f"raw/courses (大學部):      {ugrad_cnt} 課號")
    print(f"raw/graduate_courses:      {grad_cnt} 課號")
    print(f"scraped_missing (大學部):  {sc_u_cnt} 課號")
    print(f"scraped_missing (研究所):  {sc_g_cnt} 課號")
    print(f"raw 合計:                  {len(raw_by_code)} 課號")
    print(f"curriculum_requirements: {len(curr_courses)} 課號")
    print(f"credit_programs:         {len(cp_courses)} 課號")

    # ── 課號層比對 ───────────────────────────────────────────────────────────
    curr_in_raw  = {c for c in curr_courses if c in raw_by_code}
    curr_only    = {c for c in curr_courses if c not in raw_by_code}
    cp_in_raw    = {c for c in cp_courses if c in raw_by_code}
    cp_only      = {c for c in cp_courses if c not in raw_by_code}

    # 課號吻合但課名不一致
    curr_name_diff = []
    for c in sorted(curr_in_raw):
        info = curr_courses[c]
        n1 = norm_name(info['name'])
        n2 = raw_by_code[c]['norm']
        if n1 != n2:
            curr_name_diff.append({
                'code': c,
                'curriculum_name': info['name'],
                'raw_name': raw_by_code[c]['name'],
                'source_dept': info['source_dept'],
                'source_college': info['source_college'],
            })

    cp_name_diff = []
    for c in sorted(cp_in_raw):
        info = cp_courses[c]
        n1 = norm_name(info['name'])
        n2 = raw_by_code[c]['norm']
        if n1 != n2:
            cp_name_diff.append({
                'code': c,
                'cp_name': info['name'],
                'raw_name': raw_by_code[c]['name'],
                'source_program': info['source_program'],
                'source_college': info['source_college'],
            })

    # ── 課名匹配補救：curr_only & cp_only ───────────────────────────────────
    def curr_entry(c):
        info = curr_courses[c]
        base = classify_unmatched(c, info['name'], raw_by_prefix_norm, raw_by_norm)
        base['source_dept']    = info['source_dept']
        base['source_college'] = info['source_college']
        return base

    def cp_entry(c):
        info = cp_courses[c]
        base = classify_unmatched(c, info['name'], raw_by_prefix_norm, raw_by_norm)
        base['source_program'] = info['source_program']
        base['source_college'] = info['source_college']
        if 'source_group' in info:
            base['source_group'] = info['source_group']
        return base

    curr_only_analysis = [curr_entry(c) for c in sorted(curr_only)]
    cp_only_analysis   = [cp_entry(c)   for c in sorted(cp_only)]

    cp_name_same   = [x for x in cp_only_analysis if x['name_match'] == 'same_prefix']
    cp_name_any    = [x for x in cp_only_analysis if x['name_match'] == 'any_prefix']
    cp_name_none   = [x for x in cp_only_analysis if x['name_match'] == 'none']
    # 非標準格式課號（2-4字母+4-5數字以外）
    cp_non_std     = [x for x in cp_name_none
                      if not re.match(r'^[A-Za-z]{2,4}\d{4,5}$', x['code'])]
    cp_std_none    = [x for x in cp_name_none
                      if re.match(r'^[A-Za-z]{2,4}\d{4,5}$', x['code'])]
    cp_grad_none   = [x for x in cp_std_none if x['level'] == 'grad']
    cp_ugrad_none  = [x for x in cp_std_none if x['level'] == 'undergrad']

    # ── 輸出 JSON ────────────────────────────────────────────────────────────
    output = {
        "summary": {
            "raw_courses_total": len(raw_by_code),
            "curriculum_total": len(curr_courses),
            "credit_programs_total": len(cp_courses),
            "curriculum_vs_raw": {
                "code_match": len(curr_in_raw),
                "code_match_pct": round(len(curr_in_raw) / len(curr_courses) * 100, 1),
                "code_only_in_curriculum": len(curr_only),
                "name_diff_count": len(curr_name_diff),
            },
            "credit_programs_vs_raw": {
                "code_match": len(cp_in_raw),
                "code_match_pct": round(len(cp_in_raw) / len(cp_courses) * 100, 1),
                "code_only_in_cp": len(cp_only),
                "name_diff_count": len(cp_name_diff),
                "cp_only_name_match_same_prefix": len(cp_name_same),
                "cp_only_name_match_any_prefix": len(cp_name_any),
                "cp_only_non_standard_code": len(cp_non_std),
                "cp_only_name_no_match_grad": len(cp_grad_none),
                "cp_only_name_no_match_undergrad": len(cp_ugrad_none),
                "total_matchable": len(cp_in_raw) + len(cp_name_same) + len(cp_name_any),
                "total_matchable_pct": round(
                    (len(cp_in_raw) + len(cp_name_same) + len(cp_name_any)) / len(cp_courses) * 100, 1),
            },
        },
        "curriculum_name_diff": curr_name_diff,
        "cp_name_diff": cp_name_diff,
        "curriculum_only": curr_only_analysis,
        "cp_only_name_matched_same_prefix": cp_name_same,
        "cp_only_name_matched_any_prefix": cp_name_any,
        "cp_only_non_standard_code": cp_non_std,
        "cp_only_no_match_grad": cp_grad_none,
        "cp_only_no_match_undergrad": cp_ugrad_none,
    }

    out_path = BASE / 'data' / 'processed' / 'validation' / 'cross_source_matching.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n✅ 分析報告已輸出至：{out_path}")

    # ── 印出摘要 ─────────────────────────────────────────────────────────────
    s = output['summary']
    print("\n" + "=" * 60)
    print("【curriculum_requirements vs raw（大學部+研究所）】")
    print(f"  課號吻合：{s['curriculum_vs_raw']['code_match']} / {s['curriculum_total']}"
          f" = {s['curriculum_vs_raw']['code_match_pct']}%")
    print(f"  課號不在 raw：{s['curriculum_vs_raw']['code_only_in_curriculum']} 筆")
    print(f"  課號吻合但課名有差：{s['curriculum_vs_raw']['name_diff_count']} 筆（多為上/下學期後綴，預期行為）")

    cv = s['credit_programs_vs_raw']
    print("\n【credit_programs vs raw（大學部+研究所）】")
    print(f"  課號直接匹配：{cv['code_match']} / {s['credit_programs_total']}"
          f" = {cv['code_match_pct']}%")
    print(f"  課號不在 raw：{cv['code_only_in_cp']} 筆")
    print(f"    └ 課名匹配補救（同系所前綴）：{cv['cp_only_name_match_same_prefix']} 筆")
    print(f"    └ 課名匹配補救（跨前綴）：   {cv['cp_only_name_match_any_prefix']} 筆")
    print(f"    └ 非標準格式課號：           {cv['cp_only_non_standard_code']} 筆（特殊學程，無對應）")
    print(f"    └ 標準格式仍缺失（研究所）：  {cv['cp_only_name_no_match_grad']} 筆")
    print(f"    └ 標準格式仍缺失（大學部）：  {cv['cp_only_name_no_match_undergrad']} 筆（隔年/停開）")
    print(f"  合計可匹配：{cv['total_matchable']} / {s['credit_programs_total']}"
          f" = {cv['total_matchable_pct']}%")

    print("\n【建圖策略建議】")
    print("  主鍵：課號（code）比對；課名作為輔助驗證")
    print("  課名後綴差異（上/下）→ 同一 Course 節點，兩學期各有一條邊")
    print(f"  課名匹配成功 {cv['cp_only_name_match_same_prefix']+cv['cp_only_name_match_any_prefix']} 門 → 建立 MAPS_TO 邊")
    print(f"  非標準格式 {cv['cp_only_non_standard_code']} 門 → 建立 Course 節點，標記 source=special_program")
    print(f"  研究所仍缺失 {cv['cp_only_name_no_match_grad']} 門 → 建立 Course 節點，source=cp_only，level=grad")
    print(f"  大學部仍缺失 {cv['cp_only_name_no_match_undergrad']} 門 → 建立 Course 節點，source=cp_only，needs_review=true")


if __name__ == '__main__':
    main()
