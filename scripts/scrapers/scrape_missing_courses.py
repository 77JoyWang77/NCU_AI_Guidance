"""
針對 cross_source_matching.json 中課號不在 raw 的課程，
到 https://cis.ncu.edu.tw/Course/main/query/byKeywords 依課號搜尋，
選擇最新學期的結果並爬取課程資料。

輸出：data/raw/scraped_missing/courses.json（累積）
使用方式：python scripts/scrapers/scrape_missing_courses.py [--limit N] [--code XX1234]
"""

import json
import re
import sys
import time
import argparse
import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

BASE = Path(__file__).parent.parent.parent
OUTPUT_PATH = BASE / 'data' / 'raw' / 'scraped_missing' / 'courses.json'
SEARCH_URL = 'https://cis.ncu.edu.tw/Course/main/query/byKeywords'


# ─── 目標課號清單 ─────────────────────────────────────────────────────────────

def get_target_codes() -> list[str]:
    """從 cross_source_matching.json 取出所有需要補搜的標準 NCU 課號"""
    path = BASE / 'data' / 'processed' / 'validation' / 'cross_source_matching.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    ncu_code = re.compile(r'^[A-Za-z]{2,4}\d{4,5}$')
    codes = set()
    for key in ['curriculum_only',
                'cp_only_name_matched_same_prefix',
                'cp_only_name_matched_any_prefix',
                'cp_only_no_match_grad',
                'cp_only_no_match_undergrad']:
        for x in data.get(key, []):
            if ncu_code.match(x.get('code', '')):
                codes.add(x['code'])
    return sorted(codes)


# ─── 載入已爬取結果（斷點續爬）──────────────────────────────────────────────

def load_existing() -> dict:
    """回傳 {code: course_dict}"""
    if OUTPUT_PATH.exists():
        data = json.loads(OUTPUT_PATH.read_text(encoding='utf-8'))
        return {c.get('課號-班別', '').split('-')[0]: c for c in data if c.get('課號-班別')}
    return {}


def save_results(results: dict):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(list(results.values()), ensure_ascii=False, indent=2),
        encoding='utf-8'
    )


# ─── Selenium 工具 ───────────────────────────────────────────────────────────

def make_driver(headless: bool = False) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--start-maximized')
    return webdriver.Chrome(options=opts)


def extract_url_from_onclick(onclick: str) -> str:
    m = re.search(r"['\"]([^'\"]+)['\"]", onclick or '')
    return f"https://cis.ncu.edu.tw{m.group(1)}" if m else ''


def split_serial_course(text: str) -> dict:
    parts = text.strip().split('\n')
    return {
        '流水號':    parts[0] if len(parts) > 0 else '',
        '課號-班別': parts[1] if len(parts) > 1 else '',
    }


def split_name_note(text: str) -> dict:
    parts = text.strip().split('\n')
    return {
        '課程名稱(中文)': parts[0] if len(parts) > 0 else '',
        '課程名稱(英文)': parts[1] if len(parts) > 1 else '',
        '備註':          '\n'.join(parts[2:]) if len(parts) > 2 else '',
    }


def split_time_room(text: str) -> dict:
    if '/' in text:
        parts = text.split('/', 1)
        return {'上課時間': parts[0].strip(), '教室': parts[1].strip()}
    return {'上課時間': text.strip(), '教室': ''}


# ─── 解析彈出視窗 ─────────────────────────────────────────────────────────────

def parse_condition_popup(driver) -> dict:
    result = {}
    try:
        tables = driver.find_elements(By.TAG_NAME, 'table')
        for table in tables:
            rows = table.find_elements(By.TAG_NAME, 'tr')
            if len(rows) < 2:
                continue
            headers = [c.text.strip() for c in rows[0].find_elements(By.TAG_NAME, 'th') or
                       rows[0].find_elements(By.TAG_NAME, 'td')]
            if any('優先' in h for h in headers):
                priorities = []
                for row in rows[1:]:
                    cells = row.find_elements(By.TAG_NAME, 'td')
                    if len(cells) >= 2:
                        priorities.append({'優先順序': cells[0].text.strip(),
                                           '相關條件限制說明': cells[1].text.strip()})
                if priorities:
                    result['優先順序列表'] = priorities
        if not result:
            for cell in driver.find_elements(By.XPATH, "//td[@colspan='2']"):
                t = cell.text.strip()
                if t:
                    result['限制說明'] = t
                    break
    except Exception as e:
        result['限制說明'] = f'解析失敗: {e}'
    return result


def parse_outline_popup(driver) -> dict:
    result = {}
    try:
        # 核心能力表格
        core_abilities = []
        try:
            tbl = driver.find_element(
                By.XPATH, "//th[normalize-space()='系所核心能力']/ancestor::table[1]")
            for row in tbl.find_elements(By.TAG_NAME, 'tr')[1:]:
                cells = row.find_elements(By.TAG_NAME, 'td')
                if len(cells) >= 3 and cells[0].text.strip():
                    core_abilities.append({
                        '能力名稱': cells[0].text.strip(),
                        '強度指數': cells[1].text.strip(),
                        '評量方式': cells[2].text.strip(),
                    })
        except Exception:
            pass

        # body text → 欄位解析
        text = driver.find_element(By.TAG_NAME, 'body').text
        field_keywords = ['學期', '開課單位', '流水號', '課號', '授課教師',
                          '課程名稱(中文)', '課程名稱(英文)', '課程學制', '學分',
                          '課程目標', '授課內容', '教科書/參考書', '自編教材比例',
                          '授課方式', '評量配分比重', '辦公時間', '授課週數',
                          '彈性教學說明', '課程領域', 'Office Hours', '備註']
        current_field, current_value = None, []
        for line in text.split('\n'):
            line = line.strip()
            if not line or '智慧財產權' in line:
                continue
            matched = False
            for kw in field_keywords:
                if line.startswith(kw + ' ') or line == kw:
                    if current_field and current_value:
                        result[current_field] = '\n'.join(current_value)
                    current_field = kw
                    val = line[len(kw):].strip()
                    current_value = [val] if val else []
                    matched = True
                    break
            if not matched and current_field:
                current_value.append(line)
        if current_field and current_value:
            result[current_field] = '\n'.join(current_value)

        # 清理課程領域
        if '課程領域' in result and '系所核心能力' in result['課程領域']:
            result['課程領域'] = result['課程領域'][:result['課程領域'].find('系所核心能力')].strip()

        result['核心能力'] = core_abilities
    except Exception as e:
        result['錯誤'] = str(e)
    return result


def click_popup(driver, wait, link_elem, detail_type: str) -> dict:
    orig_window = driver.current_window_handle
    orig_windows = set(driver.window_handles)
    try:
        link_elem.click()
        time.sleep(2)
        new_windows = set(driver.window_handles) - orig_windows
        if new_windows:
            driver.switch_to.window(new_windows.pop())
            time.sleep(1)
            result = (parse_condition_popup if detail_type == '分發條件'
                      else parse_outline_popup)(driver)
            driver.close()
            driver.switch_to.window(orig_window)
            time.sleep(0.5)
            return result
    except Exception as e:
        print(f'  [彈窗錯誤 {detail_type}: {str(e)[:40]}]', end=' ')
        for w in set(driver.window_handles) - orig_windows:
            try:
                driver.switch_to.window(w)
                driver.close()
            except Exception:
                pass
        try:
            driver.switch_to.window(orig_window)
        except Exception:
            pass
    return {}


# ─── 搜尋單一課號 ─────────────────────────────────────────────────────────────

def do_search(driver, wait, code: str):
    """前往搜尋頁、選全部學年、輸入課號、按查詢，等待結果載入。"""
    driver.get(SEARCH_URL)
    time.sleep(1.5)
    try:
        sel = Select(wait.until(EC.presence_of_element_located((By.ID, 'year'))))
        sel.select_by_value('all')
        time.sleep(0.3)
    except Exception:
        pass
    kw_input = wait.until(EC.presence_of_element_located((By.ID, 'keyword')))
    kw_input.clear()
    kw_input.send_keys(code)
    time.sleep(0.3)
    driver.find_element(By.CSS_SELECTOR, "input[name='query'], input[type='submit']").click()
    time.sleep(2.5)


def parse_result_tables(driver, code: str) -> list[dict]:
    """
    結果頁每筆課程是一個獨立的小 table（1 header row + 1 data row）。
    從各 table 的 data row 解析課程資料，並從連結 URL 取得學期號。
    """
    entries = []
    tables = driver.find_elements(By.TAG_NAME, 'table')
    for tbl in tables:
        rows = tbl.find_elements(By.TAG_NAME, 'tr')
        if len(rows) != 2:
            continue
        headers = [th.text.strip() for th in rows[0].find_elements(By.TAG_NAME, 'th')]
        if '流水號' not in ''.join(headers):
            continue  # 不是課程結果 table
        cells = rows[1].find_elements(By.TAG_NAME, 'td')
        if len(cells) < 8:
            continue

        sc = split_serial_course(cells[0].text)
        raw_code = re.sub(r'-[A-Z0-9*]+$', '', sc.get('課號-班別', '').strip())
        if raw_code != code:
            continue

        entry = dict(sc)
        entry.update(split_name_note(cells[1].text) if len(cells) > 1 else {})
        if len(cells) > 2: entry['授課教師'] = cells[2].text.strip()
        if len(cells) > 3: entry['學分']    = cells[3].text.strip()
        if len(cells) > 4: entry.update(split_time_room(cells[4].text))
        if len(cells) > 5: entry['選修別']  = cells[5].text.strip()
        if len(cells) > 6: entry['全半年']  = cells[6].text.strip()
        if len(cells) > 7: entry['人數限制'] = cells[7].text.strip()

        # 從 table 前一個兄弟 <h5> 取學期號（如 "1142"）
        semester = 0
        try:
            h5 = driver.execute_script(
                'return arguments[0].previousElementSibling;', tbl)
            if h5 and h5.tag_name == 'h5':
                m = re.search(r'(\d{4})', h5.text.strip())
                if m:
                    semester = int(m.group(1))
        except Exception:
            pass

        entry['semester'] = semester
        entry['_table_elem'] = tbl   # 保留 element 供後續點擊
        entries.append(entry)

    return entries


def scrape_single(driver, wait, code: str) -> dict | None:
    """搜尋 code，選最新學期，爬取完整資料。回傳 course dict 或 None。"""
    do_search(driver, wait, code)
    entries = parse_result_tables(driver, code)
    if not entries:
        return None

    # 選最新學期
    best = max(entries, key=lambda e: e.get('semester', 0))
    sem_str = str(best['semester'])
    year = sem_str[:3] if len(sem_str) == 4 else ''
    sem  = sem_str[3]  if len(sem_str) == 4 else ''

    # 從最佳 table 點擊分發條件 (col 8) 和課程綱要 (col 9)
    condition, outline = {}, {}
    try:
        tbl = best['_table_elem']
        data_row = tbl.find_elements(By.TAG_NAME, 'tr')[1]
        cells = data_row.find_elements(By.TAG_NAME, 'td')
        if len(cells) > 8:
            try:
                condition = click_popup(driver, wait,
                    cells[8].find_element(By.TAG_NAME, 'a'), '分發條件')
            except Exception:
                pass
        if len(cells) > 9:
            try:
                outline = click_popup(driver, wait,
                    cells[9].find_element(By.TAG_NAME, 'a'), '課程綱要')
            except Exception:
                pass
    except Exception as e:
        print(f'  [detail error: {str(e)[:60]}]', end=' ')

    return {
        '學年度':         year,
        '學期':           sem,
        '系所':           outline.get('開課單位', ''),
        '流水號':         best.get('流水號', ''),
        '課號-班別':      best.get('課號-班別', ''),
        '課程名稱(中文)': best.get('課程名稱(中文)', ''),
        '課程名稱(英文)': best.get('課程名稱(英文)', '') or outline.get('課程名稱(英文)', ''),
        '備註':           best.get('備註', ''),
        '授課教師':       best.get('授課教師', ''),
        '學分':           best.get('學分', ''),
        '上課時間':       best.get('上課時間', ''),
        '教室':           best.get('教室', ''),
        '選修別':         best.get('選修別', ''),
        '全半年':         best.get('全半年', ''),
        '人數限制':       best.get('人數限制', ''),
        '分發條件':       condition,
        '課程綱要':       outline,
        '_source':        'scraped_missing',
        '_semester':      best['semester'],
    }


# ─── 主程式 ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=0,
                        help='最多搜尋幾個課號（0=全部）')
    parser.add_argument('--code', type=str, default='',
                        help='只搜尋單一課號（測試用）')
    parser.add_argument('--headless', action='store_true',
                        help='無頭模式執行')
    args = parser.parse_args()

    target_codes = [args.code] if args.code else get_target_codes()
    if args.limit:
        target_codes = target_codes[:args.limit]

    existing = load_existing()
    to_scrape = [c for c in target_codes if c not in existing]
    print(f'目標課號：{len(target_codes)} 個，已爬取：{len(existing)} 個，待爬：{len(to_scrape)} 個')

    if not to_scrape:
        print('無需爬取，結束。')
        return

    driver = make_driver(headless=args.headless)
    wait = WebDriverWait(driver, 15)
    results = dict(existing)

    try:
        for i, code in enumerate(to_scrape, 1):
            print(f'[{i}/{len(to_scrape)}] {code} ...', end=' ')
            try:
                course = scrape_single(driver, wait, code)
                if course:
                    results[code] = course
                    print(f'✅ {course.get("課程名稱(中文)","")} ({course.get("_semester","")})')
                else:
                    print('❌ 查無結果')
                    results[code] = {'課號-班別': f'{code}-?', '_not_found': True}
            except Exception as e:
                print(f'❌ 錯誤: {e}')
                results[code] = {'課號-班別': f'{code}-?', '_error': str(e)}

            # 每 10 筆存一次
            if i % 10 == 0:
                save_results(results)
                print(f'  (已存 {i} 筆)')

            time.sleep(1)

    finally:
        driver.quit()
        save_results(results)
        found = sum(1 for v in results.values() if not v.get('_not_found') and not v.get('_error'))
        print(f'\n完成：{found} / {len(results)} 筆成功爬取')
        print(f'輸出：{OUTPUT_PATH}')


if __name__ == '__main__':
    main()
