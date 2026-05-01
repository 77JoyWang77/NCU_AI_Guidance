# Curriculum Requirements 資料結構修正與前端視覺化規劃

> 撰寫日期：2026-04-29 / 更新：2026-04-30  
> **Phase 1 ✅ 完成** | **Phase 2 ✅ 完成**  
> 現況：所有 55 個系所節點已從 schedule_draft 合併，圖譜與 Qdrant payload 已重建

---

## 一、問題診斷

### 問題 1：`parse_when` 缺乏系所脈絡

**現況**：`when` 欄位（如「大一上」）被 `build_vector_index.py` 直接轉換成
全域 `when_semesters: ["1_1"]`，並作為向量索引的過濾條件。

**問題根源**：「大一上」是相對於 **該系所課程安排** 的建議修習時間，
跨系所比較毫無意義——資工系大一上的必修課和中文系大一上的必修課
在課程序列上完全不可互換。

**修正方向**：
- `when` 欄位在向量 payload 中必須附帶 `dept` 脈絡（`when_context = "{dept_id}@大一上"`）
- payload 加上 `when_is_dept_scoped: true` 旗標，防止跨系過濾
- 不重新嵌入，改用 Qdrant `set_payload` API 更新 metadata

---

### 問題 2：graduation_rules 中 `course_codes` 缺少課程名稱／學分

**影響的 rule type（共 5 種）**：
| type | 說明 |
|---|---|
| `design_course_min` | 必修設計課程，只列 code |
| `capstone_credit_limit` | 畢業專題學分上限 |
| `internship_limit` | 實習學分上限 |
| `law_finance_group` | 法律/財務必選群 |
| `required_elective` | 指定選修 |

**問題**：規則只有 `course_codes: ["CI3012", ...]`，
圖譜建立時 `_add_rules` 無法顯示課程名稱，前端也無法呈現。

**修正方向**：
- `build_graph.py` 的 `_add_rules` 在處理 `course_codes` 時，
  從 `raw` dict 查表補充 `name` / `credits`
- `when` 一律補為「不限」（這類規則是畢業條件，無時序限制）
- 在 rule 節點新增 `courses_enriched` 欄位供前端直接讀取

---

### 問題 3：純描述型規則無課程列表（84 種 type）

`elective_min`、`dept_required`、`foreign_language` 等規則只有 `description` 文字，
不列出具體課程。這是 **正確設計**（學分下限規定不需要列出所有課程），
但前端需要能明確區分：
- **A 類**：有課程列表的規則（`course_codes` / `courses` / `elective_groups`）
- **B 類**：純學分/條件描述規則（顯示為說明卡片）

---

## 二、實作階段

### Phase 1：前端確認頁面（優先）

> 目標：在資料修正前，先讓使用者視覺化確認資料結構是否符合預期

#### 1.1 後端 API（新增 `backend/app/routes/curriculum.py`）

```
GET /api/curriculum/tree
  → 回傳 College → Department/CBP 階層樹（id + name + program_type）

GET /api/curriculum/dept/{dept_id}
  → 從 curriculum_requirements_114.json 找到對應系所
  → 合併 schedule_draft/{college}/{dept}.json 的 when/verified 資訊
  → 回傳完整系所資料（graduation_rules + required_courses + elective_groups）
```

資料來源：直接讀取 JSON 檔案（不依賴 Qdrant 或 igraph），速度快且不需要重建索引。

#### 1.2 前端新頁面 `/curriculum`（`frontend/src/pages/CurriculumPage.tsx`）

**版面設計**：

```
┌──────────────────────────────────────────────────────────────────┐
│ Navbar                                                           │
├──────────────┬───────────────────────────────────────────────────┤
│ 學院/系所樹  │  系所名稱 ── 最低 128 學分 ── traditional_dept   │
│              │                                                   │
│ ▼ 文學院     │  [畢業規定] [必修時程] [選修群]                   │
│   中文系     │                                                   │
│   英美系     │  ── Tab: 畢業規定 ─────────────────────────────  │
│   法文系     │  ┌──────────────────────┐ ┌───────────────────┐  │
│   文學院學士 │  │ credit_minimum       │ │ dept_required     │  │
│              │  │ 最低 128 學分        │ │ 必修 56 學分      │  │
│ ▶ 理學院     │  └──────────────────────┘ └───────────────────┘  │
│ ▶ 工學院     │  ┌──────────────────────────────────────────────┐ │
│ ▶ 管理學院   │  │ design_course_min  [有課程列表]              │ │
│ ▶ 資電學院   │  │ 至少修 2 門設計課：CI3012・CI3028・CI4024... │ │
│ ▶ 地科學院   │  └──────────────────────────────────────────────┘ │
│ ▶ 生醫學院   │                                                   │
│ ▶ 客家學院   │  ── Tab: 必修時程 ─────────────────────────────  │
│              │  大一上  大一下  大二上  大二下  大三上  大三下  │
│              │  ┌────┐ ┌────┐ ┌────┐  ...                      │
│              │  │課程 │ │課程 │ │課程 │                          │
│              │  │課程 │ │    │ │課程 │                          │
│              │  └────┘ └────┘ └────┘                           │
│              │  ● verified  ○ when_auto（自動推斷）             │
│              │                                                   │
│              │  ── Tab: 選修群 ────────────────────────────────  │
│              │  ▶ 語言訓練類（二擇一）                           │
│              │  ▶ 專業學科類必選（六擇四）                       │
└──────────────┴───────────────────────────────────────────────────┘
```

**顯示規則**：
- `verified: true` → 課程名稱旁顯示綠色 ✓
- `when_auto: true` → 顯示灰色 ○（自動推斷，信度較低）
- `when` 為空 → 顯示「不限」
- graduation_rule 有 `course_codes`/`courses` → 展開列出課程
- graduation_rule 無課程列表 → 純描述卡片（bg-gray-50）

---

### Phase 2：資料修正（前端確認後執行）

#### 2.1 合併 schedule_draft → curriculum_requirements_114.json

新腳本：`scripts/data/merge_schedule_to_curriculum.py`

- 掃描 `data/processed/schedule_draft/**/*.json`
- 依 `id` 比對 curriculum_requirements_114.json 中的系所
- 為每個 `required_course` 加上 `when`, `when_auto`, `verified`, `note`
- 若 schedule_draft 有更新的 graduation_rules 則覆蓋
- 輸出覆蓋 `data/processed/curriculum_requirements_114.json`

```python
# required_course 加入欄位後格式：
{
  "code": "CE1001",
  "name": "工程圖學",
  "credits": 2,
  "when": "大一上",
  "when_auto": false,
  "verified": true,
  "note": ""
}
```

#### 2.2 修正 `build_graph.py`

- `_add_rules()`：當 rule 有 `course_codes` 時，從 `raw` 補 `name`/`credits`，`when` 設「不限」
- `enrich_schedule()`：`suggested_year`/`suggested_semester` 屬性加上 `dept_id` 防止跨系混用
  - 新屬性：`suggested_year_{dept_id}` 或改存成 dict `{"dept": ..., "year": ..., "sem": ...}`

#### 2.3 更新 Qdrant payload（不重新嵌入）

新腳本：`scripts/rag/update_schedule_payload.py`

- 讀取 schedule_lookup（from schedule_draft）
- 用 Qdrant `set_payload` API 更新現有向量點的 metadata
- 新增欄位：
  ```python
  {
    "when_is_dept_scoped": True,
    "when_context": f"{dept_id}@{when_raw}",  # e.g. "dept_civil_eng@大一上"
    "when_raw": when_raw,
    "verified": verified,
    "when_semesters": [...],  # 保留，但標記為 dept-scoped
  }
  ```
- 完全不呼叫 Azure OpenAI Embedding API

#### 2.4 重建圖譜

```bash
python scripts/graph/build_graph.py  # 完整流程
```

---

## 三、`parse_when` 重新設計

**現況問題**：`parse_when("大一上")` → `{"when_semesters": ["1_1"], ...}` 無 dept 脈絡

**修正後**：
```python
def parse_when(when_str: str, dept_id: str = "") -> dict:
    result = {
        "when_raw": when_str or "",
        "when_is_dept_scoped": True,       # 新增：標記為系所相對時間
        "when_context": f"{dept_id}@{when_str}" if dept_id else when_str,
        "when_year_start": 0,
        "when_year_end": 0,
        "when_sem_start": 0,
        "when_sem_end": 0,
        "when_semesters": [],
    }
    # ... 原有解析邏輯 ...
    return result
```

**使用限制**（在 retriever/tools 中加上文件）：
- `when_semesters` 過濾必須同時指定 `dept` filter
- 不應在跨系查詢時使用 `when_semesters` 作為排序依據

---

## 四、資料結構說明（不變動部分）

### graduation_rule type 分類

| 分類 | 典型 types | 前端顯示 |
|---|---|---|
| 學分下限 | `credit_minimum`, `dept_required`, `elective_min` | 描述卡片 |
| 選課規定 | `design_course_min`, `required_elective`, `law_finance_group` | 課程列表卡片 |
| 先修條件 | `prerequisite`, `prerequisite_*` | 條件說明卡片 |
| 外部要求 | `certification_required`, `foreign_language`, `cpe_certification` | badge 卡片 |
| 特殊規定 | `restriction`, `course_substitution`, `equivalent_courses` | 警告卡片 |

---

## 五、驗證方式

1. 前端 `/curriculum` 頁面能正確顯示所有學院系所
2. 必修時程 Tab 中，verified 課程有正確標記
3. design_course_min 等規則能展開顯示課程名稱
4. `scripts/data/merge_schedule_to_curriculum.py` 執行後，curriculum_requirements_114.json 中 required_courses 包含 `when` 欄位
5. `scripts/rag/update_schedule_payload.py` 執行後，Qdrant 中課程點有 `when_is_dept_scoped: true`
6. `scripts/graph/build_graph.py` 重建後，stats 顯示 `suggested_year` 數量符合預期
