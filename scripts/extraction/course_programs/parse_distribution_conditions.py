"""
解析 raw/courses 和 raw/graduate_courses 的分發條件，
為每門課萃取結構化的選課資格屬性。

輸出格式（v2）：每筆記錄分三個語意 block：

  eligibility          : 修課資格限制（誰可以修）
    is_unrestricted    : bool  無任何系所/學院/年級/學制限制 → 全校可修
    eligible_years     : list[int]   可修年級，空 = 無年級限制
    program_types      : list[str]   學制限制（bachelor/master/phd/...）
    dept_include       : list[str]   指定可修系所
    dept_exclude       : list[str]   排除系所
    college_include    : list[str]   指定可修學院
    college_exclude    : list[str]   排除學院
    open_to_minor      : bool        輔系可修
    minor_include      : list[str]   輔系細目（空 = 全部輔系）
    open_to_double_major: bool       雙主修可修
    double_major_include: list[str]
    open_to_credit_prog: bool        學分學程可修
    credit_prog_include: list[str]
    open_to_2nd_spec   : bool        第二專長可修
    spec_include       : list[str]
    open_to_edu_program: bool        教育學程可修
    edu_program_include: list[str]
    open_to_cross_school: bool       申請校學士可修
    identity_flags     : list[str]   其他身份旗標
    priority_count     : int         優先順序層數（批次數）
    has_special_condition: bool      含無法完全結構化的條件
    has_conditional_prereq: bool     先修只在部分優先序存在（非絕對要求）

  course_relations     : 課程依賴關係（for 知識圖譜邊）
    prereq_codes       : list[str]   先修課號（修過才能選）
    coreq_codes        : list[str]   同修課號（同學期一起修）
    conflict_codes     : list[str]   擋修課號（已修不能再修）
    forbidden_codes    : list[str]   禁修課號（禁止同時修）

  raw_conditions       : list[str]   原始優先序文字（供 debug / 前端顯示）
  unparseable_conditions: list[str]  無法結構化解析的條件片段

使用方式：
  python scripts/extraction/course_programs/parse_distribution_conditions.py
"""

import json
import re
from pathlib import Path

BASE = Path(__file__).parent.parent.parent.parent
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
ALL_YEARS = [1, 2, 3, 4]
GRAD_YEARS = [1, 2, 3, 4, 5]

# ── 學制標準化 ────────────────────────────────────────────────────────────────

PROGRAM_NORM = {
    '學士班':       'bachelor',
    '碩士班':       'master',
    '博士班':       'phd',
    '碩士在職專班': 'master_inservice',
    '產業碩士專班': 'master_industry',
    '碩士學位學程': 'master',
    '博士學位學程': 'phd',
}

def normalize_program(raw: str) -> list[str]:
    result = []
    for zh, en in PROGRAM_NORM.items():
        if zh in raw:
            result.append(en)
    return result or ['unknown']


# ── 已知的系所前綴（特殊身份類型）────────────────────────────────────────────

# 格式：前綴字串 → (open_to_flag, include_list_key)
SPECIAL_PREFIXES: dict[str, tuple[str, str]] = {
    '輔系-':     ('open_to_minor',         'minor_include'),
    '雙主修-':   ('open_to_double_major',   'double_major_include'),
    '學分學程-': ('open_to_credit_prog',    'credit_prog_include'),
    '第二專長-': ('open_to_2nd_spec',       'spec_include'),
    '教育學程-': ('open_to_edu_program',    'edu_program_include'),
}

# ── 年級解析 ──────────────────────────────────────────────────────────────────

def parse_years(year_text: str, is_grad: bool = False) -> list[int]:
    base = GRAD_YEARS if is_grad else ALL_YEARS
    is_延修 = '延修' in year_text
    explicit_years = [YEAR_MAP[ch] for ch in YEAR_MAP if ch + '年級' in year_text]

    if '非' in year_text:
        excluded = set()
        for ch, n in YEAR_MAP.items():
            if f'非{ch}年級' in year_text:
                excluded.add(n)
        result = [y for y in base if y not in excluded]
        if is_延修:
            result.append(99)
        return result

    result = sorted(set(explicit_years))
    if is_延修:
        result.append(99)
    if not result and '不限' in year_text:
        return base
    return result


# ── 課號萃取 ──────────────────────────────────────────────────────────────────

def parse_course_codes(raw: str) -> list[str]:
    return re.findall(r'[A-Z]{2}\d{4}', raw)


# ── 無法解析的殘餘條件萃取 ───────────────────────────────────────────────────

def extract_unparseable(text: str) -> list[str]:
    """
    移除已知可結構化解析的條件片段後，回傳剩餘的原文片段。
    主要用於捕捉「且檢定指定課程平均成績達50分以上」等複雜限制。
    """
    cleaned = text
    # 移除已知 pattern（含句號）
    for pattern in [
        r'年級[:：].+?(?:[。]|$)',
        r'學制[:：].+?(?:[。]|$)',
        r'系所[:：]限.+?(?:[。]|$)',
        r'學院[:：]限.+?(?:[。]|$)',
        r'身份[:：]限.+?(?:[。]|$)',
        r'班別[:：]限.+?(?:[。]|$)',
        r'性別[:：]限.+?(?:[。]|$)',
        r'學號[:：]限.+?(?:[。]|$)',
        r'指定課程[:：].+?(?:[。]|$)',
    ]:
        cleaned = re.sub(pattern, '', cleaned)
    # 整理殘餘片段
    fragments = []
    for seg in re.split(r'[。]', cleaned):
        seg = seg.strip().lstrip('且').strip()
        if seg and len(seg) > 2:   # 過濾掉太短的雜訊（標點等）
            fragments.append(seg)
    return fragments


# ── 解析單一條件說明 ──────────────────────────────────────────────────────────

def parse_condition_text(text: str) -> dict:
    """
    解析一行「相關條件限制說明」，回傳結構化 dict。
    回傳欄位分成三類：
      - 修課資格欄位（年級、學制、系所、學院、特殊身份）
      - 課程關係欄位（先修、同修、擋修、禁修的課號）
      - unparseable（殘餘無法解析的原文片段）
    """
    result = {
        # 修課資格
        'years': [],
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
        'open_to_edu_program': False,
        'edu_program_include': [],
        'open_to_cross_school': False,
        'identity_flags': [],
        'section_include': [],    # 班別限制（A/B/C）
        'gender_restriction': [], # 性別限制（male/female）
        'student_id_parity': [],  # 學號奇偶（odd/even）
        # 課程關係
        'prereq_codes': [],
        'coreq_codes': [],
        'conflict_codes': [],
        'forbidden_codes': [],
        # 殘餘
        'unparseable': [],
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

    # ── 系所（含特殊身份前綴）──
    m = re.search(r'系所[:：]限(.+?)(?:[。]|$)', text)
    if m:
        dept_raw = m.group(1)
        for item in re.split(r'[、，,]', dept_raw):
            item = item.strip()
            if not item:
                continue

            # 嘗試比對所有已知特殊前綴
            matched_prefix = False
            for prefix, (flag_key, include_key) in SPECIAL_PREFIXES.items():
                if item.startswith(prefix):
                    result[flag_key] = True
                    name = item[len(prefix):].strip()
                    if name:
                        result[include_key].append(name)
                    matched_prefix = True
                    break

            if not matched_prefix:
                # 排除系所
                if item.startswith('非'):
                    result['dept_exclude'].append(item[1:])
                else:
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

    # ── 班別 ──
    m = re.search(r'班別[:：]限(.+?)(?:[。]|$)', text)
    if m:
        for item in re.split(r'[、，,]', m.group(1)):
            item = item.strip()
            if item:
                result['section_include'].append(item)

    # ── 性別 ──
    m = re.search(r'性別[:：]限(.+?)(?:[。]|$)', text)
    if m:
        gender_raw = m.group(1)
        if '男' in gender_raw:
            result['gender_restriction'].append('male')
        if '女' in gender_raw:
            result['gender_restriction'].append('female')

    # ── 學號 ──
    m = re.search(r'學號[:：]限(.+?)(?:[。]|$)', text)
    if m:
        id_raw = m.group(1)
        if '單' in id_raw:
            result['student_id_parity'].append('odd')
        if '雙' in id_raw:
            result['student_id_parity'].append('even')

    # ── 身份 ──
    _KNOWN_IDENTITY_KEYWORDS = [
        '校學士', '非僑生', '非交換生', '非外籍生', '非重修生',
        '交換生', '外籍生', '重修生', '僑生', '不限',
    ]
    m = re.search(r'身份[:：]限(.+?)(?:[。]|$)', text)
    if m:
        identity_raw = m.group(1).strip()
        if '不限' in identity_raw:
            pass  # 無身份限制，不加任何旗標
        else:
            if '校學士' in identity_raw:
                result['open_to_cross_school'] = True
            if '非僑生' in identity_raw:
                result['identity_flags'].append('not_overseas_chinese')
            if '非交換生' in identity_raw:
                result['identity_flags'].append('not_exchange')
            if '非外籍生' in identity_raw:
                result['identity_flags'].append('not_foreign')
            if '非重修生' in identity_raw:
                result['identity_flags'].append('not_retake')
            # 正向身份（注意要排除「非XXX」的誤命中）
            if '交換生' in identity_raw and '非交換生' not in identity_raw:
                result['identity_flags'].append('exchange_only')
            if '外籍生' in identity_raw and '非外籍生' not in identity_raw:
                result['identity_flags'].append('foreign_only')
            if '重修生' in identity_raw and '非重修生' not in identity_raw:
                result['identity_flags'].append('retake_only')
            if '僑生' in identity_raw and '非僑生' not in identity_raw:
                result['identity_flags'].append('overseas_chinese')
            # 去除已知關鍵字後，若還有實質性殘餘 → 保留原文
            remaining = identity_raw
            for kw in _KNOWN_IDENTITY_KEYWORDS:
                remaining = remaining.replace(kw, '')
            remaining = re.sub(r'[、，,及與或及以後學年（）()\d]+', '', remaining).strip()
            if remaining and len(remaining) > 3:
                result['unparseable'].append(f'身份限制：{identity_raw}')

    # ── 指定課程（先修 / 同修 / 擋修 / 禁修）──
    m = re.search(r'指定課程[:：](.+?)(?:[。]|$)', text)
    if m:
        course_raw = m.group(1)
        for seg in re.split(r'[、，,]', course_raw):
            seg = seg.strip()
            codes = parse_course_codes(seg)
            if not codes:
                continue
            if '同修' in seg:
                result['coreq_codes'].extend(codes)
            elif '先修' in seg:
                result['prereq_codes'].extend(codes)
            elif '擋修' in seg:
                result['conflict_codes'].extend(codes)
            elif '禁修' in seg:
                result['forbidden_codes'].extend(codes)

    # ── 無法解析的殘餘條件 ──
    result['unparseable'].extend(extract_unparseable(text))

    return result


# ── 合併多優先序 ──────────────────────────────────────────────────────────────

def merge_priorities(priority_results: list[dict]) -> dict:
    """
    將多個優先序的解析結果合併：
    - 修課資格：取聯集（任一條件符合即可修）
    - 課程關係（prereq/coreq/conflict/forbidden）：跨優先序取聯集
    - has_conditional_prereq：先修只存在於「部分」優先序（非全部）→ True
    - has_special_condition：有無法完全結構化的條件 → True

    回傳：
      {
        'eligibility': {...},
        'course_relations': {...},
        'unparseable_conditions': [...],
      }
    """
    elig = {
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
        'open_to_edu_program': False,
        'edu_program_include': set(),
        'open_to_cross_school': False,
        'identity_flags': set(),
        'section_include': set(),
        'gender_restriction': set(),
        'student_id_parity': set(),
    }
    rels = {
        'prereq_codes': set(),
        'coreq_codes': set(),
        'conflict_codes': set(),
        'forbidden_codes': set(),
    }
    unparseable_set: set[str] = set()

    # 追蹤先修是否存在於「全部」優先序，以判斷是否為條件性先修
    priorities_with_prereq = 0
    all_years_unrestricted = False

    for r in priority_results:
        if not r['years']:
            all_years_unrestricted = True
        else:
            elig['eligible_years'].update(r['years'])

        if r['program_types']:
            elig['program_types'].update(r['program_types'])

        elig['dept_include'].update(r['dept_include'])
        elig['dept_exclude'].update(r['dept_exclude'])
        elig['college_include'].update(r['college_include'])
        elig['college_exclude'].update(r['college_exclude'])
        elig['identity_flags'].update(r['identity_flags'])
        elig['section_include'].update(r['section_include'])
        elig['gender_restriction'].update(r['gender_restriction'])
        elig['student_id_parity'].update(r['student_id_parity'])

        for flag_key, include_key in [
            ('open_to_minor', 'minor_include'),
            ('open_to_double_major', 'double_major_include'),
            ('open_to_credit_prog', 'credit_prog_include'),
            ('open_to_2nd_spec', 'spec_include'),
            ('open_to_edu_program', 'edu_program_include'),
        ]:
            if r[flag_key]:
                elig[flag_key] = True
                elig[include_key].update(r[include_key])

        if r['open_to_cross_school']:
            elig['open_to_cross_school'] = True

        rels['prereq_codes'].update(r['prereq_codes'])
        rels['coreq_codes'].update(r['coreq_codes'])
        rels['conflict_codes'].update(r['conflict_codes'])
        rels['forbidden_codes'].update(r['forbidden_codes'])

        if r['prereq_codes']:
            priorities_with_prereq += 1

        unparseable_set.update(r['unparseable'])

    # 年級處理
    if all_years_unrestricted:
        elig['eligible_years'] = []
    else:
        elig['eligible_years'] = sorted(elig['eligible_years'])

    # has_conditional_prereq：先修只在「部分」優先序存在
    has_conditional_prereq = (
        bool(rels['prereq_codes'])
        and priorities_with_prereq < len(priority_results)
    )

    # is_unrestricted：無任何結構限制（系所/學院/年級/學制皆空）
    is_unrestricted = (
        not elig['eligible_years']
        and not elig['program_types']
        and not elig['dept_include']
        and not elig['dept_exclude']
        and not elig['college_include']
        and not elig['college_exclude']
    )

    has_special_condition = bool(unparseable_set)

    eligibility_out = {
        'is_unrestricted':       is_unrestricted,
        'eligible_years':        elig['eligible_years'],
        'program_types':         sorted(elig['program_types']),
        'dept_include':          sorted(elig['dept_include']),
        'dept_exclude':          sorted(elig['dept_exclude']),
        'college_include':       sorted(elig['college_include']),
        'college_exclude':       sorted(elig['college_exclude']),
        'open_to_minor':         elig['open_to_minor'],
        'minor_include':         sorted(elig['minor_include']),
        'open_to_double_major':  elig['open_to_double_major'],
        'double_major_include':  sorted(elig['double_major_include']),
        'open_to_credit_prog':   elig['open_to_credit_prog'],
        'credit_prog_include':   sorted(elig['credit_prog_include']),
        'open_to_2nd_spec':      elig['open_to_2nd_spec'],
        'spec_include':          sorted(elig['spec_include']),
        'open_to_edu_program':   elig['open_to_edu_program'],
        'edu_program_include':   sorted(elig['edu_program_include']),
        'open_to_cross_school':  elig['open_to_cross_school'],
        'identity_flags':        sorted(elig['identity_flags']),
        'section_include':       sorted(elig['section_include']),
        'gender_restriction':    sorted(elig['gender_restriction']),
        'student_id_parity':     sorted(elig['student_id_parity']),
        'has_special_condition': has_special_condition,
        'has_conditional_prereq': has_conditional_prereq,
    }
    relations_out = {
        'prereq_codes':   sorted(rels['prereq_codes']),
        'coreq_codes':    sorted(rels['coreq_codes']),
        'conflict_codes': sorted(rels['conflict_codes']),
        'forbidden_codes':sorted(rels['forbidden_codes']),
    }
    return {
        'eligibility':            eligibility_out,
        'course_relations':       relations_out,
        'unparseable_conditions': sorted(unparseable_set),
    }


# ── 同課號不同班別合併 ────────────────────────────────────────────────────────

def _join_list_fields(existing: list, incoming: list) -> list:
    merged = set(existing) | set(incoming)
    return sorted(merged)


def merge_into_existing(existing: dict, parsed: dict, raw_cond_str: str) -> None:
    """將同課號不同班別的 parsed 結果合併進 existing（in-place）。"""
    ex_elig = existing['eligibility']
    in_elig = parsed['eligibility']
    ex_rels = existing['course_relations']
    in_rels = parsed['course_relations']

    # 年級聯集（有一個無限制就無限制）
    if ex_elig['eligible_years'] and in_elig['eligible_years']:
        ex_elig['eligible_years'] = sorted(
            set(ex_elig['eligible_years']) | set(in_elig['eligible_years'])
        )
    else:
        ex_elig['eligible_years'] = []

    # 一般 list 欄位取聯集
    for f in ['program_types', 'dept_include', 'dept_exclude',
              'college_include', 'college_exclude', 'identity_flags',
              'minor_include', 'double_major_include',
              'credit_prog_include', 'spec_include', 'edu_program_include',
              'section_include', 'gender_restriction', 'student_id_parity']:
        ex_elig[f] = _join_list_fields(ex_elig[f], in_elig[f])

    # bool 欄位取 OR
    for f in ['open_to_minor', 'open_to_double_major', 'open_to_credit_prog',
              'open_to_2nd_spec', 'open_to_edu_program', 'open_to_cross_school',
              'has_special_condition', 'has_conditional_prereq']:
        if in_elig.get(f):
            ex_elig[f] = True

    # is_unrestricted：只要有一個班別無限制，整門課視為無限制
    if in_elig.get('is_unrestricted'):
        ex_elig['is_unrestricted'] = True

    # 課程關係取聯集
    for f in ['prereq_codes', 'coreq_codes', 'conflict_codes', 'forbidden_codes']:
        ex_rels[f] = _join_list_fields(ex_rels[f], in_rels[f])

    # unparseable 取聯集
    existing['unparseable_conditions'] = sorted(
        set(existing.get('unparseable_conditions', []))
        | set(parsed.get('unparseable_conditions', []))
    )

    # raw_conditions 累積（去重）
    if raw_cond_str and raw_cond_str not in existing['raw_conditions']:
        existing['raw_conditions'].append(raw_cond_str)


# ── 主程式 ────────────────────────────────────────────────────────────────────

def main():
    results: dict[tuple, dict] = {}
    total = no_condition = 0

    for d in COURSE_DIRS:
        if not d.exists():
            continue
        for f in sorted(d.glob('*.json')):
            data = json.loads(f.read_text(encoding='utf-8'))
            for c in data:
                total += 1
                raw_code = c.get('課號-班別', '').split('-')[0]
                if not raw_code:
                    continue

                cond_data = c.get('分發條件') or {}
                priorities = cond_data.get('優先順序列表', [])

                # 組合原文（同課號不同班別用換行區分）
                raw_cond_str = ' | '.join(
                    f'P{p.get("優先順序","?")}: {p.get("相關條件限制說明","").strip()}'
                    for p in priorities
                ) if priorities else ''

                if not priorities:
                    no_condition += 1
                    parsed = {
                        'eligibility': {
                            'is_unrestricted': True,
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
                            'open_to_edu_program': False,
                            'edu_program_include': [],
                            'open_to_cross_school': False,
                            'identity_flags': [],
                            'section_include': [],
                            'gender_restriction': [],
                            'student_id_parity': [],
                            'has_special_condition': False,
                            'has_conditional_prereq': False,
                        },
                        'course_relations': {
                            'prereq_codes': [],
                            'coreq_codes': [],
                            'conflict_codes': [],
                            'forbidden_codes': [],
                        },
                        'unparseable_conditions': [],
                    }
                else:
                    # 解析每個優先序（注意：同一優先數字可能有多條，一律逐條解析）
                    priority_results = []
                    for p in priorities:
                        text = p.get('相關條件限制說明', '').strip()
                        if text:
                            priority_results.append(parse_condition_text(text))
                    parsed = merge_priorities(priority_results)
                    # priority_count = 原始優先序的「唯一批次數」（去重後的數字個數）
                    unique_batches = len({p.get('優先順序', '?') for p in priorities})
                    parsed['eligibility']['priority_count'] = unique_batches

                key = (raw_code, c.get('學年度', ''), c.get('學期', ''))
                if key in results:
                    merge_into_existing(results[key], parsed, raw_cond_str)
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

    # 確保所有記錄都有 priority_count（無分發條件的課設為 0）
    for r in results.values():
        r['eligibility'].setdefault('priority_count', 0)

    output_list = sorted(results.values(), key=lambda x: x['course_code'])
    OUTPUT.write_text(
        json.dumps(output_list, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    # ── 統計 ──────────────────────────────────────────────────────────────────
    elig_list = [r['eligibility'] for r in output_list]
    rels_list = [r['course_relations'] for r in output_list]

    has_year     = sum(1 for e in elig_list if e['eligible_years'])
    has_prog     = sum(1 for e in elig_list if e['program_types'])
    unrestricted = sum(1 for e in elig_list if e['is_unrestricted'])
    has_minor    = sum(1 for e in elig_list if e['open_to_minor'])
    has_dbl      = sum(1 for e in elig_list if e['open_to_double_major'])
    has_cp       = sum(1 for e in elig_list if e['open_to_credit_prog'])
    has_edu      = sum(1 for e in elig_list if e['open_to_edu_program'])
    has_cs       = sum(1 for e in elig_list if e['open_to_cross_school'])
    has_special  = sum(1 for e in elig_list if e['has_special_condition'])
    has_cond_pre = sum(1 for e in elig_list if e['has_conditional_prereq'])
    has_prereq   = sum(1 for r in rels_list if r['prereq_codes'])
    has_coreq    = sum(1 for r in rels_list if r['coreq_codes'])
    has_conflict = sum(1 for r in rels_list if r['conflict_codes'])
    has_forbid   = sum(1 for r in rels_list if r['forbidden_codes'])

    print(f'處理課程：{total} 門 → 去重後 {len(output_list)} 個課號')
    print(f'無分發條件（全部開放）：{no_condition} 門')
    print()
    print(f'完全無限制（is_unrestricted）：{unrestricted} 個課號')
    print(f'有年級限制：                  {has_year} 個課號')
    print(f'有學制限制：                  {has_prog} 個課號')
    print(f'輔系可修：                    {has_minor} 個課號')
    print(f'雙主修可修：                  {has_dbl} 個課號')
    print(f'學分學程可修：                {has_cp} 個課號')
    print(f'教育學程可修：                {has_edu} 個課號')
    print(f'申請校學士可修：              {has_cs} 個課號')
    print(f'含特殊不可解析條件：          {has_special} 個課號')
    print()
    print(f'有先修課程（含條件性）：      {has_prereq} 個課號')
    print(f'  其中條件性先修：            {has_cond_pre} 個課號')
    print(f'有同修課程要求：              {has_coreq} 個課號')
    print(f'有擋修課程限制：              {has_conflict} 個課號')
    print(f'有禁修課程限制：              {has_forbid} 個課號')
    print()
    print(f'輸出：{OUTPUT}')

    # 解析範例驗證
    print('\n=== 有先修要求 ===')
    for r in output_list:
        if r['course_relations']['prereq_codes']:
            e = r['eligibility']
            print(f'  {r["course_code"]} {r["course_name"][:20]}')
            print(f'    prereq={r["course_relations"]["prereq_codes"]}  conditional={e["has_conditional_prereq"]}')
            if len([x for x in output_list if x['course_relations']['prereq_codes']]) >= 3:
                break

    print('\n=== 有擋修課程 ===')
    count = 0
    for r in output_list:
        if r['course_relations']['conflict_codes']:
            print(f'  {r["course_code"]} {r["course_name"][:20]}')
            print(f'    conflict={r["course_relations"]["conflict_codes"]}')
            count += 1
            if count >= 3:
                break

    print('\n=== 含特殊不可解析條件 ===')
    count = 0
    for r in output_list:
        if r.get('unparseable_conditions'):
            print(f'  {r["course_code"]} {r["course_name"][:20]}')
            print(f'    unparseable={r["unparseable_conditions"]}')
            count += 1
            if count >= 3:
                break
    print()


if __name__ == '__main__':
    main()
