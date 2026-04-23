# SYSTEM_PROMPT 測試問題集

> 建立日期：2026-04-22  
> 更新日期：2026-04-24  
> 用途：驗證改版後 SYSTEM_PROMPT 的工具選用正確率、新工具覆蓋率  
> 測試方法：在前端發送問題，用 DebugTracePanel 核對「預期工具」欄

---

## 如何判斷測試通過

| 檢查項目 | 通過條件 |
|---------|---------|
| 工具呼叫 | DebugTracePanel 顯示的工具名稱符合「預期工具」 |
| 參數正確 | 無多餘 filter（`eligible_year` 已移除；`dept` 未被猜測加入）|
| 新參數 | `exclude_grad_only` 在高中生情境下未被設為 `false` |
| course_cards | 對應課程出現在右側卡片（非空）|
| Fallback | 失敗情境下改用第二個工具，非直接回傳空 |

---

## 一、基礎功能（每個工具至少觸發一次）

### B-01 — 技術查詢（search_courses with tech）
```
中央大學哪些課程有教 Python？
```
**預期工具**：`search_courses(query="程式設計", tech="Python")`  
**核心驗證**：`tech` 參數有被傳入；course_cards 非空

---

### B-02 — 系所必修（get_dept_courses）
```
大氣科學學系有哪些必修課？
```
**預期工具**：`get_dept_courses("大氣科學學系", course_type="required")`  
**核心驗證**：出現「大氣熱力學」「大氣動力學」等核心必修

---

### B-03 — 知識地圖（get_course_knowledge_map）
```
「有機化學」這門課在學哪些概念？使用什麼工具？
```
**預期工具**：`get_course_knowledge_map("有機化學")`  
**核心驗證**：回傳 Concept 清單 + 相似課程

---

### B-04 — 相似課（find_similar_courses）
```
有沒有和生物統計概念相近的課？不限系所。
```
**預期工具**：`find_similar_courses("生物統計")`  
**核心驗證**：回傳跨系課程（統計學系、公衛相關等）

---

### B-05 — 學程雙工具（program_description + program_courses 並行）
```
永續發展學分學程有哪些課程？請也介紹一下學程內容。
```
**預期工具**：並行 `get_program_description("永續發展")` + `get_program_courses("永續發展")`  
**核心驗證**：DebugTracePanel 同一輪出現兩個工具

---

### B-06 — 畢業規定整合（get_graduation_requirements）
```
中文學系的畢業規定是什麼？需要幾學分？有沒有證照要求？
```
**預期工具**：`get_graduation_requirements("中國文學學系")`  
**核心驗證**：回答含最低學分數、必修學分、認證要求（若有）；**不應**分兩次分別呼叫 `get_graduation_rules` 和 `get_requirements_notes`

---

### B-07 — 教師探索（ppr_explore instructor）
```
中央大學哪些教授在研究大氣科學或氣象預報？
```
**預期工具**：`ppr_explore(seed="大氣科學,數值天氣預報", focus="instructor")`  
**核心驗證**：找到大氣科學學系相關教師

---

### B-08 — 技術系所分布（get_depts_by_tech）
```
GIS（地理資訊系統）是哪些系所的課程會教到？
```
**預期工具**：`get_depts_by_tech("GIS")`  
**核心驗證**：回傳地科系、土木系等；區分必修/選修

---

### B-09 — 官方課綱（get_course_syllabus）
```
普通化學這門課的官方課程目標是什麼？用哪本教科書？
```
**預期工具**：`get_course_syllabus(name_zh="普通化學")`  
**核心驗證**：若同名多系，回傳 `ambiguous=True` + candidates 讓使用者選擇；否則直接顯示 `objective` + `textbook`

---

### B-10 — 學程搜尋（search_programs）
```
中央大學有沒有和語言、文化或跨文化相關的學分學程？
```
**預期工具**：`search_programs(query="語言 文化 跨文化")`  
**核心驗證**：找到客語、外語、人文相關學程；distance 分數可見

---

## 二、多工具並行 / 串行

### M-01 — 技術全景（search_courses + get_depts_by_tech 並行）
```
統計學在中央大學哪些地方有開課？從具體課程到系所分布都想了解。
```
**預期工具**：並行 `search_courses(query="統計學", tech="統計")` + `get_depts_by_tech("統計")`  
**核心驗證**：兩工具都呼叫；涵蓋課程清單和系所分布

---

### M-02 — 課綱 + 知識地圖互補
```
演算法這門課官方說要教什麼？跟它概念最相近的課程有哪些？
```
**預期工具**：並行 `get_course_syllabus(name_zh="演算法")` + `get_course_knowledge_map("演算法")`  
**核心驗證**：同名消歧義若觸發，回傳 candidates；knowledge_map 提供概念清單

---

### M-03 — PPR 全模式探索（ppr_explore focus=all）
```
客家文化連到哪些老師、課程和系所？我想全面了解。
```
**預期工具**：`ppr_explore(seed="客家文化", focus="all", top_k=15)`  
**核心驗證**：回傳教師 + 課程 + 系所（客家語文暨社會科學學系）

---

### M-04 — 概念延伸路徑（ppr concept → search 串行）
```
高中學了微積分，大學可以往哪些方向延伸？中央大學有沒有相關進階課程？
```
**預期工具**：第一輪 `ppr_explore(seed="微積分", focus="concept")` → 第二輪 `search_courses(query="數值分析 偏微分方程 最佳化")`  
**核心驗證**：兩輪 ReAct；第一輪找概念延伸，第二輪找課程

---

### M-05 — 教師研究探索（ppr instructor → get_teacher_info 串行）
```
哪些教授在研究地球科學或板塊構造？他們的研究方向是什麼？
```
**預期工具**：第一步 `ppr_explore(seed="地球科學,板塊構造", focus="instructor")` → 第二步 `get_teacher_info("找到的教師名")`  
**核心驗證**：兩步串行；第一步找人，第二步確認專長

---

### M-06 — 先修 + 資格並行規劃
```
物理治療相關系所的課程，外系學生可以修嗎？先修條件有哪些？
```
**預期工具**：並行 `search_courses(query="物理治療 復健")` + `get_course_eligibility("物理治療")` + `get_prereq_info("物理治療")`  
**核心驗證**：`raw_conditions` 明確說明系所限制；三工具都呼叫

---

### M-07 — 系所 + 介紹 + 必修完整探索
```
我對土木工程有興趣，中央大學土木系的特色是什麼？有哪些必修課？
```
**預期工具**：並行 `get_dept_info(query="土木工程學系")` + `get_dept_courses("土木工程學系", "required")`  
**核心驗證**：兩工具都呼叫；介紹 + 課程清單皆出現

---

### M-08 — 學程發現 + 詳情（search_programs → program_description 串行）
```
我對生醫相關的跨領域學程有興趣，有哪些可以選？能不能介紹其中一個？
```
**預期工具**：第一步 `search_programs(query="生醫 醫療 跨領域")` → 第二步 `get_program_description("找到的學程名")`  
**核心驗證**：兩步串行；第一步發現學程清單，第二步說明內容

---

## 三、跨院 / 非理工 / 通識（驗證 dept 名稱正確性）

### G-01 — 通識人文藝術課
```
中央大學有哪些人文藝術類的通識課可以選？
```
**預期工具**：`get_dept_courses("通識教育中心", course_type="elective")`  
**核心驗證**：出現音樂欣賞、哲學、藝術等課程；**無** `eligible_year` 或系所 filter

---

### G-02 — 外語課查詢
```
語言中心有哪些外語課可以選？我想學日文或西班牙文。
```
**預期工具**：`get_dept_courses("語言中心", course_type="elective")`  
**核心驗證**：出現「日文」「西班牙文」；dept 為「語言中心」（非縮寫）

---

### G-03 — 客家學院課程
```
中央大學客家語文暨社會科學學系有哪些選修課？
```
**預期工具**：`get_dept_courses("客家語文暨社會科學學系", course_type="elective")`  
**核心驗證**：出現「客語口語表達」「族群關係」等課程

---

### G-04 — 管理學院探索
```
管理學院有哪些和行銷或消費者行為相關的課程？
```
**預期工具**：`search_courses(query="行銷 消費者行為", college="管理學院")`  
**核心驗證**：`college` 過濾正確；無不必要的 dept filter

---

### G-05 — 中文系介紹 + 必修
```
中文系適合什麼人讀？有哪些必修課？
```
**預期工具**：並行 `get_dept_info(query="中國文學學系")` + `get_dept_courses("中國文學學系", "required")`  
**核心驗證**：介紹包含文學研究、漢學特色；必修課出現「古典文學」等

---

### G-06 — 地科/大氣跨學院比較
```
大氣科學和地球科學有什麼不同？各自有什麼代表課程？
```
**預期工具**：並行 `get_dept_info(query="大氣科學")` + `get_dept_info(query="地球科學")`，搭配各自的 `get_dept_courses`  
**核心驗證**：兩個系所的介紹和代表課程都有被列出

---

### G-07 — 永續 / 環境相關課（跨院）
```
有哪些和環境永續或生態保護相關的課程，不限系所？
```
**預期工具**：`search_courses(query="環境永續 生態保護 永續發展")`（不加 `dept`/`college`）  
**核心驗證**：出現跨院課程（地科、大氣、通識等）；**無** dept filter

---

### G-08 — 音樂 / 藝術探索
```
中央大學有沒有音樂或藝術表演相關的課可以選修？
```
**預期工具**：`search_courses(query="音樂欣賞 藝術表演 合唱")`  
**核心驗證**：出現通識音樂課、藝文表演類課程；course_cards 非空

---

## 四、新工具壓力測試

### N-01 — 課綱同名消歧義（get_course_syllabus ambiguous）
```
「統計學」這門課在教什麼？教科書是哪本？
```
**預期行為**：`get_course_syllabus(name_zh="統計學")` → 多個科系都有 → `ambiguous=True` + candidates  
**核心驗證**：回答列出各科系版本供使用者選擇；**不應**任意選一門直接回答

---

### N-02 — 精確課綱查詢（get_course_syllabus with dept）
```
化學學系的普通化學這門課用哪本教科書？授課內容是什麼？
```
**預期工具**：`get_course_syllabus(name_zh="普通化學", dept="化學學系")`  
**核心驗證**：直接回傳 `textbook` 和 `content`；無歧義問題

---

### N-03 — 畢業規定整合（不應分兩次呼叫）
```
土木工程學系要畢業需要修幾學分？有哪些認證或證照要求？
```
**預期工具**：`get_graduation_requirements("土木工程學系")`（單次呼叫，**非** graduation_rules + requirements_notes 各一次）  
**核心驗證**：回答包含 `min_credits`、`certifications`、`raw_notes` 完整說明

---

### N-04 — 學程搜尋（search_programs 發現型）
```
中央大學有沒有和法律或公共政策相關的學分學程？
```
**預期工具**：`search_programs(query="法律 公共政策 法制")`  
**核心驗證**：找到相關學程（若存在）；`distance` 分數可合理判斷相關性

---

### N-05 — 修課資格查詢（raw_conditions 原文）
```
外系學生可以修「客語教學」相關的課嗎？有什麼限制？
```
**預期工具**：`get_course_eligibility("客語教學")`  
**核心驗證**：`raw_conditions` 字串直接呈現分發條件；**不應**輸出 `access_rules` JSON 結構

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
**預期行為**：`search_courses(query="區塊鏈 Web3")` → 結果為空 → LLM 誠實回答「目前查無此課」  
**核心驗證**：course_cards 為空；LLM 未捏造課程名稱

---

### W-03 — PPR seed 找不到 Fallback
```
中央大學有沒有跨文化溝通相關的課程？
```
**預期行為**：`ppr_explore(seed="跨文化溝通")` 無結果 → Fallback 到 `search_courses(query="跨文化溝通 文化差異")`  
**核心驗證**：Fallback 有效；不直接回傳空

---

### W-04 — 系所名稱確認（生醫正確名稱）
```
生醫工程相關課程有哪些？
```
**預期工具**：`search_courses(query="生醫工程 醫療影像", dept="生醫科學與工程學系")`（注意：**生醫科學與工程學系**，非「生醫工程學系」）  
**核心驗證**：dept 名稱正確；有回傳課程

---

### W-05 — 客家畢業規定（小系所完整性）
```
客家學院的客家語文暨社會科學學系畢業需要幾學分？有什麼規定？
```
**預期工具**：`get_graduation_requirements("客家語文暨社會科學學系")`  
**核心驗證**：回傳 `raw_notes` 原文（即使無結構化資料）；不回傳「找不到」

---

## 六、高複雜度壓力測試

### P-01 — 社會組轉資料分析
```
我高中讀社會組，對資料分析和統計有興趣，中央大學有沒有不需要很強程式基礎的課程或學程？
```
**預期工具**：`ppr_explore(seed="統計,資料分析", focus="course")` + `search_programs(query="統計 資料分析 商業智慧")`  
**核心驗證**：推薦管理、統計相關課程和學程；**無**純理工系必修出現在前排

---

### P-02 — 大氣地科選系方向比較
```
我對天氣和地球有興趣，大氣科學系和地球科學系有什麼不同？我更適合哪個？
```
**預期工具**：並行 `get_dept_info(query="大氣科學學系")` + `get_dept_info(query="地球科學學系")` + `get_dept_courses`（各一次）  
**核心驗證**：兩系介紹都有；比較出現職涯差異和代表課程

---

### P-03 — 中文和外文科系比較
```
中文系和英文系有什麼不同？我適合哪一個？它們畢業後能做什麼？
```
**預期工具**：並行 `get_dept_info(query="中國文學學系")` + `get_dept_info(query="英美語文學系")`  
**核心驗證**：兩系特色、生涯進路都有；**不應**只描述一個系

---

### P-04 — 想當護理師的學習路徑
```
我想從事醫護相關工作，中央大學有沒有相關科系或課程可以選？
```
**預期工具**：`ppr_explore(seed="醫護,健康照護", focus="dept")` + `get_dept_info(query="醫護 物理治療 生醫")`  
**核心驗證**：誠實說明中央沒有護理系，但推薦生醫、物理治療等相關資源

---

### P-05 — 土木 + 環境跨域學習規劃
```
我想同時了解土木工程和環境工程，中央大學有哪些相關課程和學程可以搭配規劃？
```
**預期工具**：`ppr_explore(seed="土木工程,環境工程", focus="all")` + `search_programs(query="環境 永續 土木")`  
**核心驗證**：PPR 跨越兩個領域；學程搜尋也有相關結果

---

### P-06 — 高中生完全探索（廣泛模糊問題）
```
我高中很喜歡化學，想了解中央大學哪些系所和課程跟化學有關，未來可以往哪裡發展。
```
**預期工具**：`ppr_explore(seed="化學", focus="all")` + `get_dept_info(query="化學 化工 材料")`  
**核心驗證**：推薦化學系、化工材料系、生命科學系等；PPR 節點包含課程、教師、系所

---

## 七、工具選擇對照表（常見問題分類）

| 問題類型 | 應使用的工具 | 常見誤用 |
|---------|------------|---------|
| 「XX 系有哪些必修課」 | `get_dept_courses(required)` | ❌ `search_courses(dept=XX, course_type=必修)` |
| 「XX 課在教什麼」（官方） | `get_course_syllabus` | ❌ `get_course_knowledge_map`（後者是 NLP 提取） |
| 「XX 課有哪些概念/相似課」 | `get_course_knowledge_map` | ❌ `search_courses` |
| 「有沒有類似 XX 的課」 | `find_similar_courses` | ❌ 只用 `search_courses` |
| 「XX 系畢業要幾學分」 | `get_graduation_requirements` | ❌ 分兩次呼叫舊工具 |
| 「有沒有和 XX 相關的學程」 | `search_programs` 先發現 | ❌ 直接猜學程名用 `get_program_description` |
| 「XX 課能不能外系選修」 | `get_course_eligibility` | ❌ `search_courses(eligible_year=...)` |
| 「哪些系重視 XX 技術」 | `get_depts_by_tech` | ❌ `search_courses(tech=XX)` 只找課程 |

---

## 測試結果記錄表

| 題號 | 問題摘要 | 預期工具 | 工具正確 | course_cards | Fallback 正確 | 備註 |
|------|---------|---------|:-------:|:------------:|:------------:|------|
| B-01 | Python 課程 | search_courses(tech) | ☐ | ☐ | — | |
| B-02 | 大氣系必修 | get_dept_courses | ☐ | ☐ | — | |
| B-03 | 有機化學知識地圖 | knowledge_map | ☐ | ☐ | — | |
| B-04 | 生物統計相似課 | find_similar | ☐ | ☐ | — | |
| B-05 | 永續學程介紹+課程 | prog_desc+courses 並行 | ☐ | ☐ | — | |
| B-06 | 中文系畢業規定 | grad_requirements | ☐ | — | — | 整合工具 |
| B-07 | 大氣教授搜尋 | ppr(instructor) | ☐ | — | — | |
| B-08 | GIS 系所分布 | get_depts_by_tech | ☐ | — | — | |
| B-09 | 普通化學課綱 | get_course_syllabus | ☐ | — | — | 同名消歧 |
| B-10 | 語言文化學程 | search_programs | ☐ | — | — | 新工具 |
| M-01 | 統計學全景 | search+depts_by_tech | ☐ | ☐ | — | |
| M-02 | 演算法課綱+知識地圖 | syllabus+knowledge_map | ☐ | ☐ | — | |
| M-03 | 客家文化全模式 | ppr(all) | ☐ | ☐ | — | |
| M-04 | 微積分延伸 | ppr(concept)→search | ☐ | ☐ | — | 2輪 |
| M-05 | 地科教授 | ppr(inst)→teacher | ☐ | — | — | 2輪 |
| M-06 | 物治修課資格 | search+elig+prereq | ☐ | ☐ | — | |
| M-07 | 土木系全探索 | dept_info+dept_courses | ☐ | ☐ | — | |
| M-08 | 生醫學程發現+詳情 | search_prog→prog_desc | ☐ | — | — | 2輪 |
| G-01 | 通識人文藝術 | dept(通識教育中心) | ☐ | ☐ | — | |
| G-02 | 語言中心外語 | dept(語言中心) | ☐ | ☐ | — | |
| G-03 | 客家學系選修 | dept(客家語文...) | ☐ | ☐ | — | |
| G-04 | 管院行銷課 | search(college=管理) | ☐ | ☐ | — | |
| G-05 | 中文系介紹+必修 | dept_info+dept_courses | ☐ | ☐ | — | |
| G-06 | 大氣vs地科比較 | dept_info×2 | ☐ | ☐ | — | |
| G-07 | 環境永續跨院 | search(無dept) | ☐ | ☐ | — | |
| G-08 | 音樂藝術課 | search(音樂欣賞) | ☐ | ☐ | — | |
| N-01 | 統計學課綱消歧義 | syllabus→ambiguous | ☐ | — | — | 消歧 |
| N-02 | 化學系普通化學 | syllabus(dept指定) | ☐ | — | — | |
| N-03 | 土木畢業規定 | grad_requirements | ☐ | — | — | 整合工具 |
| N-04 | 法律政策學程 | search_programs | ☐ | — | — | |
| N-05 | 客語課修課資格 | course_eligibility | ☐ | ☐ | — | raw條件 |
| W-01 | 全球環境 Fallback | find_similar→search | — | ☐ | ☐ | |
| W-02 | 區塊鏈幻覺過濾 | search→空 | ☐ | ☐ | — | |
| W-03 | 跨文化 PPR Fallback | ppr→search | — | ☐ | ☐ | |
| W-04 | 生醫正確 dept 名 | search(正確dept) | ☐ | ☐ | — | |
| W-05 | 客家系畢業規定 | grad_requirements | ☐ | — | — | 小系完整性 |
| P-01 | 社會組轉資料 | ppr+search_programs | ☐ | ☐ | — | |
| P-02 | 大氣vs地科選系 | dept_info+dept_courses×2 | ☐ | ☐ | — | |
| P-03 | 中文vs英文科系 | dept_info×2 | ☐ | ☐ | — | |
| P-04 | 醫護學習路徑 | ppr(dept)+dept_info | ☐ | ☐ | — | |
| P-05 | 土木+環境跨域 | ppr+search_programs | ☐ | ☐ | — | |
| P-06 | 高中生化學探索 | ppr(all)+dept_info | ☐ | ☐ | — | |
