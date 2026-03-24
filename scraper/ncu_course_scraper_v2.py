"""
NCU 課程爬蟲 v2 - 無需登入版本
直接訪問公開課程查詢頁面
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import os
import json
import re


class NCUCourseScraperV2:
    def __init__(self, year="114", semester="1"):
        self.year = year
        self.semester = semester
        self.base_url = f"https://cis.ncu.edu.tw/Course/main/query/byYears?do=showDept&semester={year}{semester}"

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

    def navigate_to_course_page(self):
        """直接前往課程查詢頁面（無需登入）"""
        print("=" * 60)
        print(f"前往 {self.year}-{self.semester} 課程查詢頁面")
        print("=" * 60)
        try:
            self.driver.get(self.base_url)
            time.sleep(3)
            print("✓ 已進入課程查詢頁面")
            return True
        except Exception as e:
            print(f"✗ 錯誤: {e}")
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

        match = re.search(r"['\"]([^'\"]+)['\"]", onclick_attr)
        if match:
            path = match.group(1)
            return f"https://cis.ncu.edu.tw{path}"
        return ""

    def parse_condition_detail(self, driver_window):
        """解析分發條件的詳細欄位（從表格）"""
        result = {}

        try:
            tables = driver_window.find_elements(By.TAG_NAME, "table")

            for table in tables:
                rows = table.find_elements(By.TAG_NAME, "tr")
                if len(rows) < 2:
                    continue

                header_cells = rows[0].find_elements(By.TAG_NAME, "th")
                if not header_cells:
                    header_cells = rows[0].find_elements(By.TAG_NAME, "td")

                headers = [cell.text.strip() for cell in header_cells]

                # 優先順序表格
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

                # 先修課程表格
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

            if not result:
                colspan_cells = driver_window.find_elements(By.XPATH, "//td[@colspan='2']")
                for cell in colspan_cells:
                    text = cell.text.strip()
                    if text and text != "課程沒有限制":
                        if not any(keyword in text for keyword in ['流水號', '課號', '課程名稱', 'MN', 'PE', 'Physical', 'All-out']):
                            result['限制說明'] = text
                            break
                    elif text == "課程沒有限制":
                        result['限制說明'] = text
                        break

            if not result:
                text = driver_window.find_element(By.TAG_NAME, "body").text
                lines = text.split('\n')
                cleaned_lines = []
                for line in lines:
                    line = line.strip()
                    if line and not any(keyword in line for keyword in ['流水號', '課號', 'Physical', 'All-out', 'Education', 'Training']):
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
            text = driver_window.find_element(By.TAG_NAME, "body").text
            tables = driver_window.find_elements(By.TAG_NAME, "table")

            # 解析表格
            for table in tables:
                rows = table.find_elements(By.TAG_NAME, "tr")

                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if not cells:
                        cells = row.find_elements(By.TAG_NAME, "th")

                    if len(cells) == 2:
                        field_name = cells[0].text.strip()
                        field_value = cells[1].text.strip()

                        if field_name and field_value:
                            result[field_name] = field_value

            # 從文字解析
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

                    is_field = False
                    for keyword in field_keywords:
                        if line.startswith(keyword + ' ') or line.startswith(keyword):
                            if current_field and current_value:
                                result[current_field] = '\n'.join(current_value)

                            current_field = keyword
                            value = line[len(keyword):].strip()
                            current_value = [value] if value else []
                            is_field = True
                            break

                    if not is_field and current_field:
                        current_value.append(line)

                if current_field and current_value:
                    result[current_field] = '\n'.join(current_value)

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
                new_window = None
                for w in new_windows:
                    if w not in current_windows:
                        new_window = w
                        break

                if new_window:
                    self.driver.switch_to.window(new_window)
                    time.sleep(1)

                    if detail_type == "分發條件":
                        result = self.parse_condition_detail(self.driver)
                    else:
                        result = self.parse_outline_detail(self.driver)

                    self.driver.close()
                    self.driver.switch_to.window(current_window)
                    time.sleep(0.5)

                    return result

            return {}
        except Exception as e:
            print(f"[獲取{detail_type}錯誤: {str(e)[:50]}]", end=" ")
            try:
                all_windows = self.driver.window_handles
                if len(all_windows) > len(current_windows):
                    for w in all_windows:
                        if w not in current_windows:
                            self.driver.switch_to.window(w)
                            self.driver.close()
                self.driver.switch_to.window(current_window)
            except:
                pass
            return {}

    def scrape_courses_with_pagination(self, college, dept_name):
        """爬取課程（支援翻頁）"""
        courses = []
        page_num = 1
        has_next_page = True

        while has_next_page:
            print(f"  頁 {page_num}...", end=" ")

            try:
                tables = self.driver.find_elements(By.TAG_NAME, "table")
                course_table = max(tables, key=lambda t: len(t.find_elements(By.TAG_NAME, "tr")))
                rows = course_table.find_elements(By.TAG_NAME, "tr")
                courses_before = len(courses)

                for i in range(1, len(rows)):
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

                courses_on_page = len(courses) - courses_before
                print(f"{courses_on_page} 門", end=" ")

                # 檢查是否有下一頁
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

    def save_dept_json(self, dept_name, courses):
        """儲存系所課程為獨立JSON"""
        try:
            safe_name = re.sub(r'[\\/:*?"<>|]', '_', dept_name)
            filename = os.path.join(self.output_dir, f"{safe_name}.json")

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(courses, f, ensure_ascii=False, indent=2)
            print(f"  ✓ 已儲存至 {filename} ({len(courses)} 門課程)")
        except Exception as e:
            print(f"  ✗ 儲存錯誤: {e}")

    def scrape_all_depts(self, exclude_keywords=None):
        """爬取所有系所"""
        if exclude_keywords is None:
            exclude_keywords = ['碩士', '博士']

        try:
            dept_list_url = self.driver.current_url
            
            tables = self.driver.find_elements(By.TAG_NAME, "table")
            dept_table = tables[-1]
            rows = dept_table.find_elements(By.TAG_NAME, "tr")

            total_depts = len(rows) - 1
            print(f"\n找到 {total_depts} 個系所")

            for dept_index in range(total_depts):
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

                if any(keyword in full_name for keyword in exclude_keywords):
                    print(f"\n[{dept_index+1}/{total_depts}] 跳過：{full_name} (碩博士班)")
                    continue

                print(f"\n[{dept_index+1}/{total_depts}] 爬取：{full_name}")

                dept_link = cells[2].find_element(By.TAG_NAME, "a")
                dept_link.click()
                time.sleep(3)

                courses = self.scrape_courses_with_pagination(college, dept_name)

                if courses:
                    self.save_dept_json(full_name, courses)

                self.driver.get(dept_list_url)
                time.sleep(2)

        except Exception as e:
            print(f"\n爬取所有系所錯誤: {e}")
            import traceback
            traceback.print_exc()

    def close(self):
        """關閉瀏覽器"""
        try:
            self.driver.quit()
        except:
            pass

    def run(self):
        """執行"""
        try:
            if not self.navigate_to_course_page():
                return

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
    print("  NCU 課程爬蟲 v2 (無需登入)")
    print("=" * 60)

    # 爬取兩個學期
    for semester in ["1", "2"]:
        print(f"\n開始爬取 114 學年度第 {semester} 學期")
        print("=" * 60)

        scraper = NCUCourseScraperV2(year="114", semester=semester)
        scraper.run()

    print("\n" + "=" * 60)
    print("所有學期爬取完成！")
    print("=" * 60)
