"""
解析 raw/courses 和 raw/graduate_courses 的分發條件，
為每門課萃取結構化的選課資格屬性，
並將結果存為 data/processed/course_eligibility.json，
供後續更新知識圖譜節點使用。

輸出欄位說明（每門課一筆）：
  course_code          : 課號（去班別後綴）
  course_name          : 課程名稱
  dept                 : 系所
  semester             : 學期（1141 / 1142）
  eligible_years       : 可修課年級 list[int]，空 = 無限制
  program_types        : 學制限制 list[str]，空 = 無限制
  dept_include         : 指定系所（可修）list[str]
  dept_exclude         : 排除系所（不可修）list[str]
  college_include      : 指定學院 list[str]
  college_exclude      : 排除學院 list[str]
  open_to_minor        : 輔系學生可修 bool
  open_to_double_major : 雙主修學生可修 bool
  open_to_credit_prog  : 學分學程學生可修 bool
  open_to_2nd_spec     : 第二專長學生可修 bool
  open_to_cross_school : 申請校學士可修 bool
  priority_count       : 優先順序層數

使用方式：
  python scripts/graph/parse_distribution_conditions.py
"""

import json
import re
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent.parent.parent
COURSE_DIRS = [
    BASE / 'data' / 'raw' / 'courses' / '114_1',
    BASE / 'data' / 'raw' / 'courses' / '114_2',
    BASE / 'data' / 'raw' / 'graduate_courses' / '114_1',
    BASE / 'data' / 'raw' / 'graduate_courses' / '114_2',
]
OUTPUT = BASE / 'data' / 'processed' / 'course_eligibility.json'

# ── 中文數字對應 ──────────────────────────────────────────────────────────────

YEAR_MAP = {
    '一': 1, '二': 2, '三': 3, '四': 4,
    '五': 5, '六': 6, '七': 7, '八': 8,
}
ALL_YEARS = [1, 2, 3, 4]          # 學士班標準年級
GRAD_YEARS = [1, 2, 3, 4, 5]      # 研究所

# ── 學制標準化 ────────────────────────────────────────────────────────────────

PROGRAM_NORM = {
    '學士班':           'bachelor',
    '碩士班':           'master',
    '博士班':           'phd',
    '碩士在職專班':     'master_inservice',
    '產業碩士專班':     'master_industry',
    '碩士學位學程':     'master',
    '博士學位學程':     'phd',
}

def normalize_program(raw: str) -> list[str]:
    result = []
    for zh, en in PROGRAM_NORM.items():
        if zh in raw:
            result.append(en)
    return result or ['unknown']


# ── 年級解析 ──────────────────────────────────────────────────────────────────

def parse_years(year_text: str, is_grad: bool = False) -> list[int]:
    """
    解析「年級:限XXX」的值，回傳可修年級 list[int]。
    is_grad=True 時基準為研究所年級（1,2,3,4,5）。
    """
    base = GRAD_YEARS if is_grad else ALL_YEARS

    # 延修生單獨處理（非數字年級）
    is_延修 = '延修' in year_text

    # 找所有明確年級數字
    explicit_years = [YEAR_MAP[ch] for ch in YEAR_MAP if ch + '年級' in year_text]

    # 「非」模式：從全部中扣除
    if '非' in year_text:
        excluded = set()
        for ch, n in YEAR_MAP.items():
            if f'非{ch}年級' in year_text:
                excluded.add(n)
        result = [y for y in base if y not in excluded]
        if is_延修:
            result.append(99)  # 延修生標記
        return result

    # 正向模式
    result = sorted(set(explicit_years))
    if is_延修:
        result.append(99)
    if not result and '不限' in year_text:
        return base
    return result


# ── 分解單一條件說明 ──────────────────────────────────────────────────────────

def parse_course_codes(raw: str) -> list[str]:
    """從字串中萃取所有課號（如 CI1010、MA1003）"""
    return re.findall(r'[A-Z]{2}\d{4}', raw)


def parse_condition_text(text: str) -> dict:
    """
    解析一行 相關條件限制說明，回傳結構化 dict。
    格式：「學制:限XXX。系所:限YYY。年級:限ZZZ。指定課程:必須先修AA0000。」
    """
    result = {
        'years': [],
        'program_types': [],
        'dept_include': [],
        'dept_exclude': [],
        'college_include': [],
        'college_exclude': [],
        'open_to_minor': False,
        'minor_include': [],        # 輔系-XXX → 具體系所名稱
        'open_to_double_major': False,
        'double_major_include': [], # 雙主修-XXX → 具體系所名稱
        'open_to_credit_prog': False,
        'credit_prog_include': [],  # 學分學程-XXX → 具體學程名稱
        'open_to_2nd_spec': False,
        'spec_include': [],         # 第二專長-XXX → 具體專長名稱
        'open_to_cross_school': False,
        'identity_flags': [],
        # 指定課程 → 課程代碼關係
        'prereq_codes': [],    # 先修：修過才能選
        'coreq_codes': [],     # 同修：同學期一起選
        'conflict_codes': [],  # 擋修：已修過則不能再選（學分衝突/同質課）
        'forbidden_codes': [], # 禁修：禁止同時修（通常是同一課兩班別）
    }

    is_grad = any(k in text for k in ['碩士', '博士', '研究所'])

    # ── 年級 ──
    m = re.search(r'年級[:：](.+?)(?:[。]|$)', text)
    if m:
        result['years'] = parse_years(m.group(1), is_grad=is_grad)

    # ── 學制 ──
    m = re.search(r'學制[:：](.+?)(?:[。]|$)', text)
    if m:
        result['program_types'] = normalize_program(m.group(1))

    # ── 系所（複雜，含輔系/雙主修/學分學程/第二專長）──
    m = re.search(r'系所[:：]限(.+?)(?:[。]|$)', text)
    if m:
        dept_raw = m.group(1)
        # 以「、」分割各項
        for item in re.split(r'[、，,]', dept_raw):
            item = item.strip()
            if not item:
                continue

            # 特殊身份前綴
            if item.startswith('輔系-'):
                result['open_to_minor'] = True
                name = item[len('輔系-'):].strip()
                if name:
                    result['minor_include'].append(name)
            elif item.startswith('雙主修-'):
                result['open_to_double_major'] = True
                name = item[len('雙主修-'):].strip()
                if name:
                    result['double_major_include'].append(name)
            elif item.startswith('學分學程-'):
                result['open_to_credit_prog'] = True
                name = item[len('學分學程-'):].strip()
                if name:
                    result['credit_prog_include'].append(name)
            elif item.startswith('第二專長-'):
                result['open_to_2nd_spec'] = True
                name = item[len('第二專長-'):].strip()
                if name:
                    result['spec_include'].append(name)
            elif item.startswith('非'):
                # 排除系所（去掉前綴「非」）
                result['dept_exclude'].append(item[1:])
            else:
                # 一般系所（含研究所、學位學程等）
                result['dept_include'].append(item)

    # ── 學院 ──
    m = re.search(r'學院[:：]限(.+?)(?:[。]|$)', text)
    if m:
        college_raw = m.group(1)
        for item in re.split(r'[、，,]', college_raw):
            item = item.strip()
            if not item:
                continue
            if item.startswith('非'):
                result['college_exclude'].append(item[1:])
            else:
                result['college_include'].append(item)

    # ── 身份 ──
    m = re.search(r'身份[:：]限(.+?)(?:[。]|$)', text)
    if m:
        identity_raw = m.group(1)
        if '校學士' in identity_raw:
            result['open_to_cross_school'] = True
        if '非僑生' in identity_raw or '非交換生' in identity_raw:
            result['identity_flags'].append('not_exchange')
        if '交換生' in identity_raw and '非' not in identity_raw:
            result['identity_flags'].append('exchange_only')
        if '外籍生' in identity_raw and '非' not in identity_raw:
            result['identity_flags'].append('foreign_only')
        if '重修生' in identity_raw and '非' not in identity_raw:
            result['identity_flags'].append('retake_only')

    # ── 指定課程（先修 / 同修 / 擋修 / 禁修）──
    m = re.search(r'指定課程[:：](.+?)(?:[。]|$)', text)
    if m:
        course_raw = m.group(1)
        # 依「、」切分後逐段判斷動詞類型
        # 每段格式：「(必須)?先修XXNNNN」、「禁修XXNNNN」…
        # 先找所有 動詞+課號 片段
        for seg in re.split(r'[、，,]', course_raw):
            seg = seg.strip()
            codes = parse_course_codes(seg)
            if not codes:
                continue
            if '同修' in seg:        # 先判斷「同修」，避免「含先修」被誤分類
                result['coreq_codes'].extend(codes)
            elif '先修' in seg:
                result['prereq_codes'].extend(codes)
            elif '擋修' in seg:
                result['conflict_codes'].extend(codes)
            elif '禁修' in seg:
                result['forbidden_codes'].extend(codes)

    return result


# ── 彙整多優先序的結果 ────────────────────────────────────────────────────────

def merge_priorities(priority_results: list[dict]) -> dict:
    """
    將多個優先序的解析結果取聯集，代表「任一條件符合即可修」。
    years 為空表示全年級皆可。
    課程關係（先修/同修/擋修/禁修）跨優先序取聯集。
    """
    merged = {
        'eligible_years': set(),
        'program_types': set(),
        'dept_include': set(),
        'dept_exclude': set(),
        'college_include': set(),
        'college_exclude': set(),
        'open_to_minor': False,
        'minor_include': set(),
        'open_to_double_major': False,
        'double_major_include': set(),
        'open_to_credit_prog': False,
        'credit_prog_include': set(),
        'open_to_2nd_spec': False,
        'spec_include': set(),
        'open_to_cross_school': False,
        'prereq_codes': set(),
        'coreq_codes': set(),
        'conflict_codes': set(),
        'forbidden_codes': set(),
    }

    all_years_unrestricted = False

    for r in priority_results:
        if not r['years']:
            all_years_unrestricted = True
        else:
            merged['eligible_years'].update(r['years'])

        if r['program_types']:
            merged['program_types'].update(r['program_types'])

        merged['dept_include'].update(r['dept_include'])
        merged['dept_exclude'].update(r['dept_exclude'])
        merged['college_include'].update(r['college_include'])
        merged['college_exclude'].update(r['college_exclude'])

        if r['open_to_minor']:
            merged['open_to_minor'] = True
            merged['minor_include'].update(r['minor_include'])
        if r['open_to_double_major']:
            merged['open_to_double_major'] = True
            merged['double_major_include'].update(r['double_major_include'])
        if r['open_to_credit_prog']:
            merged['open_to_credit_prog'] = True
            merged['credit_prog_include'].update(r['credit_prog_include'])
        if r['open_to_2nd_spec']:
            merged['open_to_2nd_spec'] = True
            merged['spec_include'].update(r['spec_include'])
        if r['open_to_cross_school']: merged['open_to_cross_school'] = True

        merged['prereq_codes'].update(r['prereq_codes'])
        merged['coreq_codes'].update(r['coreq_codes'])
        merged['conflict_codes'].update(r['conflict_codes'])
        merged['forbidden_codes'].update(r['forbidden_codes'])

    if all_years_unrestricted:
        merged['eligible_years'] = []
    else:
        merged['eligible_years'] = sorted(merged['eligible_years'])

    return {
        'eligible_years':        merged['eligible_years'],
        'program_types':         sorted(merged['program_types']),
        'dept_include':          sorted(merged['dept_include']),
        'dept_exclude':          sorted(merged['dept_exclude']),
        'college_include':       sorted(merged['college_include']),
        'college_exclude':       sorted(merged['college_exclude']),
        'open_to_minor':         merged['open_to_minor'],
        'minor_include':         sorted(merged['minor_include']),
        'open_to_double_major':  merged['open_to_double_major'],
        'double_major_include':  sorted(merged['double_major_include']),
        'open_to_credit_prog':   merged['open_to_credit_prog'],
        'credit_prog_include':   sorted(merged['credit_prog_include']),
        'open_to_2nd_spec':      merged['open_to_2nd_spec'],
        'spec_include':          sorted(merged['spec_include']),
        'open_to_cross_school':  merged['open_to_cross_school'],
        'prereq_codes':          sorted(merged['prereq_codes']),
        'coreq_codes':           sorted(merged['coreq_codes']),
        'conflict_codes':        sorted(merged['conflict_codes']),
        'forbidden_codes':       sorted(merged['forbidden_codes']),
    }


# ── 主程式 ────────────────────────────────────────────────────────────────────

def main():
    # 用 (course_code, semester) 做 key 避免重複
    results: dict[tuple, dict] = {}

    total = no_condition = 0

    for d in COURSE_DIRS:
        # 從路徑判斷學期
        sem = d.parent.name + d.name  # e.g. "courses114_1"（用於 debug）
        for f in sorted(d.glob('*.json')):
            data = json.loads(f.read_text(encoding='utf-8'))
            for c in data:
                total += 1
                raw_code = c.get('課號-班別', '').split('-')[0]
                if not raw_code:
                    continue

                cond_data = c.get('分發條件') or {}
                priorities = cond_data.get('優先順序列表', [])

                # 原文條件（每個班別的條件列表，格式：「P1: <text> | P2: <text>」）
                raw_cond_str = ' | '.join(
                    f'P{p.get("優先順序","?")}: {p.get("相關條件限制說明","").strip()}'
                    for p in priorities
                ) if priorities else ''

                if not priorities:
                    no_condition += 1
                    # 無分發條件 = 無限制
                    parsed = {
                        'eligible_years': [],
                        'program_types': [],
                        'dept_include': [],
                        'dept_exclude': [],
                        'college_include': [],
                        'college_exclude': [],
                        'open_to_minor': False,
                        'minor_include': [],
                        'open_to_double_major': False,
                        'double_major_include': [],
                        'open_to_credit_prog': False,
                        'credit_prog_include': [],
                        'open_to_2nd_spec': False,
                        'spec_include': [],
                        'open_to_cross_school': False,
                        'prereq_codes': [],
                        'coreq_codes': [],
                        'conflict_codes': [],
                        'forbidden_codes': [],
                        'priority_count': 0,
                    }
                else:
                    priority_results = []
                    for p in priorities:
                        text = p.get('相關條件限制說明', '').strip()
                        if text:
                            priority_results.append(parse_condition_text(text))
                    parsed = merge_priorities(priority_results)
                    parsed['priority_count'] = len(priorities)

                key = (raw_code, c.get('學年度', ''), c.get('學期', ''))
                # 同課號不同班別：合併（取聯集）
                if key in results:
                    existing = results[key]
                    # 取年級聯集
                    if existing['eligible_years'] and parsed['eligible_years']:
                        existing['eligible_years'] = sorted(
                            set(existing['eligible_years']) | set(parsed['eligible_years'])
                        )
                    else:
                        existing['eligible_years'] = []  # 至少一個無限制 → 無限制
                    # 合併系所、學院、學制、身份細目、課程代碼（取聯集）
                    for list_field in ['dept_include', 'dept_exclude',
                                       'college_include', 'college_exclude',
                                       'program_types',
                                       'minor_include', 'double_major_include',
                                       'credit_prog_include', 'spec_include',
                                       'prereq_codes', 'coreq_codes',
                                       'conflict_codes', 'forbidden_codes']:
                        merged_set = set(existing[list_field]) | set(parsed[list_field])
                        existing[list_field] = sorted(merged_set)
                    for flag in ['open_to_minor', 'open_to_double_major',
                                 'open_to_credit_prog', 'open_to_2nd_spec',
                                 'open_to_cross_school']:
                        if parsed[flag]:
                            existing[flag] = True
                    # 取最大優先序數
                    existing['priority_count'] = max(
                        existing['priority_count'], parsed['priority_count']
                    )
                    # 累積原文（不同班別以換行分隔，去重）
                    if raw_cond_str:
                        existing_raws = existing.get('raw_conditions', [])
                        if raw_cond_str not in existing_raws:
                            existing_raws.append(raw_cond_str)
                        existing['raw_conditions'] = existing_raws
                else:
                    results[key] = {
                        'course_code':  raw_code,
                        'course_name':  c.get('課程名稱(中文)', ''),
                        'dept':         c.get('系所', ''),
                        'academic_year':c.get('學年度', ''),
                        'semester':     c.get('學期', ''),
                        **parsed,
                        'raw_conditions': [raw_cond_str] if raw_cond_str else [],
                    }

    output_list = sorted(results.values(), key=lambda x: x['course_code'])
    OUTPUT.write_text(
        json.dumps(output_list, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    # 統計
    has_year    = sum(1 for r in output_list if r['eligible_years'])
    has_prog    = sum(1 for r in output_list if r['program_types'])
    has_minor   = sum(1 for r in output_list if r['open_to_minor'])
    has_dbl     = sum(1 for r in output_list if r['open_to_double_major'])
    has_cp      = sum(1 for r in output_list if r['open_to_credit_prog'])
    has_cs      = sum(1 for r in output_list if r['open_to_cross_school'])
    has_prereq  = sum(1 for r in output_list if r['prereq_codes'])
    has_coreq   = sum(1 for r in output_list if r['coreq_codes'])
    has_conflict = sum(1 for r in output_list if r['conflict_codes'])
    has_forbid  = sum(1 for r in output_list if r['forbidden_codes'])

    print(f'處理課程：{total} 門 → 去重後 {len(output_list)} 個課號')
    print(f'無分發條件（全部開放）：{no_condition} 門')
    print()
    print(f'有年級限制：       {has_year} 個課號')
    print(f'有學制限制：       {has_prog} 個課號')
    print(f'輔系可修：         {has_minor} 個課號')
    print(f'雙主修可修：       {has_dbl} 個課號')
    print(f'學分學程可修：     {has_cp} 個課號')
    print(f'申請校學士可修：   {has_cs} 個課號')
    print()
    print(f'有先修課程要求：   {has_prereq} 個課號')
    print(f'有同修課程要求：   {has_coreq} 個課號')
    print(f'有擋修課程限制：   {has_conflict} 個課號')
    print(f'有禁修課程限制：   {has_forbid} 個課號')
    print()
    print(f'輸出：{OUTPUT}')

    # 印幾個範例確認解析正確
    print('\n=== 解析範例（有年級+學制限制）===')
    examples = [r for r in output_list if r['eligible_years'] and r['program_types']][:2]
    for ex in examples:
        print(f'  {ex["course_code"]} {ex["course_name"][:20]}')
        print(f'    eligible_years={ex["eligible_years"]}  program_types={ex["program_types"]}')

    print('\n=== 解析範例（有先修課程）===')
    examples = [r for r in output_list if r['prereq_codes']][:3]
    for ex in examples:
        print(f'  {ex["course_code"]} {ex["course_name"][:20]}')
        print(f'    prereq_codes={ex["prereq_codes"]}')

    print('\n=== 解析範例（有擋修課程）===')
    examples = [r for r in output_list if r['conflict_codes']][:3]
    for ex in examples:
        print(f'  {ex["course_code"]} {ex["course_name"][:20]}')
        print(f'    conflict_codes={ex["conflict_codes"]}')
    print()


if __name__ == '__main__':
    main()
