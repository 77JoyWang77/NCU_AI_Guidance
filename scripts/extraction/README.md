# scripts/extraction — 資料萃取腳本

依資料來源與功能分為四個子資料夾。

---

## 📁 projects_pdf/  —  研究計畫論文 PDF 處理

處理 `data/raw/projects/` 下的學生專題論文 PDF，為 RAG 系統建立問答資料。

| 腳本 | 說明 |
|------|------|
| `1_extract_pdf_metadata.py` | 抽取 PDF 基本元資料（題目、學生、年份） |
| `2_generate_questions.py` | 依元資料自動生成問答對 |
| `3a_extract_pdf_sections.py` | 從 PDF 抽取研究動機、方法、結論三段原文 |
| `3b_summarize_with_azure.py` | 透過 Azure OpenAI 摘要三段原文 |
| `3c_extract_abstract.py` | 抽取摘要（Abstract）與關鍵字（Keywords） |

執行順序：`1 → 2 → 3a → 3b → 3c`

---

## 📁 curriculum_maps/  —  課程地圖（圖像式流程圖）

處理各系所以圖片形式呈現的課程流程圖，轉換後透過 Vision API 結構化。

| 腳本 | 說明 |
|------|------|
| `convert_to_png.py` | 將 PDF / PPTX / AVIF / JPG 統一轉成 PNG |
| `extract_curriculum_map.py` | 用 GPT-4o Vision 提取課程清單與先修關係 |

執行順序：`convert_to_png → extract_curriculum_map`

---

## 📁 requirements/  —  應修科目表（結構化課程要求）

處理 `data/raw/應修科目表/` 的 47 份 PDF，產生課程年級/學期/備注等結構化資料。

| 腳本 | 說明 | 輸出 |
|------|------|------|
| `parse_requirements_table.py` | **核心函式庫**，含 `extract_semester_map()`、課號標準化等工具函式（供其他腳本引用） | — |
| `reorganize_requirements.py` | 將舊版 `curriculum_requirements_114.json` 拆分至 `curriculum_requirements/學院/系所.json` | `data/processed/curriculum_requirements/` |
| `extract_requirements_pdfplumber.py` | 純規則式萃取每門課的年級與學期 | `data/processed/requirements_semester_map.json` |
| `fix_requirements_notes.py` | 修正 `requirements_notes.json` 中備注從錯誤位置開始或被截斷的問題 | `data/processed/requirements_notes.json` |
| `export_tables_html.py` | 將應修科目表轉成互動式 HTML 編輯器，可直接編輯課程格子 | `tables_editor.html` |
| `schedule_review_html.py` | 產生人工審核介面，顯示 schedule_draft 中每門課的年級/學期標籤，支援下拉修正 | `schedule_review.html` |

執行順序：`reorganize → extract_requirements_pdfplumber → fix_requirements_notes → export_tables_html / schedule_review_html`

---

## 📁 course_programs/  —  學分學程與課程領域

| 腳本 | 說明 | 輸出 |
|------|------|------|
| `parse_programs.py` | 解析 `學分學程.js`，結構化各學程的必選修課程 | `data/processed/credit_programs.json` |
| `process_course_domain.py` | 依課號前綴判斷課程所屬學院/領域 | `data/processed/course_domain_map.json` |
