# 工具詳細設計（15 個工具）

> 文件版本：2026-04-21  
> 來源：`backend/app/services/tools.py`

---

## 工具總覽

| # | 工具名稱 | 資料源 | 分數欄位 | 主要用途 |
|---|---------|--------|---------|---------|
| 1 | `search_courses` | ChromaDB 向量 | `distance` | 語意搜尋課程 |
| 2 | `get_dept_courses` | 知識圖譜 | 無 | 查詢系所必/選修 |
| 3 | `get_program_courses` | 知識圖譜 | 無 | 查詢學程課程 |
| 4 | `get_teacher_info` | 圖 + 向量 | 無 | 查詢教師詳情 |
| 5 | `search_teachers` | ChromaDB 向量 | `distance` | 語意搜尋教師 |
| 6 | `get_prereq_info` | ChromaDB 向量 | 無 | 查詢先修條件 |
| 7 | `get_graduation_rules` | schedule_draft JSON | 無 | 查詢畢業學分規定 |
| 8 | `get_dept_info` | ChromaDB 向量 | `distance` | 查詢系所介紹 |
| 9 | `get_course_eligibility` | ChromaDB 向量 | 無 | 查詢修課資格 |
| 10 | `get_program_description` | program_descriptions.json | 無 | 查詢學程說明 |
| 11 | `get_requirements_notes` | requirements_notes.json | 無 | 查詢畢業規定原文 |
| 12 | `find_similar_courses` | 知識圖譜 | `shared_concepts` | 找相似課程 |
| 13 | `get_course_knowledge_map` | 知識圖譜 | `shared_concepts` | 知識地圖探索 |
| 14 | `get_depts_by_tech` | 知識圖譜 | 無 | 查詢技術分布系所 |
| 15 | `ppr_explore` | 知識圖譜 PPR | `score` (×1000) | 廣泛圖探索 |

---

## 詳細說明

### 1. `search_courses` — 語意搜尋課程

**功能**：以自然語言描述語意搜尋課程，支援多種過濾條件。若傳入 `tech` 參數，優先走圖的精確技術查詢（graph-first），再補向量結果。

**參數表**

| 參數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|-------|------|
| `query` | string | ✓ | — | 搜尋關鍵詞或自然語言描述 |
| `dept` | string | | — | 限縮系所，如「資訊工程學系」 |
| `college` | string | | — | 限縮學院，如「資訊電機學院」 |
| `course_type` | string | | — | `"必修"` 或 `"選修"` |
| `year` | integer | | — | 建議修習年級（1-4） |
| `sem` | integer | | — | `1`=上學期，`2`=下學期 |
| `tech` | string | | — | 技術/工具名稱，如 `"PyTorch"` |
| `is_grad` | boolean | | `false` | `true`=搜尋研究所課程 |
| `eligible_year` | integer | | — | 修課資格年級過濾 |
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
    "prereq_codes": "CS0001",
    "eligible_years": "2,3,4",
    "summary": "課程摘要前 200 字..."
  }
]
```

> `distance` 分數由底層 retriever 計算，目前 **未傳遞** 至 SSE 事件（待補強）

**使用範例**

| 問題 | 典型呼叫 |
|------|---------|
| 找 AI 相關課程 | `search_courses(query="人工智慧")` |
| 找資工系必修 | `search_courses(query="資工必修", dept="資訊工程學系", course_type="必修")` |
| 找有教 PyTorch 的課 | `search_courses(query="深度學習", tech="PyTorch")` |
| 找研究所 NLP 課程 | `search_courses(query="自然語言處理", is_grad=True)` |
| 找大三可修的課 | `search_courses(query="演算法", eligible_year=3)` |

---

### 2. `get_dept_courses` — 查詢系所必/選修課程

**功能**：從知識圖譜查詢特定系所的必修或選修課程清單（結構化資料，比向量搜尋更精確）。

**參數表**

| 參數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|-------|------|
| `dept_name` | string | ✓ | — | 系所名稱，如「資訊工程學系」 |
| `course_type` | string | | `"required"` | `"required"`, `"elective"`, `"all"` |

**回傳格式**（`dict`）

```json
{
  "dept_name": "資訊工程學系",
  "course_type": "required",
  "courses": [
    {"id": "CS1001", "name": "資料結構", "credits": 3, "relation": "必修", "teacher": "王教授"}
  ]
}
```

**注意**：選修課若圖資料缺失，自動 fallback 至 ChromaDB metadata 精確查詢。

**使用範例**

| 問題 | 典型呼叫 |
|------|---------|
| 資工系必修課有哪些？ | `get_dept_courses(dept_name="資訊工程學系", course_type="required")` |
| 電機系選修課清單 | `get_dept_courses(dept_name="電機工程學系", course_type="elective")` |
| 資管系全部課程 | `get_dept_courses(dept_name="資訊管理學系", course_type="all")` |

---

### 3. `get_program_courses` — 查詢學程課程

**功能**：從知識圖譜查詢學分學程的必修和選修課程。

**參數表**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `program_name` | string | ✓ | 學程名稱，如「人工智慧技術應用」 |

**回傳格式**（`dict`）

```json
{
  "program_name": "人工智慧技術應用",
  "courses": [
    {"id": "CS3001", "name": "機器學習", "credits": 3, "relation": "必修"}
  ]
}
```

**使用範例**：通常與 `get_program_description` 並行呼叫

```
使用者：人工智慧技術應用學程要修哪些課？
→ 同時呼叫：get_program_description + get_program_courses
```

---

### 4. `get_teacher_info` — 查詢教師詳情

**功能**：查詢特定教師的官方專長（教育部申報資料）與開課清單（來自知識圖譜）。

**參數表**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `teacher_name` | string | ✓ | 教師姓名 |

**回傳格式**（`dict`）

```json
{
  "teacher_name": "王教授",
  "profile": [
    {"name": "王教授", "dept": "資訊工程學系", "rank": "教授", "specialties": "機器學習,資料探勘"}
  ],
  "courses": [
    {"id": "CS3001", "name": "機器學習"}
  ]
}
```

**使用範例**

| 問題 | 典型呼叫 |
|------|---------|
| 王教授教什麼課？ | `get_teacher_info(teacher_name="王教授")` |

---

### 5. `search_teachers` — 語意搜尋教師

**功能**：依研究領域或專長關鍵詞在 ChromaDB 做語意搜尋，適合「哪位教授專長是 NLP」此類查詢。

**參數表**

| 參數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|-------|------|
| `query` | string | ✓ | — | 研究領域或專長描述 |
| `n` | integer | | `5` | 回傳筆數 |

**回傳格式**（`list[dict]`）

```json
[
  {"name": "王教授", "dept": "資訊工程學系", "rank": "教授", "specialties": "機器學習,資料探勘"}
]
```

> `distance` 分數由底層 retriever 計算，目前未傳遞至 SSE 事件

**使用範例**

| 問題 | 典型呼叫 |
|------|---------|
| 哪位老師專長是深度學習？ | `search_teachers(query="深度學習")` |
| 有沒有研究 NLP 的教授？ | `search_teachers(query="自然語言處理 NLP")` |

---

### 6. `get_prereq_info` — 查詢先修條件

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

**注意**：先搜尋最相似的 3 門課，取第一筆的 `prereq_codes` 展開。

---

### 7. `get_graduation_rules` — 查詢畢業學分規定

**功能**：從 schedule_draft 取得系所畢業學分要求、必修學分與認證要求。

**參數表**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `dept_name` | string | ✓ | 系所名稱 |

**回傳格式**（`dict`）

```json
{
  "dept_name": "資訊工程學系",
  "min_credits": 128,
  "required_credits": 60,
  "graduation_rules": [{"description": "..."}],
  "certifications": ["英語能力認證"]
}
```

**注意**：`get_requirements_notes` 包含更完整的原文說明，**優先使用後者**。

---

### 8. `get_dept_info` — 查詢系所介紹

**功能**：語意搜尋系所介紹（來自 Collego 資料：特色、生涯進路、能力特質）。

**參數表**

| 參數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|-------|------|
| `query` | string | ✓ | — | 系所名稱或描述，如「適合喜歡設計的人的系所」 |

**回傳格式**（`list[dict]`，n_results=5）

```json
[
  {"dept_name": "資訊工程學系", "summary": "系所介紹前 500 字..."}
]
```

**使用範例**

| 問題 | 典型呼叫 |
|------|---------|
| 資工系在學什麼？ | `get_dept_info(query="資訊工程學系")` |
| 適合喜歡數學的人的系 | `get_dept_info(query="適合喜歡數學分析的人")` |

---

### 9. `get_course_eligibility` — 查詢修課資格

**功能**：查詢課程的修課限制（年級、限定系所、是否開放外系等）。

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
  "note": "找到 2 門同名課程，請依 dept/level 判斷",
  "courses": [
    {
      "course_code": "CS2001",
      "name_zh": "演算法",
      "dept": "資訊工程學系",
      "eligible_years": "2,3,4",
      "open_to_minor": false,
      "open_to_double_major": true,
      "is_unrestricted": false
    }
  ]
}
```

---

### 10. `get_program_description` — 查詢學程說明

**功能**：直接從 `program_descriptions.json` 取得學分學程的完整說明文字。比向量搜尋更完整，**應優先使用**。

**參數表**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `program_name` | string | ✓ | 學程名稱 |

**回傳格式**（`str`）

```
【人工智慧技術應用學分學程】
本學程旨在培養學生具備 AI 開發能力...（完整說明）
```

**比對策略**：精確比對 → 包含比對 → 模糊字元比對 → 列出所有學程名稱

---

### 11. `get_requirements_notes` — 查詢畢業規定原文

**功能**：直接從 `requirements_notes.json` 取得系所畢業規定原文，含完整說明細節。比 `get_graduation_rules` 更完整，**應優先使用**。

**參數表**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `dept_name` | string | ✓ | 系所名稱 |

**回傳格式**（`str`）

```
【資訊工程學系 畢業規定】
一、畢業應修最低學分數為 128 學分...（原文）
```

---

### 12. `find_similar_courses` — 找相似課程

**功能**：透過知識圖譜 Concept/Technology 節點找與指定課程概念最相近的跨系課程。

**算法**：
1. 找種子課程的 `COVERS`/`TEACHES` 出向邊 → Concept/Technology 節點集合
2. 走反向邊找有共同 Concept 的其他課程
3. 以 `shared_concepts`（共享概念數）排序，回傳前 15 名

**參數表**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `course_name` | string | ✓ | 課程名稱，如「機器學習」「演算法」 |

**回傳格式**（`str`，格式化字串）

```
與「機器學習」概念相近的課程（共 12 門）：
- 深度學習（資訊工程學系，3學分） [共享概念：8 個]
- 人工智慧概論（電機工程學系，3學分） [共享概念：6 個]
- ...
```

**分數說明**：`shared_concepts` 越大代表概念重疊越多，通常 5+ 為高度相關。

**top_n**：`tool_find_similar_courses` 呼叫 `graph_service.search_courses_by_concept_cluster(course_name, top_n=15)`

**使用範例**

| 問題 | 典型呼叫 |
|------|---------|
| 有沒有類似機器學習的課？ | `find_similar_courses(course_name="機器學習")` |
| 跨系有沒有和演算法相關的課？ | `find_similar_courses(course_name="演算法")` |

---

### 13. `get_course_knowledge_map` — 知識地圖探索

**功能**：回傳一門課的完整知識地圖：涵蓋的學術概念、使用的技術工具，以及概念重疊最高的相似課程（top 8）。

**內部邏輯**：
1. 查詢課程節點
2. 取出 `USES_TECH`/`COVERS_CONCEPT` 出向邊 → 技術清單（前 10）、概念清單（全部）
3. 呼叫 `search_courses_by_concept_cluster(course_name, top_n=10)` 取相似課程（前 8 門）

**參數表**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `course_name` | string | ✓ | 課程名稱 |

**回傳格式**（`str`，格式化字串）

```
【深度學習】（資訊工程學系，3學分）

使用技術：PyTorch, TensorFlow, Keras, Python
涵蓋概念（共 15 個）：神經網路, 反向傳播, 捲積神經網路, ...

概念重疊最高的相關課程（可延伸學習）：
  - 機器學習（資訊工程學系）[共享 10 個概念]
  - 電腦視覺（資訊工程學系）[共享 8 個概念]
  - ...
```

**使用範例**

| 問題 | 典型呼叫 |
|------|---------|
| 深度學習這門課教什麼？ | `get_course_knowledge_map(course_name="深度學習")` |
| 有沒有和深度學習概念重疊最高的課程？ | `get_course_knowledge_map(course_name="深度學習")` |

**注意**：只查詢 pool 內的 8 門相似課程（graph 結果），**應搭配 `search_courses` 才能找到名稱直接含「深度學習」的其他課程**（參見已知問題 C）。

---

### 14. `get_depts_by_tech` — 查詢技術分布系所

**功能**：多跳圖查詢，找哪些系所的課程教授某技術或概念，並區分必修與選修。

**算法**：
1. 在知識圖譜找 tech 節點
2. 走 `TEACHES`/`COVERS` 反向邊找到相關課程
3. 再往上找課程所屬系所
4. 區分必修課 vs 選修課系所

**參數表**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `tech_name` | string | ✓ | 技術或概念名稱，如「Python」「機器學習」「SQL」 |

**回傳格式**（`str`，格式化字串）

```
教「Python」的系所分布（共 25 門相關課程）：

必修課含此技術的系所（3 個）：
  - 資訊工程學系
  - 資訊管理學系
  - ...

選修課含此技術的系所（8 個）：
  - 電機工程學系
  - ...

相關課程（前 10 門）：
  - Python程式設計（機械工程學系）
  - ...
```

**使用範例**

| 問題 | 典型呼叫 |
|------|---------|
| 什麼科系需要學 Python？ | `get_depts_by_tech(tech_name="Python")` |
| 哪些系重視機器學習？ | `get_depts_by_tech(tech_name="機器學習")` |

---

### 15. `ppr_explore` — Personalized PageRank 廣泛探索

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
以「深度學習」為起點的 PPR 探索結果（all 模式）：
  [課程] 機器學習（資訊工程學系）
  [課程] 電腦視覺（資訊工程學系）
  [教師] 王教授（資訊工程學系）
  [概念] 神經網路
  [系所] 資訊工程學系
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

**score 計算**：NetworkX PPR 原始值（PageRank，範圍 0~1）乘以 1000，值越高代表與種子關係越密切。

**使用範例**

| 問題 | 典型呼叫 |
|------|---------|
| 和機器學習相關的一切有哪些？ | `ppr_explore(seed="機器學習", focus="all", top_k=20)` |
| 深度學習有哪些相關課程？ | `ppr_explore(seed="深度學習", focus="course")` |
| 深度學習連結到哪些老師？ | `ppr_explore(seed="深度學習", focus="instructor")` |
| 我對 AI 有興趣，有哪些系所？ | `ppr_explore(seed="人工智慧,機器學習", focus="dept")` |
