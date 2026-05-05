# SYSTEM_PROMPT 測試問題集

> 更新時間：2026-05-02（對齊 14 工具版本）  
> 用途：驗證工具選用正確率，搭配 `scripts/debug_agent.py` 或 `scripts/test_rag.py` 執行  
> 測試方法：前端 DebugTracePanel，或 `python scripts/debug_agent.py "問題"`

---

## 如何判斷測試通過

| 檢查項目 | 通過條件 |
|---------|---------|
| 工具呼叫 | DebugTracePanel 顯示的工具名稱符合「預期工具」 |
| 參數正確 | 無多餘 filter（`dept` 未被猜測加入；`course_type` 未在未說明時加入）|
| course_cards | 對應課程出現在右側卡片（非空）|
| 反幻覺 | course_cards 的課程皆在工具回傳結果中，不包含未回傳的課程 |
| Fallback | 工具無結果時改用第二個工具，非直接回傳空 |

---

## 一、基礎工具覆蓋（每個工具至少觸發一次）

### B-01 — 技術查詢（search_courses with tech）
```
中央大學哪些課程有教 Python？
```
**預期工具**：`search_courses(query="程式設計", tech="Python")`  
**核心驗證**：`tech` 參數有傳入；course_cards 非空

---

### B-02 — 系所必修（get_dept_courses required）
```
大氣科學學系有哪些必修課？
```
**預期工具**：`get_dept_courses("大氣科學學系", course_type="required")`  
**核心驗證**：出現大氣熱力學、大氣動力學等核心必修

---

### B-03 — 系所選修（get_dept_courses elective）
```
通識教育中心有哪些選修課可以選？
```
**預期工具**：`get_dept_courses("通識教育中心", course_type="elective")`  
**核心驗證**：回傳選修清單；dept 為「通識教育中心」（非縮寫）

---

### B-04 — 課程詳情（get_course_detail 精確）
```
化學學系的普通化學這門課教科書是哪本？授課內容是什麼？
```
**預期工具**：`get_course_detail(name_zh="普通化學", dept="化學學系")`  
**核心驗證**：直接回傳 `textbook` 和 `content`；無歧義問題

---

### B-05 — 課程詳情消歧義（get_course_detail ambiguous）
```
統計學這門課在教什麼？教科書是哪本？
```
**預期行為**：`get_course_detail(name_zh="統計學")` → 多科系 → `ambiguous=True` + candidates  
**核心驗證**：回答列出各科系版本供使用者選擇；不應任意選一門直接回答

---

### B-06 — 學程整合查詢（get_program_info）
```
永續發展學分學程有哪些課？請介紹一下學程內容。
```
**預期工具**：`get_program_info("永續發展")`（**單次呼叫**，非兩個工具並行）  
**核心驗證**：DebugTracePanel 只出現一個工具；同時有說明文字和課程清單

---

### B-07 — 學程搜尋（search_programs）
```
中央大學有沒有和語言、文化或跨文化相關的學分學程？
```
**預期工具**：`search_programs(query="語言 文化 跨文化")`  
**核心驗證**：找到客語、外語、人文相關學程；`distance` 分數可見

---

### B-08 — 畢業規定整合（get_graduation_requirements）
```
中文學系的畢業規定是什麼？需要幾學分？有沒有認證要求？
```
**預期工具**：`get_graduation_requirements("中國文學學系")`  
**核心驗證**：含最低學分、必修學分、認證要求；**不應**分兩次呼叫舊工具

---

### B-09 — 系所介紹（get_dept_info）
```
資訊工程學系適合什麼人讀？有什麼特色？
```
**預期工具**：`get_dept_info(query="資訊工程學系")`  
**核心驗證**：回傳系所介紹（Collego 資料）

---

### B-10 — 教師搜尋（search_teachers）
```
中央大學哪位教授專長是自然語言處理或文字探勘？
```
**預期工具**：`search_teachers(query="自然語言處理 文字探勘")`  
**核心驗證**：回傳教師清單；`specialties` 可見

---

### B-11 — 教師詳情（get_teacher_info）
```
中央大學江振瑞教授的專長是什麼？他開了哪些課？
```
**預期工具**：`get_teacher_info("江振瑞")`  
**核心驗證**：回傳 `profile`（專長）+ `courses`（開課清單）

---

### B-12 — 技術系所分布（get_depts_by_tech）
```
GIS（地理資訊系統）是哪些系的課程有教到？
```
**預期工具**：`get_depts_by_tech("GIS")`  
**核心驗證**：回傳地科系、土木系等；區分必修/選修

---

### B-13 — 相似課（find_similar_courses）
```
有沒有和生物統計概念相近的課？不限系所。
```
**預期工具**：`find_similar_courses("生物統計")`  
**核心驗證**：回傳跨系課程（統計學系、公衛相關等）

---

### B-14 — 知識地圖（get_course_knowledge_map）
```
「有機化學」這門課在學哪些概念？有沒有相關的跨系課程？
```
**預期工具**：`get_course_knowledge_map("有機化學")`  
**核心驗證**：回傳 Concept 清單 + 相似課程

---

### B-15 — PPR 廣泛探索（ppr_explore）
```
客家文化連到哪些老師、課程和系所？我想全面了解。
```
**預期工具**：`ppr_explore(seed="客家文化", focus="all", top_k=15)`  
**核心驗證**：回傳教師 + 課程 + 系所（客家語文暨社會科學學系）

---

## 二、多工具並行 / 串行

### M-01 — 技術全景（search_courses + get_depts_by_tech 並行）
```
機器學習在中央大學哪些地方有開課？從具體課程到系所分布都想了解。
```
**預期工具**：並行 `search_courses(query="機器學習", tech="機器學習")` + `get_depts_by_tech("機器學習")`  
**核心驗證**：兩工具都呼叫；涵蓋課程清單和系所分布

---

### M-02 — 系所全探索（get_dept_info + get_dept_courses 並行）
```
我對土木工程有興趣，中央大學土木系的特色是什麼？有哪些必修課？
```
**預期工具**：並行 `get_dept_info(query="土木工程學系")` + `get_dept_courses("土木工程學系", "required")`  
**核心驗證**：兩工具都呼叫；介紹 + 課程清單皆出現

---

### M-03 — 教師研究探索（ppr instructor → get_teacher_info 串行）
```
哪些教授在研究地球科學或板塊構造？他們的研究方向是什麼？
```
**預期工具**：第一步 `ppr_explore(seed="地球科學,板塊構造", focus="instructor")` → 第二步 `get_teacher_info("找到的教師名")`  
**核心驗證**：兩步串行；第一步找人，第二步確認專長

---

### M-04 — 概念延伸（ppr concept → search_courses 串行）
```
高中學了微積分，大學可以往哪些方向延伸？中央大學有相關進階課程嗎？
```
**預期工具**：第一輪 `ppr_explore(seed="微積分", focus="concept")` → 第二輪 `search_courses(query="數值分析 偏微分方程 最佳化")`  
**核心驗證**：兩輪 ReAct；第一輪找概念延伸，第二輪找課程

---

### M-05 — 學程發現 + 詳情（search_programs → get_program_info 串行）
```
我對生醫相關的跨領域學程有興趣，有哪些可以選？能不能介紹其中一個？
```
**預期工具**：第一步 `search_programs(query="生醫 醫療 跨領域")` → 第二步 `get_program_info("找到的學程名")`  
**核心驗證**：兩步串行；第一步發現學程清單，第二步取得說明 + 課程

---

### M-06 — 課程詳情 + 語意搜尋並行
```
外系學生想修機器學習，先修條件和修課資格是什麼？有沒有類似的替代課程？
```
**預期工具**：並行 `get_course_detail(name_zh="機器學習")` + `find_similar_courses("機器學習")`  
**核心驗證**：`raw_conditions` 含先修與資格原文；相似課有跨系結果

---

### M-07 — 兩系比較（get_dept_info 並行）
```
大氣科學系和地球科學系有什麼不同？各自有什麼代表課程？
```
**預期工具**：並行 `get_dept_info(query="大氣科學學系")` + `get_dept_info(query="地球科學學系")`，搭配各自的 `get_dept_courses`  
**核心驗證**：兩個系所的介紹和代表課程都有被列出

---

## 三、通識 / 語言 / 非理工（驗證 dept 名稱正確性）

### G-01 — 外語課主題查詢（search_courses + dept）
```
語言中心有沒有日文或西班牙文課？
```
**預期工具**：`search_courses(query="日文 西班牙文", dept="語言中心")`  
**核心驗證**：dept 為「語言中心」（非縮寫）；找到對應課程

---

### G-02 — 通識主題查詢（search_courses + dept）
```
通識有沒有法律相關的課？
```
**預期工具**：`search_courses(query="法律", dept="通識教育中心")`  
**核心驗證**：向量搜尋精準命中；**不應**用 `get_dept_courses` 回傳全部課程

---

### G-03 — 跨院主題搜尋（search_courses 不加 dept）
```
有哪些和環境永續或生態保護相關的課程，不限系所？
```
**預期工具**：`search_courses(query="環境永續 生態保護 永續發展")`（**不加** `dept`/`college`）  
**核心驗證**：出現跨院課程（地科、大氣、通識等）；**無** dept filter

---

### G-04 — 管理學院主題搜尋（search_courses + college）
```
管理學院有哪些和行銷或消費者行為相關的課？
```
**預期工具**：`search_courses(query="行銷 消費者行為", college="管理學院")`  
**核心驗證**：`college` 過濾正確；無不必要的 dept filter

---

## 四、工具選用壓力測試

### N-01 — 學程查詢不應分兩次呼叫
```
人工智慧技術應用學程要修哪些課？請也介紹一下學程目標。
```
**預期工具**：`get_program_info("人工智慧技術應用")`（**單次呼叫**）  
**核心驗證**：DebugTracePanel **不應**同時出現 `get_program_description` + `get_program_courses`

---

### N-02 — 修課資格查詢（get_course_detail raw_conditions）
```
外系學生可以修客語教學相關的課嗎？有什麼限制？
```
**預期工具**：`get_course_detail(name_zh="客語教學")`  
**核心驗證**：`raw_conditions` 字串直接呈現分發條件；不應輸出 JSON 結構

---

### N-03 — 畢業規定整合（不應分兩次呼叫）
```
土木工程學系要畢業需要修幾學分？有哪些認證或證照要求？
```
**預期工具**：`get_graduation_requirements("土木工程學系")`（**非** graduation_rules + requirements_notes 各一次）  
**核心驗證**：含 `min_credits`、`certifications`、`raw_notes` 完整說明

---

### N-04 — 技術查詢應帶 tech 參數
```
有哪些課有教 PyTorch？
```
**預期工具**：`search_courses(query="深度學習", tech="PyTorch")`  
**核心驗證**：`tech` 參數有傳入；graph-first 路徑觸發

---

## 五、Fallback / 弱領域壓力測試

### W-01 — 相似課 Fallback（概念稀疏）
```
有沒有和「全球環境變遷」概念最相近的課程？
```
**預期行為**：`find_similar_courses("全球環境變遷")` 無結果 → Fallback 到 `search_courses(query="環境變遷 氣候變遷")`  
**核心驗證**：不直接回傳「查不到」；Fallback 工具有被呼叫

---

### W-02 — 幻覺過濾（查無此課）
```
中央大學有沒有「區塊鏈與 Web3 應用」這門課？
```
**預期行為**：`search_courses(query="區塊鏈 Web3")` → 結果稀少 → LLM 誠實回答「目前查無此課」  
**核心驗證**：course_cards 為空或極少；LLM 未捏造課程名稱

---

### W-03 — PPR seed 不在圖中 → Fallback
```
中央大學有沒有跨文化溝通相關的課程？
```
**預期行為**：`ppr_explore(seed="跨文化溝通")` 若無結果 → Fallback 到 `search_courses(query="跨文化溝通 文化差異")`  
**核心驗證**：Fallback 有效；不直接回傳空

---

### W-04 — 學程名稱找不到 → available_programs 引導
```
請介紹「資料科學」學分學程的課程。
```
**預期行為**：`get_program_info("資料科學")` → `found=False` + `available_programs` 清單 → LLM 提示使用者確認名稱  
**核心驗證**：回答列出相近學程名稱；不回傳「找不到」就結束

---

## 六、高複雜度壓力測試

### P-01 — 社會組轉資料分析
```
我高中讀社會組，對資料分析和統計有興趣，中央大學有沒有不需要很強程式基礎的課程或學程？
```
**預期工具**：`ppr_explore(seed="統計,資料分析", focus="course")` + `search_programs(query="統計 資料分析 商業智慧")`  
**核心驗證**：推薦管理、統計相關課程和學程；無純理工系必修出現在前排

---

### P-02 — 大氣地科選系方向比較
```
我對天氣和地球有興趣，大氣科學系和地球科學系有什麼不同？我更適合哪個？
```
**預期工具**：並行 `get_dept_info` × 2 + `get_dept_courses` × 2  
**核心驗證**：兩系介紹都有；比較出現職涯差異和代表課程

---

### P-03 — 高中生化學探索（廣泛模糊問題）
```
我高中很喜歡化學，想了解中央大學哪些系所和課程跟化學有關，未來可以往哪裡發展。
```
**預期工具**：`ppr_explore(seed="化學", focus="all")` + `get_dept_info(query="化學 化工 材料")`  
**核心驗證**：推薦化學系、化工材料系、生命科學系等；PPR 節點包含課程、教師、系所

---

### P-04 — 跨域學習規劃
```
我想同時了解土木工程和環境工程，中央大學有哪些相關課程和學程可以搭配規劃？
```
**預期工具**：`ppr_explore(seed="土木工程,環境工程", focus="all")` + `search_programs(query="環境 永續 土木")`  
**核心驗證**：PPR 跨越兩個領域；學程搜尋也有相關結果

---

## 七、工具選擇對照表（快速查閱）

| 問題類型 | 應使用的工具 | 常見誤用 |
|---------|------------|---------|
| 「XX 系有哪些必修課」 | `get_dept_courses(required)` | ❌ `search_courses(dept=XX, course_type=必修)` |
| 「XX 課在教什麼 / 先修 / 外系能修嗎」 | `get_course_detail` | ❌ 分三次呼叫舊工具 |
| 「XX 課有哪些概念 / 相似課」 | `get_course_knowledge_map` | ❌ `search_courses` |
| 「有沒有類似 XX 的課」 | `find_similar_courses` | ❌ 只用 `search_courses` |
| 「XX 系畢業要幾學分」 | `get_graduation_requirements` | ❌ 分兩次呼叫舊工具 |
| 「有沒有和 XX 相關的學程」 | `search_programs` 先發現 | ❌ 直接猜學程名 |
| 「XX 學程有哪些課 / 介紹」 | `get_program_info` | ❌ `get_program_description` + `get_program_courses` 兩次 |
| 「XX 課能不能外系選修」 | `get_course_detail` (raw_conditions) | ❌ `search_courses(eligible_year=...)` |
| 「哪些系重視 XX 技術」 | `get_depts_by_tech` | ❌ `search_courses(tech=XX)` 只找課程 |
| 「語言中心有日文嗎」 | `search_courses(dept="語言中心")` | ❌ `get_dept_courses("語言中心")` 回傳全部 |

---

## 八、測試結果記錄表

| 題號 | 問題摘要 | 預期工具 | 工具正確 | course_cards | Fallback 正確 | 備註 |
|------|---------|---------|:-------:|:------------:|:------------:|------|
| B-01 | Python 課程 | search_courses(tech) | ☐ | ☐ | — | |
| B-02 | 大氣系必修 | get_dept_courses | ☐ | ☐ | — | |
| B-03 | 通識選修 | get_dept_courses | ☐ | ☐ | — | |
| B-04 | 化學系普通化學課綱 | get_course_detail(dept) | ☐ | — | — | 精確 |
| B-05 | 統計學消歧義 | get_course_detail→ambiguous | ☐ | — | — | 消歧 |
| B-06 | 永續學程 | get_program_info 單次 | ☐ | ☐ | — | 整合 |
| B-07 | 語言文化學程搜尋 | search_programs | ☐ | — | — | |
| B-08 | 中文系畢業規定 | get_graduation_requirements | ☐ | — | — | 整合 |
| B-09 | 資工系介紹 | get_dept_info | ☐ | — | — | |
| B-10 | NLP 教授搜尋 | search_teachers | ☐ | — | — | |
| B-11 | 江振瑞詳情 | get_teacher_info | ☐ | — | — | |
| B-12 | GIS 系所分布 | get_depts_by_tech | ☐ | — | — | |
| B-13 | 生物統計相似課 | find_similar_courses | ☐ | ☐ | — | |
| B-14 | 有機化學知識地圖 | get_course_knowledge_map | ☐ | ☐ | — | |
| B-15 | 客家文化 PPR | ppr(all) | ☐ | ☐ | — | |
| M-01 | 機器學習全景 | search+depts_by_tech 並行 | ☐ | ☐ | — | |
| M-02 | 土木系全探索 | dept_info+dept_courses 並行 | ☐ | ☐ | — | |
| M-03 | 地科教授 | ppr(inst)→teacher_info 串行 | ☐ | — | — | 2輪 |
| M-04 | 微積分延伸 | ppr(concept)→search 串行 | ☐ | ☐ | — | 2輪 |
| M-05 | 生醫學程發現+詳情 | search_prog→program_info 串行 | ☐ | ☐ | — | 2輪 |
| M-06 | 機器學習先修+替代 | course_detail+find_similar 並行 | ☐ | ☐ | — | |
| M-07 | 大氣vs地科比較 | dept_info×2 並行 | ☐ | ☐ | — | |
| G-01 | 語言中心日文 | search_courses(dept=語言中心) | ☐ | ☐ | — | |
| G-02 | 通識法律課 | search_courses(dept=通識) | ☐ | ☐ | — | |
| G-03 | 環境永續跨院 | search_courses(無dept) | ☐ | ☐ | — | |
| G-04 | 管院行銷課 | search_courses(college=管理) | ☐ | ☐ | — | |
| N-01 | AI學程不應分兩次 | get_program_info 單次 | ☐ | ☐ | — | 整合驗證 |
| N-02 | 客語課修課資格 | get_course_detail raw_conditions | ☐ | ☐ | — | |
| N-03 | 土木畢業規定 | get_graduation_requirements | ☐ | — | — | 整合驗證 |
| N-04 | PyTorch 課程 | search_courses(tech=PyTorch) | ☐ | ☐ | — | |
| W-01 | 全球環境 Fallback | find_similar→search | — | ☐ | ☐ | |
| W-02 | 區塊鏈幻覺過濾 | search→空 | ☐ | ☐ | — | |
| W-03 | 跨文化 PPR Fallback | ppr→search | — | ☐ | ☐ | |
| W-04 | 資料科學學程找不到 | program_info→available | ☐ | — | ☐ | |
| P-01 | 社會組轉資料 | ppr+search_programs | ☐ | ☐ | — | |
| P-02 | 大氣vs地科選系 | dept_info+dept_courses×2 | ☐ | ☐ | — | |
| P-03 | 高中生化學探索 | ppr(all)+dept_info | ☐ | ☐ | — | |
| P-04 | 土木+環境跨域 | ppr+search_programs | ☐ | ☐ | — | |
