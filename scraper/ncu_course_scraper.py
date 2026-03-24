"""
測試單一系所爬蟲 - 詳細 JSON 格式
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import os
from dotenv import load_dotenv
import json
import re

class NCUCourseScraper:
    def __init__(self, year="114", semester="1"):
        load_dotenv()
        self.username = os.getenv('NCU_USERNAME')
        self.password = os.getenv('NCU_PASSWORD')
        self.year = year
        self.semester = semester

        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--start-maximized')

        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 15)

        # 創建輸出資料夾
        self.output_dir = f"{year}_{semester}"
        os.makedirs(self.output_dir, exist_ok=True)
        print(f"✓ 輸出資料夾：{self.output_dir}")

    def login(self):
        """登入"""
        print("=" * 60)
        print("登入 NCU Portal")
        print("=" * 60)
        try:
            self.driver.get("https://portal.ncu.edu.tw/")
            username_input = self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//input[@type='text' and not(@readonly)]"))
            )
            username_input.send_keys(self.username)
            password_input = self.driver.find_element(By.XPATH, "//input[@type='password']")
            password_input.send_keys(self.password)
            time.sleep(10)
            login_button = self.driver.find_element(By.XPATH, "//button[contains(text(), '登入')]")
            login_button.click()
            time.sleep(3)
            print("✓ 登入成功")
            return True
        except Exception as e:
            print(f"✗ 登入錯誤: {e}")
            return False

    def navigate_to_course_system(self):
        """前往選課系統"""
        try:
            self.driver.get("https://portal.ncu.edu.tw/system/cs")
            time.sleep(5)
            iframe = self.wait.until(EC.presence_of_element_located((By.ID, "portalFrame")))
            self.driver.switch_to.frame(iframe)
            print("✓ 已進入選課系統")
            return True
        except:
            return False

    def click_course_query_and_year(self):
        """點擊課程查詢 → 依年份查詢"""
        try:
            course_query = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), '課程查詢')]"))
            )
            course_query.click()
            time.sleep(2)
            year_query = self.wait.until(
                EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "依年份查詢"))
            )
            year_query.click()
            time.sleep(3)
            print("✓ 已進入依年份查詢")
            return True
        except:
            return False

    def click_year_semester(self, year="114", semester="1"):
        """點擊年份學期"""
        try:
            tables = self.driver.find_elements(By.TAG_NAME, "table")
            year_table = tables[1]
            rows = year_table.find_elements(By.TAG_NAME, "tr")

            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 2 and cells[0].text.strip() == year:
                    links = cells[1].find_elements(By.TAG_NAME, "a")
                    if semester == "1" and len(links) >= 1:
                        links[0].click()
                    elif semester == "2" and len(links) >= 2:
                        links[1].click()
                    time.sleep(3)
                    print(f"✓ 已點擊 {year}-{semester}")
                    return True
            return False
        except:
            return False

    def split_serial_course(self, text):
        """分割流水號和課號"""
        parts = text.strip().split('\n')
        return {
            "流水號": parts[0] if len(parts) > 0 else "",
            "課號-班別": parts[1] if len(parts) > 1 else ""
        }

    def split_name_note(self, text):
        """分割課程名稱、英文名稱和備註"""
        parts = text.strip().split('\n')
        return {
            "課程名稱(中文)": parts[0] if len(parts) > 0 else "",
            "課程名稱(英文)": parts[1] if len(parts) > 1 else "",
            "備註": '\n'.join(parts[2:]) if len(parts) > 2 else ""
        }

    def split_time_room(self, text):
        """分割上課時間和教室"""
        if '/' in text:
            parts = text.split('/')
            return {
                "上課時間": parts[0].strip(),
                "教室": parts[1].strip() if len(parts) > 1 else ""
            }
        return {
            "上課時間": text.strip(),
            "教室": ""
        }

    def extract_url_from_onclick(self, onclick_attr):
        """從onclick屬性中提取URL"""
        if not onclick_attr:
            return ""

        # onclick格式: javascript:open_limit('/Course/main/query/byKeywords?limit=1001&semester=1141');
        # 或: javascript:open_outline('/Course/main/query/byKeywords?serialNo=01001&outline=1001&semester=1141');
        match = re.search(r"['\"]([^'\"]+)['\"]", onclick_attr)
        if match:
            path = match.group(1)
            # 構建完整URL
            return f"https://portal.ncu.edu.tw{path}"
        return ""

    def parse_condition_detail(self, driver_window):
        """解析分發條件的詳細欄位（從表格）"""
        result = {}

        try:
            # 查找表格
            tables = driver_window.find_elements(By.TAG_NAME, "table")

            # 處理優先順序表格
            for table in tables:
                rows = table.find_elements(By.TAG_NAME, "tr")
                if len(rows) < 2:
                    continue

                # 檢查是否為優先順序表格
                header_cells = rows[0].find_elements(By.TAG_NAME, "th")
                if not header_cells:
                    header_cells = rows[0].find_elements(By.TAG_NAME, "td")

                headers = [cell.text.strip() for cell in header_cells]

                # 如果是優先順序表格
                if any('優先' in h for h in headers):
                    priorities = []
                    for i in range(1, len(rows)):
                        cells = rows[i].find_elements(By.TAG_NAME, "td")
                        if len(cells) >= 2:
                            priority_data = {
                                "優先順序": cells[0].text.strip(),
                                "相關條件限制說明": cells[1].text.strip()
                            }
                            priorities.append(priority_data)
                    if priorities:
                        result['優先順序列表'] = priorities

                # 如果是先修課程表格
                if any('先修' in h for h in headers):
                    prereqs = []
                    for i in range(1, len(rows)):
                        cells = rows[i].find_elements(By.TAG_NAME, "td")
                        if cells:
                            prereq_text = ' '.join([cell.text.strip() for cell in cells])
                            if prereq_text:
                                prereqs.append(prereq_text)
                    if prereqs:
                        result['先修課程'] = prereqs

            # 如果沒解析到優先順序或先修課程，嘗試找 colspan="2" 的 td（通常是簡單的限制說明）
            if not result:
                # 找所有 colspan="2" 的 td 元素
                colspan_cells = driver_window.find_elements(By.XPATH, "//td[@colspan='2']")
                for cell in colspan_cells:
                    text = cell.text.strip()
                    # 過濾掉空白和只包含常見標題的內容
                    if text and text != "課程沒有限制":
                        # 如果不只是標題，保存它
                        if not any(keyword in text for keyword in ['流水號', '課號', '課程名稱', 'MN', 'PE', 'Physical', 'All-out']):
                            result['限制說明'] = text
                            break
                    elif text == "課程沒有限制":
                        result['限制說明'] = text
                        break

            # 如果還是沒有內容，保存純文字（但要清理）
            if not result:
                text = driver_window.find_element(By.TAG_NAME, "body").text
                # 分行處理，過濾掉標題行
                lines = text.split('\n')
                cleaned_lines = []
                for line in lines:
                    line = line.strip()
                    # 跳過明顯的標題和空行
                    if line and not any(keyword in line for keyword in ['流水號', '課號', 'Physical', 'All-out', 'Education', 'Training']):
                        # 跳過純數字行（流水號）和課號格式
                        if not (line.isdigit() or re.match(r'^[A-Z]{2}\d{4}$', line)):
                            cleaned_lines.append(line)
                
                cleaned_text = '\n'.join(cleaned_lines).strip()
                if cleaned_text:
                    result['限制說明'] = cleaned_text[:500]
                else:
                    result['限制說明'] = "課程沒有限制"

        except Exception as e:
            result['錯誤'] = str(e)
            result['限制說明'] = "解析失敗"

        return result

    def parse_outline_detail(self, driver_window):
        """解析課程綱要的詳細欄位（從表格或文字）"""
        result = {}

        try:
            # 獲取完整文字
            text = driver_window.find_element(By.TAG_NAME, "body").text

            # 查找所有表格
            tables = driver_window.find_elements(By.TAG_NAME, "table")

            # 方法1：嘗試解析表格（兩列格式）
            for table in tables:
                rows = table.find_elements(By.TAG_NAME, "tr")

                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if not cells:
                        cells = row.find_elements(By.TAG_NAME, "th")

                    # 表格通常是兩列：欄位名稱 | 內容
                    if len(cells) == 2:
                        field_name = cells[0].text.strip()
                        field_value = cells[1].text.strip()

                        if field_name and field_value:
                            result[field_name] = field_value

            # 方法2：如果表格解析失敗，嘗試從文字解析（一行一欄位）
            if not result:
                lines = text.split('\n')
                current_field = None
                current_value = []

                field_keywords = ['學期', '開課單位', '流水號', '課號', '授課教師',
                                '課程名稱(中文)', '課程名稱(英文)', '課程學制', '學分',
                                '課程目標', '授課內容', '教科書/參考書', '自編教材比例',
                                '授課方式', '評量配分比重', '辦公時間', '授課週數',
                                '彈性教學說明', '課程領域', 'Office Hours', '備註']

                for line in lines:
                    line = line.strip()
                    if not line or '智慧財產權' in line or '侵害他人著作權' in line:
                        continue

                    # 檢查是否為欄位開頭
                    is_field = False
                    for keyword in field_keywords:
                        if line.startswith(keyword + ' ') or line.startswith(keyword):
                            # 保存上一個欄位
                            if current_field and current_value:
                                result[current_field] = '\n'.join(current_value)

                            # 開始新欄位
                            current_field = keyword
                            # 取得欄位後的內容
                            value = line[len(keyword):].strip()
                            current_value = [value] if value else []
                            is_field = True
                            break

                    # 如果不是欄位開頭，且有當前欄位，則為內容
                    if not is_field and current_field:
                        current_value.append(line)

                # 保存最後一個欄位
                if current_field and current_value:
                    result[current_field] = '\n'.join(current_value)

            # 如果還是沒解析到任何內容，保存純文字
            if not result:
                result['完整內容'] = text[:500]

        except Exception as e:
            text = driver_window.find_element(By.TAG_NAME, "body").text
            result['錯誤'] = str(e)
            result['完整內容'] = text[:500]

        return result

    def get_detail_by_click(self, link_elem, detail_type):
        """使用 Selenium 點擊獲取詳細內容"""
        try:
            current_window = self.driver.current_window_handle
            current_windows = self.driver.window_handles

            link_elem.click()
            time.sleep(2)

            new_windows = self.driver.window_handles
            if len(new_windows) > len(current_windows):
                # 找到新視窗（排除當前視窗）
                new_window = None
                for w in new_windows:
                    if w not in current_windows:
                        new_window = w
                        break

                if new_window:
                    self.driver.switch_to.window(new_window)
                    time.sleep(1)

                    # 解析內容（傳遞 driver 以便解析表格）
                    if detail_type == "分發條件":
                        result = self.parse_condition_detail(self.driver)
                    else:  # 課程綱要
                        result = self.parse_outline_detail(self.driver)

                    # 關閉新視窗
                    self.driver.close()

                    # 切回原視窗
                    self.driver.switch_to.window(current_window)
                    time.sleep(0.5)

                    # 重要：切回 iframe
                    iframe = self.driver.find_element(By.ID, "portalFrame")
                    self.driver.switch_to.frame(iframe)

                    return result

            return {}
        except Exception as e:
            print(f"[獲取{detail_type}錯誤: {str(e)[:50]}]", end=" ")
            # 確保切回原視窗和 iframe
            try:
                all_windows = self.driver.window_handles
                if len(all_windows) > len(current_windows):
                    # 關閉多餘的視窗
                    for w in all_windows:
                        if w not in current_windows:
                            self.driver.switch_to.window(w)
                            self.driver.close()
                # 切回原視窗
                self.driver.switch_to.window(current_window)
                # 切回 iframe
                iframe = self.driver.find_element(By.ID, "portalFrame")
                self.driver.switch_to.frame(iframe)
            except:
                pass
            return {}

    def scrape_one_dept(self, dept_index=0, max_courses=None):
        """爬取一個系所（支援翻頁）"""
        print(f"\n爬取第 {dept_index + 1} 個系所...")

        try:
            # 獲取系所列表
            tables = self.driver.find_elements(By.TAG_NAME, "table")
            dept_table = tables[-1]
            rows = dept_table.find_elements(By.TAG_NAME, "tr")

            if dept_index + 1 >= len(rows):
                print("系所索引超出範圍")
                return []

            target_row = rows[dept_index + 1]
            cells = target_row.find_elements(By.TAG_NAME, "td")

            college = cells[0].text.strip()
            dept_name = cells[1].text.strip()

            print(f"系所: {college} - {dept_name}")

            # 點擊查詢
            dept_link = cells[2].find_element(By.TAG_NAME, "a")
            dept_link.click()
            time.sleep(3)

            courses = []
            page_num = 1
            has_next_page = True
            total_scraped = 0

            # 翻頁爬取
            while has_next_page:
                print(f"\n--- 第 {page_num} 頁 ---")

                # 爬取當前頁面的課程
                tables = self.driver.find_elements(By.TAG_NAME, "table")
                course_table = max(tables, key=lambda t: len(t.find_elements(By.TAG_NAME, "tr")))
                rows = course_table.find_elements(By.TAG_NAME, "tr")

                # 表頭
                header_cells = rows[0].find_elements(By.TAG_NAME, "th")
                if not header_cells:
                    header_cells = rows[0].find_elements(By.TAG_NAME, "td")
                headers = [cell.text.strip() for cell in header_cells]

                courses_on_page = len(rows) - 1
                print(f"本頁有 {courses_on_page} 門課程")

                # 決定要爬多少門課
                if max_courses:
                    remaining = max_courses - total_scraped
                    courses_to_scrape = min(remaining, courses_on_page)
                else:
                    courses_to_scrape = courses_on_page

                # 爬取指定數量的課程
                for i in range(1, courses_to_scrape + 1):
                    print(f"\n處理第 {i} 門課程...", end=" ")

                    # 重新獲取表格（防止 stale element）
                    tables = self.driver.find_elements(By.TAG_NAME, "table")
                    course_table = max(tables, key=lambda t: len(t.find_elements(By.TAG_NAME, "tr")))
                    rows = course_table.find_elements(By.TAG_NAME, "tr")
                    row = rows[i]

                    cells = row.find_elements(By.TAG_NAME, "td")

                    # 基本資料
                    course_data = {
                        "學年度": "114",
                        "學期": "1",
                        "學院": college,
                        "系所": dept_name
                    }

                    # 分割流水號和課號
                    if len(cells) > 0:
                        serial_course = self.split_serial_course(cells[0].text)
                        course_data.update(serial_course)

                    # 分割課程名稱
                    if len(cells) > 1:
                        name_note = self.split_name_note(cells[1].text)
                        course_data.update(name_note)

                    # 授課教師
                    if len(cells) > 2:
                        course_data["授課教師"] = cells[2].text.strip()

                    # 學分
                    if len(cells) > 3:
                        course_data["學分"] = cells[3].text.strip()

                    # 分割時間教室
                    if len(cells) > 4:
                        time_room = self.split_time_room(cells[4].text)
                        course_data.update(time_room)

                    # 選修別
                    if len(cells) > 5:
                        course_data["選修別"] = cells[5].text.strip()

                    # 全半年
                    if len(cells) > 6:
                        course_data["全半年"] = cells[6].text.strip()

                    # 人數限制
                    if len(cells) > 7:
                        course_data["人數限制"] = cells[7].text.strip()

                    # 獲取分發條件
                    print("獲取分發條件...", end=" ")
                    if len(cells) > 8:
                        try:
                            condition_link = cells[8].find_element(By.TAG_NAME, "a")
                            onclick_attr = condition_link.get_attribute("onclick")
                            condition_url = self.extract_url_from_onclick(onclick_attr)
                            condition_detail = self.get_detail_by_click(condition_link, "分發條件")
                            course_data["分發條件_連結"] = condition_url
                            course_data["分發條件"] = condition_detail
                        except:
                            course_data["分發條件_連結"] = ""
                            course_data["分發條件"] = {}
                    else:
                        course_data["分發條件_連結"] = ""
                        course_data["分發條件"] = {}

                    # 獲取課程綱要
                    print("獲取課程綱要...", end=" ")
                    # 重新獲取 row（因為可能頁面已重載）
                    try:
                        tables = self.driver.find_elements(By.TAG_NAME, "table")
                        if tables:
                            course_table = max(tables, key=lambda t: len(t.find_elements(By.TAG_NAME, "tr")))
                            rows = course_table.find_elements(By.TAG_NAME, "tr")
                            if i < len(rows):
                                row = rows[i]
                                cells = row.find_elements(By.TAG_NAME, "td")

                                if len(cells) > 9:
                                    outline_link = cells[9].find_element(By.TAG_NAME, "a")
                                    onclick_attr = outline_link.get_attribute("onclick")
                                    outline_url = self.extract_url_from_onclick(onclick_attr)
                                    outline_detail = self.get_detail_by_click(outline_link, "課程綱要")
                                    course_data["課程綱要_連結"] = outline_url
                                    course_data["課程綱要"] = outline_detail
                                else:
                                    course_data["課程綱要_連結"] = ""
                                    course_data["課程綱要"] = {}
                            else:
                                course_data["課程綱要_連結"] = ""
                                course_data["課程綱要"] = {}
                        else:
                            course_data["課程綱要_連結"] = ""
                            course_data["課程綱要"] = {}
                    except Exception as e:
                        print(f"[獲取課程綱要失敗]", end=" ")
                        course_data["課程綱要_連結"] = ""
                        course_data["課程綱要"] = {}

                    courses.append(course_data)
                    total_scraped += 1
                    print("✓")

                    # 如果達到限制，停止
                    if max_courses and total_scraped >= max_courses:
                        print(f"\n已達到限制 {max_courses} 門課程")
                        has_next_page = False
                        break

                # 如果還沒達到限制，檢查是否有下一頁
                if has_next_page and (max_courses is None or total_scraped < max_courses):
                    try:
                        # 尋找翻頁區塊 (class="pagelinks")
                        pagelinks = self.driver.find_elements(By.CLASS_NAME, "pagelinks")

                        next_page_clicked = False

                        if pagelinks:
                            # 在翻頁區塊中尋找 "»" 下一頁按鈕
                            next_btn = pagelinks[0].find_elements(By.XPATH, ".//a[contains(., '»')]")
                            if next_btn and next_btn[0].is_displayed():
                                print(f"\n點擊下一頁 »...", end=" ")
                                next_btn[0].click()
                                time.sleep(3)
                                page_num += 1
                                next_page_clicked = True
                            else:
                                # 如果沒有 »，嘗試找下一個數字頁碼
                                next_page_num = page_num + 1
                                page_links = pagelinks[0].find_elements(By.TAG_NAME, "a")
                                for link in page_links:
                                    if link.text.strip() == str(next_page_num):
                                        print(f"\n點擊頁碼 {next_page_num}...", end=" ")
                                        link.click()
                                        time.sleep(3)
                                        page_num = next_page_num
                                        next_page_clicked = True
                                        break

                        # 如果沒有找到或點擊失敗，表示沒有下一頁了
                        if not next_page_clicked:
                            print(f"\n沒有更多頁面")
                            has_next_page = False

                    except Exception as e:
                        # 找不到下一頁元素，結束換頁
                        print(f"\n翻頁異常: {str(e)[:50]}")
                        has_next_page = False
                else:
                    has_next_page = False

            print(f"\n共爬取 {total_scraped} 門課程")
            return courses

        except Exception as e:
            print(f"\n錯誤: {e}")
            import traceback
            traceback.print_exc()
            return []

    def save_dept_json(self, dept_name, courses):
        """儲存系所課程為獨立JSON"""
        try:
            # 清理檔名中的特殊字元
            safe_name = re.sub(r'[\\/:*?"<>|]', '_', dept_name)
            filename = os.path.join(self.output_dir, f"{safe_name}.json")

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(courses, f, ensure_ascii=False, indent=2)
            print(f"  ✓ 已儲存至 {filename} ({len(courses)} 門課程)")
        except Exception as e:
            print(f"  ✗ 儲存錯誤: {e}")

    def close(self):
        """關閉瀏覽器"""
        try:
            self.driver.quit()
        except:
            pass

    def scrape_all_depts(self, exclude_keywords=None):
        """爬取所有系所"""
        if exclude_keywords is None:
            exclude_keywords = ['碩士', '博士']

        try:
            # 保存系所列表頁面的 URL（之後可以直接導航回來，不用 back()）
            dept_list_url = self.driver.current_url
            
            # 獲取系所列表
            tables = self.driver.find_elements(By.TAG_NAME, "table")
            dept_table = tables[-1]
            rows = dept_table.find_elements(By.TAG_NAME, "tr")

            total_depts = len(rows) - 1
            print(f"\n找到 {total_depts} 個系所")

            for dept_index in range(total_depts):
                # 重新獲取表格（防止stale element）
                tables = self.driver.find_elements(By.TAG_NAME, "table")
                dept_table = tables[-1]
                rows = dept_table.find_elements(By.TAG_NAME, "tr")

                if dept_index + 1 >= len(rows):
                    continue

                row = rows[dept_index + 1]
                cells = row.find_elements(By.TAG_NAME, "td")
                college = cells[0].text.strip()
                dept_name = cells[1].text.strip()
                full_name = f"{college}_{dept_name}"

                # 檢查是否排除
                if any(keyword in full_name for keyword in exclude_keywords):
                    print(f"\n[{dept_index+1}/{total_depts}] 跳過：{full_name} (碩博士班)")
                    continue

                print(f"\n[{dept_index+1}/{total_depts}] 爬取：{full_name}")

                # 點擊查詢
                dept_link = cells[2].find_element(By.TAG_NAME, "a")
                dept_link.click()
                time.sleep(3)

                # 爬取課程
                courses = self.scrape_courses_with_pagination(college, dept_name)

                # 儲存該系所的課程
                if courses:
                    self.save_dept_json(full_name, courses)

                # 直接導航回系所列表頁面（比 back() 更穩定可靠）
                self.driver.get(dept_list_url)
                time.sleep(2)
                # 重新進入iframe
                iframe = self.driver.find_element(By.ID, "portalFrame")
                self.driver.switch_to.frame(iframe)

        except Exception as e:
            print(f"\n爬取所有系所錯誤: {e}")
            import traceback
            traceback.print_exc()

    def scrape_courses_with_pagination(self, college, dept_name):
        """爬取課程（支援翻頁）"""
        courses = []
        page_num = 1
        has_next_page = True

        while has_next_page:
            print(f"  頁 {page_num}...", end=" ")

            # 爬取當前頁
            try:
                tables = self.driver.find_elements(By.TAG_NAME, "table")
                course_table = max(tables, key=lambda t: len(t.find_elements(By.TAG_NAME, "tr")))
                rows = course_table.find_elements(By.TAG_NAME, "tr")
                courses_before = len(courses)

                # 爬完當前頁所有課程
                for i in range(1, len(rows)):
                    # 重新獲取表格（防止stale element）
                    tables = self.driver.find_elements(By.TAG_NAME, "table")
                    course_table = max(tables, key=lambda t: len(t.find_elements(By.TAG_NAME, "tr")))
                    rows = course_table.find_elements(By.TAG_NAME, "tr")
                    row = rows[i]
                    cells = row.find_elements(By.TAG_NAME, "td")

                    course_data = {
                        "學年度": self.year,
                        "學期": self.semester,
                        "學院": college,
                        "系所": dept_name
                    }

                    # 基本資料
                    if len(cells) > 0:
                        serial_course = self.split_serial_course(cells[0].text)
                        course_data.update(serial_course)
                    if len(cells) > 1:
                        name_note = self.split_name_note(cells[1].text)
                        course_data.update(name_note)
                    if len(cells) > 2:
                        course_data["授課教師"] = cells[2].text.strip()
                    if len(cells) > 3:
                        course_data["學分"] = cells[3].text.strip()
                    if len(cells) > 4:
                        time_room = self.split_time_room(cells[4].text)
                        course_data.update(time_room)
                    if len(cells) > 5:
                        course_data["選修別"] = cells[5].text.strip()
                    if len(cells) > 6:
                        course_data["全半年"] = cells[6].text.strip()
                    if len(cells) > 7:
                        course_data["人數限制"] = cells[7].text.strip()

                    # 分發條件
                    if len(cells) > 8:
                        try:
                            condition_link = cells[8].find_element(By.TAG_NAME, "a")
                            onclick_attr = condition_link.get_attribute("onclick")
                            condition_url = self.extract_url_from_onclick(onclick_attr)
                            condition_detail = self.get_detail_by_click(condition_link, "分發條件")
                            course_data["分發條件_連結"] = condition_url
                            course_data["分發條件"] = condition_detail
                        except:
                            course_data["分發條件_連結"] = ""
                            course_data["分發條件"] = {}
                    else:
                        course_data["分發條件_連結"] = ""
                        course_data["分發條件"] = {}

                    # 課程綱要
                    try:
                        tables = self.driver.find_elements(By.TAG_NAME, "table")
                        if tables:
                            course_table = max(tables, key=lambda t: len(t.find_elements(By.TAG_NAME, "tr")))
                            rows = course_table.find_elements(By.TAG_NAME, "tr")
                            if i < len(rows):
                                row = rows[i]
                                cells = row.find_elements(By.TAG_NAME, "td")
                                if len(cells) > 9:
                                    outline_link = cells[9].find_element(By.TAG_NAME, "a")
                                    onclick_attr = outline_link.get_attribute("onclick")
                                    outline_url = self.extract_url_from_onclick(onclick_attr)
                                    outline_detail = self.get_detail_by_click(outline_link, "課程綱要")
                                    course_data["課程綱要_連結"] = outline_url
                                    course_data["課程綱要"] = outline_detail
                                else:
                                    course_data["課程綱要_連結"] = ""
                                    course_data["課程綱要"] = {}
                            else:
                                course_data["課程綱要_連結"] = ""
                                course_data["課程綱要"] = {}
                        else:
                            course_data["課程綱要_連結"] = ""
                            course_data["課程綱要"] = {}
                    except:
                        course_data["課程綱要_連結"] = ""
                        course_data["課程綱要"] = {}

                    courses.append(course_data)

                # 顯示本頁爬取數量
                courses_on_page = len(courses) - courses_before
                print(f"{courses_on_page} 門", end=" ")

                # 爬完當前頁後，檢查是否有下一頁
                pagelinks = self.driver.find_elements(By.CLASS_NAME, "pagelinks")
                if pagelinks:
                    next_btn = pagelinks[0].find_elements(By.XPATH, ".//a[contains(., '»')]")
                    if next_btn and next_btn[0].is_displayed():
                        print("[翻頁]", end=" ")
                        next_btn[0].click()
                        time.sleep(3)
                        page_num += 1
                    else:
                        has_next_page = False
                else:
                    has_next_page = False

            except Exception as e:
                print(f"錯誤: {str(e)[:30]}")
                has_next_page = False

        return courses

    def run(self):
        """執行"""
        try:
            if not self.login():
                return

            if not self.navigate_to_course_system():
                return

            if not self.click_course_query_and_year():
                return

            if not self.click_year_semester(self.year, self.semester):
                return

            # 爬取所有系所
            self.scrape_all_depts()

            print("\n" + "=" * 60)
            print(f"爬取完成！所有系所已儲存至 {self.output_dir}")
            print("=" * 60)

        except Exception as e:
            print(f"\n錯誤: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.close()


if __name__ == "__main__":
    print("=" * 60)
    print("  NCU 課程爬蟲")
    print("=" * 60)

    # 爬取兩個學期
    for semester in ["1", "2"]:
        print(f"\n開始爬取 114 學年度第 {semester} 學期")
        print("=" * 60)

        scraper = NCUCourseScraper(year="114", semester=semester)
        scraper.run()

    print("\n" + "=" * 60)
    print("所有學期爬取完成！")
    print("=" * 60)
