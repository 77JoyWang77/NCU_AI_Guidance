# 工具詳細設計（18 個工具）

> 文件版本：2026-04-24  
> 來源：`backend/app/services/tools.py`

---

## 工具總覽

| # | 工具名稱 | 資料源 | 分數欄位 | 主要用途 |
|---|---------|--------|---------|---------|
| 1 | `search_courses` | ChromaDB 向量 | `distance` | 語意搜尋課程 |
| 2 | `get_course_syllabus` | ChromaDB metadata | 無 | 官方課綱（目標/內容/教科書） |
| 3 | `get_course_eligibility` | ChromaDB + eligibility JSON | 無 | 修課資格限制 |
| 4 | `get_prereq_info` | ChromaDB 向量 | 無 | 先修條件展開 |
| 5 | `get_dept_courses` | 知識圖譜 | 無 | 查詢系所必/選修 |
| 6 | `get_dept_info` | ChromaDB 向量 | `distance` | 查詢系所介紹 |
| 7 | `get_graduation_requirements` | schedule_draft + requirements_notes JSON | 無 | 畢業規定（整合版） |
| 8 | `get_program_courses` | 知識圖譜 | 無 | 查詢學程課程 |
| 9 | `get_program_description` | program_descriptions.json | 無 | 查詢學程說明 |
| 10 | `search_programs` | ChromaDB 向量 | `distance` | 語意搜尋學分學程 |
| 11 | `get_teacher_info` | 圖 + 向量 | 無 | 查詢教師詳情 |
| 12 | `search_teachers` | ChromaDB 向量 | `distance` | 語意搜尋教師 |
| 13 | `get_course_knowledge_map` | 知識圖譜 | `shared_concepts` | 知識地圖探索 |
| 14 | `find_similar_courses` | 知識圖譜 | `shared_concepts` | 找相似課程 |
| 15 | `get_depts_by_tech` | 知識圖譜 | 無 | 查詢技術分布系所 |
| 16 | `ppr_explore` | 知識圖譜 PPR | `score` (×1000) | 廣泛圖探索 |

> **向下相容保留**：`get_graduation_rules`、`get_requirements_notes` 仍保留在 `_TOOL_MAP`，但不加入 `TOOLS` schema（LLM 不主動呼叫）。

---

## 詳細說明

### 1. `search_courses` — 語意搜尋課程

**功能**：以自然語言語意搜尋課程，支援多種過濾條件。若傳入 `tech` 參數，優先走圖的精確技術查詢（graph-first），再補向量結果。

**參數表**

| 參數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|-------|------|
| `query` | string | ✓ | — | 搜尋關鍵詞或自然語言描述 |
| `dept` | string | | — | 限縮系所，如「大氣科學學系」 |
| `college` | string | | — | 限縮學院，如「理學院」 |
| `course_type` | string | | — | `"必修"` 或 `"選修"` |
| `year` | integer | | — | 建議修習年級（1-4） |
| `sem` | integer | | — | `1`=上學期，`2`=下學期 |
| `tech` | string | | — | 技術/工具名稱，如 `"Python"` |
| `is_grad` | boolean | | `false` | `true`=搜尋研究所課程 |
| `exclude_grad_only` | boolean | | `true` | `true`=排除僅限研究所課程；高中生探索情境維持預設 |
| `n` | integer | | `8` | 回傳筆數 |

**回傳格式**（`list[dict]`）

```json
[
  {
    "course_code": "CS1001",
    "name_zh": "資料結構",
    "name_en": "Data Structures",
    "dept": "資訊工程學系",
    "college": "資訊電機學院",
    "credits": 3,
    "type": "必修",
    "teacher": "王教授",
    "when_raw": "大二上",
    "concepts": "樹,堆疊,圖,排序",
    "technologies": "C++, Python",
    "domain_tags": "演算法,資料結構",
    "summary": "課程摘要前 200 字..."
  }
]
```

> 已移除的舊欄位：`eligible_years`（v2 格式）、`prereq_codes`（改用 `get_prereq_info`）、`teacher_specialties`  
> 已合併的欄位：`languages` + `tools` → `technologies`  
> 已新增的欄位：`concepts`（NLP 提取的核心概念）

**使用範例**

| 問題 | 典型呼叫 |
|------|---------|
| 找大氣相關課程 | `search_courses(query="大氣動力學 天氣預報")` |
| 管院有哪些行銷課 | `search_courses(query="行銷", college="管理學院")` |
| 找有教 Python 的課 | `search_courses(query="程式設計", tech="Python")` |
| 找研究所 NLP 課程 | `search_courses(query="自然語言處理", is_grad=True)` |

---

### 2. `get_course_syllabus` — 查詢官方課綱

**功能**：查詢課程的官方課綱：課程目標、授課內容、教科書/參考書。與 `get_course_knowledge_map`（NLP 提取）互補，此工具回傳教師填寫的官方說明。

**同名消歧義邏輯**：
- 有 `course_code` → 精確查詢（無歧義）
- 只有 `name_zh` → 若多科系都有此課，回傳 `ambiguous=True` + candidates
- `name_zh` + `dept` → 定位到指定科系

**參數表**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `name_zh` | string | | 課程中文名稱，如「普通化學」 |
| `dept` | string | | 指定系所以消歧義，如「化學學系」 |
| `course_code` | string | | 課號，精確查詢，優先使用 |

**回傳格式（找到且無歧義）**（`dict`）

```json
{
  "found": true,
  "ambiguous": false,
  "course_code": "CHEM1001",
  "name_zh": "普通化學",
  "dept": "化學學系",
  "teacher": "林教授",
  "credits": 3,
  "objective": "本課程目標為...",
  "content": "第一週：原子結構...",
  "textbook": "Chemistry: The Central Science (Brown et al.)"
}
```

**回傳格式（同名歧義）**（`dict`）

```json
{
  "found": true,
  "ambiguous": true,
  "message": "找到 4 個科系都有「普通化學」，請指定 dept 或由使用者選擇：",
  "candidates": [
    {"dept": "化學學系", "course_code": "CHEM1001", "teacher": "林教授", "credits": 3},
    {"dept": "化工與材料工程學系", "course_code": "CHEM2001", "teacher": "張教授", "credits": 3}
  ]
}
```

**使用範例**

| 問題 | 典型呼叫 |
|------|---------|
| 普通化學這門課在教什麼？ | `get_course_syllabus(name_zh="普通化學")` |
| 資工系的演算法用什麼教科書？ | `get_course_syllabus(name_zh="演算法", dept="資訊工程學系")` |

---

### 3. `get_course_eligibility` — 查詢修課資格

**功能**：查詢課程的修課限制（年級、限定系所、是否開放外系等），回傳原始分發條件原文（`raw_conditions`）。

**策略**：
1. 先用精確名稱比對（`get_courses_by_name`）
2. 無結果時改用語意搜尋 top-5

**參數表**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `course_query` | string | ✓ | 課程名稱或課號 |

**回傳格式**（`dict`）

```json
{
  "found": true,
  "match_type": "exact",
  "courses": [
    {
      "course_code": "CS2001",
      "name_zh": "演算法",
      "dept": "資訊工程學系",
      "raw_conditions": "P1: 系所:限資訊工程學系。年級:限非一年級。 | P2: 系所:限資訊工程學系。輔系-資訊工程學系。"
    }
  ]
}
```

> `raw_conditions` 為原始分發條件字串，直接供 LLM 理解，不另外解析成 JSON。  
> `is_unrestricted=True` 時，`raw_conditions` 為 `"不限修課條件（全校皆可修）"`。

---

### 4. `get_prereq_info` — 查詢先修條件

**功能**：搜尋目標課程後展開先修課號，回傳先修課的詳細資訊。

**參數表**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `course_query` | string | ✓ | 課程名稱或課號 |

**回傳格式**（`dict`）

```json
{
  "target_course": "演算法",
  "course_code": "CS2001",
  "prereq_codes": "CS1001,CS1002",
  "has_prereq": true,
  "prereq_details": [
    {"course_code": "CS1001", "name_zh": "資料結構", "credits": 3, "dept": "資訊工程學系", "when_raw": "大二上"}
  ]
}
```

**注意**：先搜尋最相似的 3 門課，取第一筆的 `prereq_codes` 展開。先修資料覆蓋率約 3.8%，無資料不代表無隱性前置需求。

---

### 5. `get_dept_courses` — 查詢系所必/選修課程

**功能**：從知識圖譜查詢特定系所的必修或選修課程清單（結構化資料，比向量搜尋更精確）。

**參數表**

| 參數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|-------|------|
| `dept_name` | string | ✓ | — | 系所名稱，如「客家語文暨社會科學學系」 |
| `course_type` | string | | `"required"` | `"required"`, `"elective"`, `"all"` |

**回傳格式**（`dict`）

```json
{
  "dept_name": "大氣科學學系",
  "course_type": "required",
  "courses": [
    {"id": "ATM1001", "name": "大氣熱力學", "credits": 3, "relation": "必修", "teacher": "張教授"}
  ]
}
```

**注意**：`dept_name` 支援系所（如「大氣科學學系」）、學院學士班（如「理學院學士班」）、系內組別（如「機械工程學系甲組」）。選修課若圖資料缺失，自動 fallback 至 ChromaDB metadata 精確查詢。

---

### 6. `get_dept_info` — 查詢系所介紹

**功能**：語意搜尋系所介紹（來自 Collego 資料：特色、生涯進路、能力特質）。

**參數表**

| 參數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|-------|------|
| `query` | string | ✓ | — | 系所名稱或描述 |

**回傳格式**（`list[dict]`，n_results=5）

```json
[
  {"dept_name": "客家語文暨社會科學學系", "summary": "系所介紹前 500 字..."}
]
```

**使用範例**

| 問題 | 典型呼叫 |
|------|---------|
| 物理治療相關科系有哪些特色？ | `get_dept_info(query="物理治療 復健 醫療")` |
| 適合對語言有興趣的人的系 | `get_dept_info(query="語言學 外語 文化")` |

---

### 7. `get_graduation_requirements` — 查詢畢業規定（整合版）

**功能**：同時回傳結構化學分要求（最低學分、必修學分、認證要求清單）與完整原文說明。整合原有 `get_graduation_rules` + `get_requirements_notes`，一次呼叫取得全部。

**參數表**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `dept_name` | string | ✓ | 系所名稱 |

**回傳格式**（`dict`）

```json
{
  "found": true,
  "dept_name": "中國文學學系",
  "min_credits": 128,
  "required_credits": 60,
  "certifications": ["英語能力認證"],
  "raw_notes": "一、畢業應修最低學分數為 128 學分...（完整原文）"
}
```

> `min_credits` / `required_credits` / `certifications` 來自 schedule_draft 結構化資料（可能不完整）；`raw_notes` 來自 requirements_notes.json 原文（更完整）。  
> 兩者皆無資料時回傳 `{"found": false}`。

---

### 8. `get_program_courses` — 查詢學程課程

**功能**：從知識圖譜查詢學分學程的必修和選修課程。

**參數表**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `program_name` | string | ✓ | 學程名稱，如「客語教學學分學程」 |

**回傳格式**（`dict`）

```json
{
  "program_name": "客語教學學分學程",
  "courses": [
    {"id": "HAKKA1001", "name": "客語口語表達", "credits": 2, "relation": "必修"}
  ]
}
```

**使用範例**：通常與 `get_program_description` 並行呼叫

---

### 9. `get_program_description` — 查詢學程說明

**功能**：直接從 `program_descriptions.json` 取得學分學程的完整說明文字。比向量搜尋更完整，**應優先使用**。

**參數表**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `program_name` | string | ✓ | 學程名稱 |

**回傳格式**（`str`）

```
【客語教學學分學程】
本學程旨在培養學生具備客語教學能力...（完整說明）
```

**比對策略**：精確比對 → 包含比對 → 模糊字元比對 → 列出所有學程名稱

---

### 10. `search_programs` — 語意搜尋學分學程

**功能**：語意搜尋 `ncu_credit_programs` collection，依主題或描述找最相關的學程清單。適合使用者不知道確切學程名稱時的發現型查詢。

**參數表**

| 參數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|-------|------|
| `query` | string | ✓ | — | 學程主題或描述，如「語言文化」「永續環境」「AI 應用」 |
| `n` | integer | | `5` | 回傳筆數 |

**回傳格式**（`list[dict]`）

```json
[
  {
    "program_name": "客語教學學分學程",
    "college": "客家學院",
    "description_excerpt": "本學程旨在...（前 300 字）",
    "distance": 0.412
  }
]
```

**使用範例**

| 問題 | 典型呼叫 |
|------|---------|
| 有沒有跟語言教學相關的學程？ | `search_programs(query="語言教學 文化")` |
| 管理學院有哪些學程？ | `search_programs(query="管理 商業 企業")` |

---

### 11. `get_teacher_info` — 查詢教師詳情

**功能**：查詢特定教師的官方專長（教育部申報資料）與開課清單（來自知識圖譜）。

**參數表**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `teacher_name` | string | ✓ | 教師姓名 |

**回傳格式**（`dict`）

```json
{
  "teacher_name": "林教授",
  "profile": [
    {"name": "林教授", "dept": "大氣科學學系", "rank": "教授", "specialties": "數值天氣預報,大氣動力學"}
  ],
  "courses": [
    {"id": "ATM2001", "name": "大氣動力學"}
  ]
}
```

---

### 12. `search_teachers` — 語意搜尋教師

**功能**：依研究領域或專長關鍵詞在 ChromaDB 做語意搜尋。

**參數表**

| 參數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|-------|------|
| `query` | string | ✓ | — | 研究領域或專長描述 |
| `n` | integer | | `5` | 回傳筆數 |

**回傳格式**（`list[dict]`）

```json
[
  {"name": "林教授", "dept": "大氣科學學系", "rank": "教授", "specialties": "數值天氣預報,大氣動力學"}
]
```

**使用範例**

| 問題 | 典型呼叫 |
|------|---------|
| 哪位老師專長是客家文化研究？ | `search_teachers(query="客家文化 族群關係")` |
| 有研究地球科學的教授嗎？ | `search_teachers(query="地球科學 地質 岩石")` |

---

### 13. `get_course_knowledge_map` — 知識地圖探索

**功能**：回傳一門課的完整知識地圖：涵蓋的學術概念、使用的技術工具，以及概念重疊最高的相似課程（top 8）。

**算法**：
1. 查詢課程節點
2. 取出 `USES_TECH`/`COVERS_CONCEPT` 出向邊 → 技術清單（前 10）、概念清單（全部）
3. 呼叫 `search_courses_by_concept_cluster(course_name, top_n=10)` 取相似課程（前 8 門）

**參數表**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `course_name` | string | ✓ | 課程名稱 |

**回傳格式**（`str`，格式化字串）

```
【氣候動力學】（大氣科學學系，3學分）

使用技術：Python, MATLAB, NCO
涵蓋概念（共 12 個）：大氣環流, 海洋耦合, 輻射平衡, ...

概念重疊最高的相關課程（可延伸學習）：
  - 大氣動力學（大氣科學學系）[共享 8 個概念]
  - 物理海洋學（地科系）[共享 5 個概念]
  - ...
```

---

### 14. `find_similar_courses` — 找相似課程

**功能**：透過知識圖譜 Concept/Technology 節點找與指定課程概念最相近的跨系課程。

**算法**：
1. 找種子課程的 `COVERS`/`TEACHES` 出向邊 → Concept/Technology 節點集合
2. 走反向邊找有共同 Concept 的其他課程
3. 以 `shared_concepts`（共享概念數）排序，回傳前 15 名

**參數表**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `course_name` | string | ✓ | 課程名稱，如「有機化學」「生物統計」 |

**回傳格式**（`str`，格式化字串）

```
與「有機化學」概念相近的課程（共 9 門）：
- 生物化學（生命科學學系，3學分） [共享概念：6 個]
- 藥物合成（化學學系，3學分） [共享概念：4 個]
- ...
```

> **已知限制**：概念數 < 3 的課程可能找不到結果，建議改用 `ppr_explore` 作為補充。

---

### 15. `get_depts_by_tech` — 查詢技術分布系所

**功能**：多跳圖查詢，找哪些系所的課程教授某技術或概念，並區分必修與選修。

**算法**：
1. 在知識圖譜找 tech 節點
2. 走 `TEACHES`/`COVERS` 反向邊找到相關課程
3. 再往上找課程所屬系所
4. 區分必修課 vs 選修課系所

**參數表**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `tech_name` | string | ✓ | 技術或概念名稱，如「統計」「氣候模擬」「GIS」 |

**回傳格式**（`str`，格式化字串）

```
教「GIS」的系所分布（共 8 門相關課程）：

必修課含此技術的系所（2 個）：
  - 地球科學學系
  - 土木工程學系

選修課含此技術的系所（5 個）：
  - 大氣科學學系
  - ...

相關課程（前 10 門）：
  - 地理資訊系統（地科系）
  - ...
```

---

### 16. `ppr_explore` — Personalized PageRank 廣泛探索

**功能**：從概念/課程節點出發，在整個知識圖譜做 Personalized PageRank 隨機遊走，找出最相關的節點（可跨課程、教師、系所、概念類型）。

**算法**：
- 種子節點：`personalization[seed_id] = 1/len(seeds)`
- 其他節點：0
- 參數：`alpha=0.85`（阻尼係數），`n_iter=25`（迭代次數）
- 分數 ×1000（讓數字可讀）

**參數表**

| 參數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|-------|------|
| `seed` | string | ✓ | — | 起始概念/課程，可用逗號分隔多個 |
| `focus` | string | | `"all"` | `"all"`, `"course"`, `"instructor"`, `"dept"`, `"concept"` |
| `top_k` | integer | | `15` | 回傳數量 |

**回傳格式**（`str`，格式化字串）

```
以「客家文化」為起點的 PPR 探索結果（all 模式）：
  [課程] 客家文化導論（客家語文暨社會科學學系）
  [課程] 族群關係與文化（社會學研究所）
  [教師] 劉教授（客家學院）
  [概念] 族群認同
  [系所] 客家語文暨社會科學學系
  ...
```

**`focus` 對應的節點類型過濾**

| focus | 包含節點類型 |
|-------|------------|
| `"course"` | `Course` |
| `"instructor"` | `Instructor` |
| `"dept"` | `Department`, `DeptGroup`, `CollegeBachelorProgram` |
| `"concept"` | `Concept`, `Technology`, `Field` |
| `"all"` | 全部 |

**使用範例**

| 問題 | 典型呼叫 |
|------|---------|
| 和客家文化相關的一切有哪些？ | `ppr_explore(seed="客家文化", focus="all", top_k=20)` |
| 生醫工程連結哪些系所？ | `ppr_explore(seed="生醫工程,醫療影像", focus="dept")` |
| 土木施工相關課程有哪些？ | `ppr_explore(seed="結構力學,土木施工", focus="course")` |
