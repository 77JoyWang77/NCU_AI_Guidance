# 修課資格資料結構與過濾邏輯

> 文件版本：2026-04-23  
> 對應實作：`data/processed/course_eligibility.json`、`backend/app/services/tools.py`  
> 生成腳本：`scripts/extraction/course_programs/parse_distribution_conditions.py`

---

## 一、設計動機

原始分發條件由多個優先序（P1, P2, P3...）組成，語意是「符合任一優先序即可修」（OR 邏輯）。

舊設計（v2）把所有優先序的欄位取聯集合併成單一 `eligibility` 物件，導致：

- P1 限「電機碩士班一年級」＋ P2 限「電機系（無年級限制）」  
  → merge 後 `program_types=[碩士班]`、`eligible_years=[]`（矛盾）  
  → 無法判斷大學部電機系四年級是否可修

現行設計（v3）**保留每個優先序為獨立 `access_rule`**，查詢時在 Python 端做 OR 邏輯判斷。

---

## 二、JSON 結構（v3）

```json
{
  "course_code": "EE6012",
  "course_name": "適應控制",
  "dept":        "電機工程學系",
  "academic_year": "114",
  "semester":    "1",

  "is_unrestricted":   false,
  "is_grad_only":      false,
  "is_undergrad_open": true,
  "has_special_condition":  false,
  "has_conditional_prereq": false,

  "access_rules": [
    {
      "program_types":        ["master", "phd"],
      "dept_include":         ["電機工程學系碩士班", "電機工程學系博士班"],
      "dept_exclude":         [],
      "college_include":      [],
      "college_exclude":      [],
      "years":                [],
      "open_to_minor":        false,
      "minor_include":        [],
      "open_to_double_major": false,
      "double_major_include": [],
      "open_to_credit_prog":  false,
      "credit_prog_include":  [],
      "open_to_2nd_spec":     false,
      "spec_include":         [],
      "open_to_edu_program":  false,
      "edu_program_include":  [],
      "open_to_cross_school": false,
      "identity_flags":       [],
      "section_include":      [],
      "gender_restriction":   [],
      "student_id_parity":    []
    },
    {
      "program_types":   [],
      "dept_include":    ["電機工程學系"],
      "college_include": [],
      "years":           [4],
      ...
    }
  ],

  "course_relations": {
    "prereq_codes":   [],
    "coreq_codes":    [],
    "conflict_codes": [],
    "forbidden_codes": []
  },

  "unparseable_conditions": [],
  "raw_conditions": ["P1: 學制:限碩士班、博士班。...  | P2: 系所:限電機工程學系。年級:限四年級。"]
}
```

---

## 三、欄位語意

### 3.1 Top-level 旗標

| 欄位 | 型別 | 說明 |
|------|------|------|
| `is_unrestricted` | bool | 無任何限制（全校皆可修）；`access_rules` 為空或含一條完全空的 rule |
| `is_grad_only` | bool | 所有 rule 都僅允許研究所學制（`program_types` 全為研究所，或 `dept_include` 名稱全以碩士班/博士班/研究所結尾） |
| `is_undergrad_open` | bool | 至少一條 rule 允許大學部（`is_unrestricted=True` 或任一 rule 非 grad-only） |
| `has_special_condition` | bool | 含無法完全結構化的條件（如「檢定成績達 50 分以上」） |
| `has_conditional_prereq` | bool | 先修只在部分優先序存在（非所有 P 都要求先修） |

### 3.2 access_rules 每條 rule 的欄位

**空 list = 不限制**（此欄位不做限制）

| 欄位 | 說明 |
|------|------|
| `program_types` | 學制：`"bachelor"` / `"master"` / `"phd"` / `"master_inservice"` / `"master_industry"` |
| `dept_include` | 指定可修系所名稱（完整名稱，如「資訊工程學系」） |
| `dept_exclude` | 排除系所 |
| `college_include` | 指定可修學院（如「資訊電機學院」） |
| `college_exclude` | 排除學院 |
| `years` | 可修年級；`[2,3,4]` 代表「非一年級」；空 = 不限 |
| `open_to_minor` | 輔系學生可修 |
| `minor_include` | 輔系細目（空 = 所有輔系） |
| `open_to_double_major` | 雙主修可修 |
| `double_major_include` | 雙主修細目 |
| `open_to_credit_prog` | 學分學程可修 |
| `open_to_cross_school` | 申請校學士可修 |
| `identity_flags` | 其他身份旗標（如 `"exchange"` 交換生） |
| `section_include` | 班別限制（A/B/C），高中生探索場景可忽略 |
| `gender_restriction` | 性別限制（體育課），可忽略 |
| `student_id_parity` | 學號奇偶（分班），可忽略 |

### 3.3 course_relations

| 欄位 | 語意 |
|------|------|
| `prereq_codes` | 先修課號（修過才能選） |
| `coreq_codes` | 同修課號（同學期必須一起選，通常是實驗課配講授課） |
| `conflict_codes` | 擋修課號（已修過就不能再選） |
| `forbidden_codes` | 禁修課號（不能同時選） |

---

## 四、過濾邏輯（`_matches_access_rule`）

位置：`backend/app/services/tools.py`

```python
def _matches_access_rule(rule, student_dept, student_year,
                          program_type="bachelor",
                          minor_depts=None, double_major_depts=None,
                          student_college=""):
    # 學制（空 = 不限）
    if rule["program_types"] and program_type not in rule["program_types"]:
        return False

    # 年級（空 = 不限）
    if rule["years"] and student_year not in rule["years"]:
        return False

    # 系所 / 學院（兩者皆空 = 不限；否則符合任一即可）
    no_restriction = not rule["dept_include"] and not rule["college_include"]
    dept_ok    = no_restriction or (student_dept in rule["dept_include"])
    college_ok = no_restriction or (student_college in rule["college_include"])
    minor_ok   = rule["open_to_minor"] and (
        not rule["minor_include"] or any(d in rule["minor_include"] for d in minor_depts)
    )
    double_ok  = rule["open_to_double_major"] and (...)
    if not (dept_ok or college_ok or minor_ok or double_ok):
        return False

    # 排除（dept_exclude / college_exclude）
    if student_dept in rule["dept_exclude"]:
        return False
    if student_college and student_college in rule["college_exclude"]:
        return False

    return True
```

**`can_student_take(course_metadata, dept, year, program_type)`**：

```python
def can_student_take(course_metadata, student_dept, student_year, ...):
    if course_metadata.get("is_unrestricted"):
        return True
    student_college = retriever.get_dept_college(student_dept)  # 查 dept_college_map.json
    return any(
        _matches_access_rule(r, student_dept, student_year, ..., student_college)
        for r in course_metadata["access_rules"]
    )
```

---

## 五、系所學院對照表（`dept_college_map.json`）

位置：`data/processed/dept_college_map.json`  
生成：`parse_distribution_conditions.py` 執行時自動輸出  
載入：`retriever.get_dept_college(dept)` → lru_cache

格式：
```json
{
  "資訊工程學系": "資訊電機學院",
  "電機工程學系": "資訊電機學院",
  "土木工程學系": "工學院",
  ...
}
```

共 83 個系所，無同系所對應不同學院的衝突。

---

## 六、驗證案例

| 課程 | raw 條件 | 學生 | 結果 | 說明 |
|------|---------|------|------|------|
| EE6012 適應控制 | P1: 電機碩博士班 \| P2: 電機系四年級 | 電機系四年級 | ✅ | 命中 rule[1] |
| EE6012 適應控制 | 同上 | 資工系一年級 | ❌ | 兩條 rule 皆不符 |
| AP1002 大氣科學通論 | P1: 限地球科學學院 | 地科系一年級 | ✅ | college_include 命中 |
| AP1002 大氣科學通論 | 同上 | 資工系一年級 | ❌ | 資電學院不在 college_include |
| BA2023 投資學 | P2: 限非管理學院三四年級 | 中文系三年級 | ✅ | rule[2] college_exclude 放行 |
| BA2023 投資學 | 同上 | 企管系三年級 | ✅ | rule[0] 管理學院三四年級放行 |
| BA2023 投資學 | 同上 | 中文系一年級 | ❌ | 年級不符（rule[2] 限三四年級） |

---

## 七、統計（114 學年，共 3,765 個課號）

| 項目 | 數量 |
|------|------|
| access_rules 總數 | 7,282 條 |
| 無分發條件（is_unrestricted） | 1,220 |
| 純研究所課程（is_grad_only） | 1,116 |
| 大學部可修（is_undergrad_open） | 2,649 |
| 有 dept_include 限制 | 2,503 |
| 有 dept_exclude 排除 | 47 |
| 有 college_include 限制 | 382 |
| 有 college_exclude 排除 | 63 |
| 有年級限制 | 1,748 |
| 有學制限制 | 1,035 |
| 輔系可修 | 272 |
| 雙主修可修 | 341 |
| 先修課程要求 | 142 |
| 同修課程要求 | 16 |
| 擋修限制 | 48 |
| 禁修限制 | 18 |

---

## 八、資料來源與更新

| 資料 | 位置 | 生成方式 |
|------|------|---------|
| 修課資格 JSON | `data/processed/course_eligibility.json` | `python scripts/extraction/course_programs/parse_distribution_conditions.py` |
| 系所學院對照 | `data/processed/dept_college_map.json` | 同上（自動一起產生） |
| ChromaDB metadata | `data/processed/chroma_db/` | `python scripts/rag/build_vector_index.py --metadata-only`（不需要 API key） |

### 指定課程類型（`course_relations`）

| 動詞 | 欄位 | 語意 |
|------|------|------|
| 先修 | `prereq_codes` | 必須修過才能選 |
| 同修 | `coreq_codes` | 同學期必須一起選（通常是實驗課配講授課）|
| 擋修 | `conflict_codes` | 已修過就不能再選（相似課衝突）|
| 禁修 | `forbidden_codes` | 不能同時選（同課不同班互斥）|
