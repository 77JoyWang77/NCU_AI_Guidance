"""
解析 raw/courses 和 raw/graduate_courses 的分發條件，
為每門課萃取結構化的選課資格屬性。

輸出格式（v3）：每個優先序（P1, P2, ...）保留為獨立 access_rule（OR 邏輯），
不再合併成單一 eligibility 物件，以避免「dept + year 關聯性」在合併時遺失。

  is_unrestricted      : bool  任何人皆可修（無任何限制）
  is_grad_only         : bool  所有 rule 都只允許研究所學制
  is_undergrad_open    : bool  至少一個 rule 允許大學部
  has_special_condition: bool  含無法完全結構化的條件
  has_conditional_prereq: bool 先修只在部分優先序存在（非絕對要求）

  access_rules         : list  各優先序條件（符合任一即可修）
    每條 rule 含：
    program_types      : list[str]   學制限制（bachelor/master/phd/...），空 = 不限
    dept_include       : list[str]   指定可修系所，空 = 不限
    dept_exclude       : list[str]   排除系所
    college_include    : list[str]   指定可修學院，空 = 不限
    college_exclude    : list[str]   排除學院
    years              : list[int]   可修年級，空 = 不限；"非一年級" → [2,3,4]
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
    section_include    : list[str]   班別限制（A/B/C）
    gender_restriction : list[str]   性別限制
    student_id_parity  : list[str]   學號奇偶

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


# ── 研究所學制判斷 ────────────────────────────────────────────────────────────

_GRAD_TYPES = {"master", "phd", "master_inservice", "master_industry"}
_GRAD_DEPT_SUFFIXES = ("碩士班", "博士班", "研究所", "在職專班", "碩士學位學程", "博士學位學程")


def _is_rule_unrestricted(rule: dict) -> bool:
    return (
        not rule['program_types']
        and not rule['dept_include']
        and not rule['dept_exclude']
        and not rule['college_include']
        and not rule['college_exclude']
        and not rule['years']
    )


def _is_rule_grad_only(rule: dict) -> bool:
    if rule['program_types']:
        return all(pt in _GRAD_TYPES for pt in rule['program_types'])
    if rule['dept_include']:
        return all(
            any(d.endswith(s) for s in _GRAD_DEPT_SUFFIXES)
            for d in rule['dept_include']
        )
    return False


def compute_top_level_flags(access_rules: list[dict]) -> dict:
    if not access_rules:
        return {'is_unrestricted': True, 'is_grad_only': False, 'is_undergrad_open': True}
    is_unrestricted = any(_is_rule_unrestricted(r) for r in access_rules)
    is_grad_only = all(_is_rule_grad_only(r) for r in access_rules)
    is_undergrad_open = is_unrestricted or any(not _is_rule_grad_only(r) for r in access_rules)
    return {
        'is_unrestricted':  is_unrestricted,
        'is_grad_only':     is_grad_only,
        'is_undergrad_open': is_undergrad_open,
    }


# ── 建立 access_rules ────────────────────────────────────────────────────────

def build_access_rules(priority_results: list[dict]) -> dict:
    """
    將各優先序解析結果保留為獨立 access_rule（OR 邏輯：符合任一即可修）。
    課程關係（prereq/coreq/conflict/forbidden）跨優先序取聯集。
    """
    access_rules = []
    rels = {
        'prereq_codes':  set(),
        'coreq_codes':   set(),
        'conflict_codes': set(),
        'forbidden_codes': set(),
    }
    unparseable_set: set[str] = set()
    priorities_with_prereq = 0

    for r in priority_results:
        rule = {
            'program_types':        sorted(r['program_types']),
            'dept_include':         sorted(r['dept_include']),
            'dept_exclude':         sorted(r['dept_exclude']),
            'college_include':      sorted(r['college_include']),
            'college_exclude':      sorted(r['college_exclude']),
            'years':                sorted(r['years']),
            'open_to_minor':        r['open_to_minor'],
            'minor_include':        sorted(r['minor_include']),
            'open_to_double_major': r['open_to_double_major'],
            'double_major_include': sorted(r['double_major_include']),
            'open_to_credit_prog':  r['open_to_credit_prog'],
            'credit_prog_include':  sorted(r['credit_prog_include']),
            'open_to_2nd_spec':     r['open_to_2nd_spec'],
            'spec_include':         sorted(r['spec_include']),
            'open_to_edu_program':  r['open_to_edu_program'],
            'edu_program_include':  sorted(r['edu_program_include']),
            'open_to_cross_school': r['open_to_cross_school'],
            'identity_flags':       sorted(r['identity_flags']),
            'section_include':      sorted(r['section_include']),
            'gender_restriction':   sorted(r['gender_restriction']),
            'student_id_parity':    sorted(r['student_id_parity']),
        }
        access_rules.append(rule)

        rels['prereq_codes'].update(r['prereq_codes'])
        rels['coreq_codes'].update(r['coreq_codes'])
        rels['conflict_codes'].update(r['conflict_codes'])
        rels['forbidden_codes'].update(r['forbidden_codes'])

        if r['prereq_codes']:
            priorities_with_prereq += 1

        unparseable_set.update(r['unparseable'])

    has_conditional_prereq = (
        bool(rels['prereq_codes']) and priorities_with_prereq < len(priority_results)
    )

    return {
        **compute_top_level_flags(access_rules),
        'access_rules':           access_rules,
        'course_relations':       {k: sorted(v) for k, v in rels.items()},
        'unparseable_conditions': sorted(unparseable_set),
        'has_special_condition':  bool(unparseable_set),
        'has_conditional_prereq': has_conditional_prereq,
    }


# ── 同課號不同班別合併 ────────────────────────────────────────────────────────

def merge_into_existing(existing: dict, parsed: dict, raw_cond_str: str) -> None:
    """同課號不同班別：合併 access_rules（去重後 append），並更新 top-level 旗標。"""
    existing_rules: list = existing.get('access_rules', [])
    for new_rule in parsed.get('access_rules', []):
        if new_rule not in existing_rules:
            existing_rules.append(new_rule)
    existing['access_rules'] = existing_rules

    existing.update(compute_top_level_flags(existing_rules))

    ex_rels = existing['course_relations']
    in_rels = parsed['course_relations']
    for f in ['prereq_codes', 'coreq_codes', 'conflict_codes', 'forbidden_codes']:
        ex_rels[f] = sorted(set(ex_rels[f]) | set(in_rels[f]))

    existing['unparseable_conditions'] = sorted(
        set(existing.get('unparseable_conditions', []))
        | set(parsed.get('unparseable_conditions', []))
    )

    if parsed.get('has_special_condition'):
        existing['has_special_condition'] = True
    if parsed.get('has_conditional_prereq'):
        existing['has_conditional_prereq'] = True

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
                        'is_unrestricted':     True,
                        'is_grad_only':        False,
                        'is_undergrad_open':   True,
                        'has_special_condition':   False,
                        'has_conditional_prereq':  False,
                        'access_rules': [],
                        'course_relations': {
                            'prereq_codes': [],
                            'coreq_codes': [],
                            'conflict_codes': [],
                            'forbidden_codes': [],
                        },
                        'unparseable_conditions': [],
                    }
                else:
                    # 解析每個優先序（同一優先數字可能有多條，一律逐條解析）
                    priority_results = []
                    for p in priorities:
                        text = p.get('相關條件限制說明', '').strip()
                        if text:
                            priority_results.append(parse_condition_text(text))
                    parsed = build_access_rules(priority_results)

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

    output_list = sorted(results.values(), key=lambda x: x['course_code'])
    OUTPUT.write_text(
        json.dumps(output_list, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    # ── 統計 ──────────────────────────────────────────────────────────────────
    rels_list = [r['course_relations'] for r in output_list]

    unrestricted    = sum(1 for r in output_list if r['is_unrestricted'])
    grad_only       = sum(1 for r in output_list if r['is_grad_only'])
    undergrad_open  = sum(1 for r in output_list if r['is_undergrad_open'])
    has_special     = sum(1 for r in output_list if r['has_special_condition'])
    has_cond_pre    = sum(1 for r in output_list if r['has_conditional_prereq'])
    has_prereq      = sum(1 for r in rels_list if r['prereq_codes'])
    has_coreq       = sum(1 for r in rels_list if r['coreq_codes'])
    has_conflict    = sum(1 for r in rels_list if r['conflict_codes'])
    has_forbid      = sum(1 for r in rels_list if r['forbidden_codes'])
    total_rules     = sum(len(r['access_rules']) for r in output_list)

    print(f'處理課程：{total} 門 → 去重後 {len(output_list)} 個課號')
    print(f'無分發條件（全部開放）：{no_condition} 門')
    print(f'access_rules 總數：    {total_rules} 條')
    print()
    print(f'完全無限制（is_unrestricted）：{unrestricted} 個課號')
    print(f'純研究所課程（is_grad_only）： {grad_only} 個課號')
    print(f'大學部可修（is_undergrad_open）：{undergrad_open} 個課號')
    print(f'含特殊不可解析條件：           {has_special} 個課號')
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
            print(f'  {r["course_code"]} {r["course_name"][:20]}')
            print(f'    prereq={r["course_relations"]["prereq_codes"]}  conditional={r["has_conditional_prereq"]}')
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
