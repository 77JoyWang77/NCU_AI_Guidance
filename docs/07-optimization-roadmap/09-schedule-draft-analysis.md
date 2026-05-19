# schedule_draft 與 eligibility 全面分析與圖譜強化規劃

> 基於 2026-05-19 實際資料分析（568 筆課程-系所對應（含組別）、3841 筆 eligibility）
> 資料來源：curriculum_requirements_114.json（由 schedule_draft/ 合併產生，已修正錯誤）

---

## 一、schedule_draft 的真實資料結構

### 1.1 目錄組織（按學院/系所）

```
data/processed/schedule_draft/
├── 資訊電機學院/
│   ├── 資訊工程學系.json       ← program_type: "traditional_dept"
│   ├── 電機工程學系.json
│   └── 資訊電機學院學士班.json
├── 工學院/
│   ├── 機械工程學系.json       ← program_type: "dept_with_groups"（含多組）
│   └── ...
└── ...
```

**兩種主要格式**：

```jsonc
// 格式 A：一般系所（traditional_dept）
{
  "id": "dept_computer_science",
  "name": "資訊工程學系",
  "program_type": "traditional_dept",
  "required_courses": [
    { "code": "MA1003", "name": "微積分上", "credits": 3,
      "when": "大一上", "when_auto": false, "verified": true }
  ]
}

// 格式 B：含組別的系所（dept_with_groups）
{
  "name": "機械工程學系",
  "program_type": "dept_with_groups",
  "groups": [
    {
      "id": "dept_me_advanced_materials",
      "group_label": "先進材料與精密製造組",
      "required_courses": [...]
    },
    {
      "id": "dept_me_optomechatronics",
      "group_label": "光機電工程組",
      "required_courses": [...]
    }
  ]
}
```

每筆課程條目的欄位：

| 欄位 | 說明 | 備註 |
|------|------|------|
| `code` | 課程代碼 | |
| `when` | 建議修習時間，如 `"大一上"`、`"大二下"`；學士班有時為範圍格式 `"大一上~大一下"` | 系所相對值 |
| `when_auto` | True = AI 推斷，False = 人工填寫 | **343/568 為 auto（60%）** |
| `verified` | **目前全部為 True（568/568）** | 此欄位已無辨別意義 |
| `note` | 補充說明（大多為空） | |

---

## 二、`load_schedule_lookup()` 的根本性設計缺陷

### 2.1 問題：以課號為 key，後者覆蓋前者

```python
# build_vector_index.py 目前的實作（有問題）
def _index_courses(courses: list, dept_id: str):
    for rc in courses:
        code = rc.get("code", "").strip()
        when = rc.get("when", "")
        if code:
            parsed = parse_when(when, dept_id=dept_id)
            parsed["verified"] = verified
            lookup[code] = parsed  # ← 同一課號後者覆蓋前者！
```

**實際影響數據（2026-05-19 修正後資料）**：

- 568 筆課程-系所對應（含組別），**全部 568 筆都有 when 值**
- **10 個課號有 when 衝突**，可分為三類：

**A 類：學士班跨學期格式（5 個，EE 課群）**

| 課號 | 課名 | 系所 A | when A | 系所 B | when B |
|------|------|--------|--------|--------|--------|
| EE1007 | 計算機概論實習 | 電機工程學系 | 大一上 | 資訊電機學院學士班 | 大一上~大一下 |
| EE1003 | 計算機概論I | 電機工程學系 | 大一上 | 資訊電機學院學士班 | 大一上~大一下 |
| EE2016 | 數位系統導論 | 電機工程學系 | 大一上 | 資訊電機學院學士班 | 大一上~大二下 |
| EE1006 | 數位邏輯實驗 | 電機工程學系 | 大一下 | 資訊電機學院學士班 | 大一上~大二下 |
| EE1009 | 工程數學-線性代數 | 電機工程學系 | 大一上 | 資訊電機學院學士班 | 大一上~大一下 |

學士班的「~」格式代表「這段時間內皆可修」，並非與電機系的排程矛盾，是**表示方式不同**。

**B 類：同系不同組別（3 個）**

| 課號 | 課名 | 組別 A | when A | 組別 B | when B |
|------|------|--------|--------|--------|--------|
| MA1013 | 計算機概論I | 數學系計算與資料科學組 | 大一上 | 數學系數學科學組 | 大一下 |
| MA2021 | 機率論 | 數學系計算與資料科學組 | 大二上 | 數學系數學科學組 | 大二下 |
| ME3081 | 流體力學 | 機械系設計與分析組 / 先進材料組 | 大二下 | 機械系光機電工程組 | 大三下 |

這些是**刻意的組別差異**，反映同系不同學習路徑的設計。

**C 類：真正的跨系衝突（2 個）**

| 課號 | 課名 | 系所 A | when A | 系所 B | when B |
|------|------|--------|--------|--------|--------|
| CM1008 | 普化實驗 | 光電科學與工程學系、生命科學系 | 大一上 | 大氣科學學系 | **大一下** |
| EG2001 | 工程統計學 | 土木工程學系 | 大二下 | 工學院學士班 | **大三上~大三下** |

這 2 筆才是真正需要在 `load_schedule_lookup()` 特殊處理的案例——同一門課在不同系確實有不同的修課時間點。

進入 Qdrant 的 `when_raw` 完全取決於處理順序，**不代表任何特定系所的規劃**。

### 2.2 Qdrant payload 的連帶問題

由於 Qdrant 的課程文件是以「獨立課程」（unique course_code）為單位儲存，而 `when_raw` 是「系所相對」的資訊，兩者天然不匹配：

```
Qdrant document: "微積分（MA1003）"
   when_raw: "大一上"  ← 來自哪個系？不知道，且可能是錯的
   when_semesters: ["1_1"]  ← 只反映最後一個被處理系所的排程
```

**真正的問題**：搜尋「大一上的必修課」時，用 `when_semesters: "1_1"` 過濾，會漏掉那些在某些系大一上修但 payload 被其他系覆蓋的課，也會誤包含那些在某些系大二才修但被大一系覆蓋的課。

---

## 三、eligibility 的複雜結構

### 3.1 基本結構

```
3841 筆課程 eligibility
  ├── 有 access_rules 格式：3211 筆
  │     ├── 只有 1 條 rule：1182 筆（相對簡單）
  │     └── 有 2 條以上 rule：2029 筆（複雜）
  └── 無 access_rules（舊格式）：0 筆（已全部轉換）
```

### 3.2 access_rules 複雜性分析

每條 rule 是「OR 關係」（任一 rule 符合即可修課），同一 rule 內所有條件是「AND 關係」：

```json
{
  "access_rules": [
    {
      "dept_include": ["資訊工程學系"],
      "years": [3, 4],              // 資工系 大三大四才能修
      "section_include": [],
      "program_types": [],
      ...
    },
    {
      "dept_include": [],           // 空 = 不限系所
      "years": [],                  // 空 = 不限年級
      "program_types": ["master"],  // 研究所學生不限
      ...
    }
  ]
}
```

**各類限制條件統計**：

| 欄位 | 有值的 rule 數 | 說明 |
|------|--------------|------|
| `dept_include` | 2559 | 限定特定系所 |
| `years` | 3210 | 限定修課年級 |
| `section_include` | 364 | **限定分班（如只有 B 班）** |
| `gender_restriction` | 378 | 性別限制 |
| `student_id_parity` | 132 | 奇偶學號限制（分流用） |

### 3.3 為何難以推斷「課程難度/適合年級」

**情況 1：跨系所年級差異**（同一門課對不同系是不同年級）

```
MA1003 微積分上（access_rules 共 6 條）：
  Rule 1: dept=[地科學院學士班, 大氣系, 太空系] + years=[1] + student_id_parity=[odd]
  Rule 2: dept=[地科系, 地科學院學士班, 大氣系, 太空系] + years=[1]
  Rule 3: dept=[地科學院學士班, 大氣系, 太空系] + years=[1] + student_id_parity=[even]
  ...（班次分流）
```

這門課對地科學院系所限制大一修，但對其他系沒有限制（可能任何年級都能選修）。想說「微積分是大一課」是對的，但不能套用於全校。

**情況 2：section_include 的分班問題**

```
AP3037（大氣系某課）：
  Rule: dept_include=["大氣科學學系"] + section_include=["B"]
  
→ 只有大氣系 B 班可以修！A 班不能修。
```

這是「課程對應到特定班級」的情況，根本無法用年級來描述難度。

**情況 3：部分系限制、部分開放**

```
AC6001（某會計課）：
  Rule 1: dept=[會計研究所碩士班] + years=[1]  ← 碩一才能修
  Rule 2: dept=[會計研究所碩士班] + years=[]   ← 同系所無年級限制
  Rule 3: dept=[] + years=[]                    ← 無系所限制（任何人）
  Rule 4: program_types=[master]               ← 研究所學生
  Rule 5: program_types=[bachelor]             ← 大學生
```

這門課：對碩士班學生有特定規則，對其他人完全開放。從 eligible_years 推斷難度幾乎不可能。

**情況 4：only eligible_years 不足**

目前 `build_vector_index.py` 的 `eligible_years` 計算邏輯：

```python
# 只取「非全研究所」規則的 years 聯集
for r in access_rules:
    if not r.get("program_types") or any(pt not in _GRAD for pt in r["program_types"]):
        undergrad_years.update(r.get("years", []))
```

例如一門課 Rule 1 允許大一（years=[1]）、Rule 2 允許大三（years=[3]）、Rule 3 無限制（years=[]），最終 `eligible_years = {1, 3}` 或因為 Rule 3 的 `years=[]` 代表無限制、不貢獻任何值 → `eligible_years = {1, 3}`，根本無法解讀「難度」。

---

## 四、現行 `search_courses` year/sem filter 的問題

### 4.1 設計意圖 vs 實際行為

```python
# tools.py 的過濾邏輯
if year is not None and sem is not None:
    conditions.append({"when_semesters": {"$contains": f"{year}_{sem}"}})
```

**問題**：`when_semesters` payload 是從 `load_schedule_lookup()` 來的，而該函式會以課號為 key 後者覆蓋前者，因此這個 filter 只反映「最後一個被處理的系所的排程」。

**具體問題**：
- 查「大一上的課」(`year=1, sem=1`) 會漏掉那些在某些系大一上修、但被其他系大二排程覆蓋的課
- 查詢結果會因為 JSON 檔案讀取順序而改變（不穩定）
- `year`/`sem` filter 若不同時帶 `dept` filter，語意就是錯的（因為 when 是系所相對的）

### 4.2 更嚴重：LLM 的誤解

工具 schema 目前寫：
```
"year": "年級過濾，例如大一填 1，大三填 3"
"sem": "學期，1=上學期，2=下學期"
```

LLM 可能把 `year=1` 解讀為「大一的課」，但這實際上是不可靠的過濾，因為：
- 同一門課對不同系有不同的「推薦年級」
- Qdrant payload 只記錄一個系的值

**建議**：除非同時帶 `dept` filter，`year`/`sem` 過濾應標示為「限縮意義不明，不建議單獨使用」。

---

## 五、知識圖譜強化的正確方向

### 5.1 現有圖譜邊結構

```
(Dept) --[REQUIRED]--> (Course)
(Dept) --[HAS_CURRICULUM]--> (Course)  ← 選修
```

這個設計本身是對的——**每條 REQUIRED 邊天然是系所相對的**，因此 `when` 資訊應該放在邊的屬性上，而不是 Course 節點上。

### 5.2 方案 A：在 REQUIRED 邊加 when 屬性（推薦）

when 資料有兩種格式：
- **點格式**：`"大一上"` → 可解析為單一 year/sem
- **範圍格式**：`"大三上~大三下"` → 無法簡化成單一 year/sem，需存 start/end

因此邊屬性應設計為 start/end 雙欄位：

```
(Dept: 地科系) --[REQUIRED {
  when_raw:       "大一上",
  when_year_start: 1,  when_sem_start: 1,
  when_year_end:   1,  when_sem_end:   1
}]--> (Course: MA1003)

(DeptGroup: 機械系_光機電組) --[REQUIRED {
  when_raw:       "大三上~大三下",
  when_year_start: 3,  when_sem_start: 1,
  when_year_end:   3,  when_sem_end:   2
}]--> (Course: ME3081)

(Dept: 資訊電機學院學士班) --[REQUIRED {
  when_raw:       "大一上~大一下",
  when_year_start: 1,  when_sem_start: 1,
  when_year_end:   1,  when_sem_end:   2
}]--> (Course: EE1003)
```

`when_raw` 保留原始字串供顯示用；`when_year_start/end`、`when_sem_start/end` 用於圖查詢排序與比較。`verified` 與 `when_auto` 不放入圖譜邊（前者全部為 True 無意義，後者只是資料來源記錄，已驗證的資料不需保留此旗標）。

**好處**：
- 每條邊有獨立的 when，不同系同一門課的排程互不干擾
- `get_dept_courses` 讀取邊屬性回傳 `when_raw` 即可正確顯示
- 天然支援比較「A系和B系何時修微積分」
- 範圍格式（如學士班的彈性選修期間）也能正確表達

**實作位置**：`scripts/graph/build_graph.py`，需在寫 REQUIRED 邊時查 schedule_lookup，lookup 改為 `{(dept_id, code): {when_raw, when_year_start, when_sem_start, when_year_end, when_sem_end}}`。

### 5.3 為何 YearLevel 節點方案不合適

```
// 提議：
(Course) --[RECOMMENDED_AT]--> (YearLevel {year: 2, sem: 1})
```

**問題**：
- 同一個 YearLevel 節點會被多個系的多門課連接，失去「哪個系在大二上修哪些課」的脈絡
- 若改為「系所相對的 YearLevel」，每個系都要建自己的 YearLevel 節點，數量爆炸（30 個系 × 8 個學期 = 240 個節點），且沒有跨系比較的意義

**結論**：邊屬性方案是正確的做法，不需要 YearLevel 節點。

### 5.4 Dept_Group 節點的處理

機械系、數學系等有分組的系所，需在圖譜中有 DeptGroup 節點：

```
(Dept: 機械工程學系)
  └── (DeptGroup: 機械工程學系_先進材料與精密製造組)
        --[REQUIRED {when_raw:"大一上", when_year_start:1, when_sem_start:1,
                     when_year_end:1, when_sem_end:1}]--> (Course: MA1003)
  └── (DeptGroup: 機械工程學系_光機電工程組)
        --[REQUIRED {when_raw:"大三上~大三下", when_year_start:3, when_sem_start:1,
                     when_year_end:3, when_sem_end:2}]--> (Course: ME3081)
```

目前圖譜是否已有 Dept_Group 節點需確認，若無則需新增。

---

## 六、verified 與 when_auto 的處置

`verified`（568/568 全為 True）與 `when_auto`（資料來源記錄）兩個欄位**均不應進入圖譜或 Qdrant**：

| 欄位 | 現況 | 結論 |
|------|------|------|
| `verified` | 568/568 全為 True，無區別意義 | **直接捨棄** |
| `when_auto` | 記錄 when 是 AI 推斷還是人工填寫，僅資料來源用途 | **直接捨棄**（資料已驗證，來源旗標無操作價值） |

schedule_draft 中的 when 資料已是最終版本（無論原始來源為何），下游系統只需使用 `when_raw` 及解析出的 start/end 欄位。

---

## 七、難度推斷的可行策略

單靠 eligibility 或 schedule_draft 都無法可靠推斷難度，但組合多個訊號可以得出較合理的估計：

### 7.1 「年級難度標籤」推算公式

```python
def infer_course_level(course_code: str) -> str:
    """
    來源優先序：
    1. schedule_draft when（跨系取最小 when_year_start）
    2. eligible_years 中的最小年級（排除 years=[] 的 rule）
    3. 無法推斷 → "unknown"
    """
    years = [
        info["when_year_start"]
        for dept_courses in schedule_lookup.values()
        if course_code in dept_courses
        for info in [dept_courses[course_code]]
        if info.get("when_year_start", 0) > 0
    ]
    
    if years:
        year = min(years)
    elif eligible_years:
        year = min(eligible_years)
    else:
        return "unknown"
    
    return {1: "introductory", 2: "core", 3: "advanced", 4: "capstone"}.get(year, "unknown")
```

### 7.2 複雜 eligibility 情況的處理策略

| 情況 | 處理方式 |
|------|---------|
| 全部 rule 都有 `years` | 取所有 `years` 的最大公約數作為最低年級 |
| 部分 rule 有 `years=[]`（無限制） | 說明此課「開放給較多年級」，不適合推斷難度 |
| 有 `section_include` | 標記為「分班修課，難度因班而異」 |
| 全部 rule 都是 `program_types=[master/phd]` | 標記為研究所課程 |
| 混合研究所+大學規則 | 分開處理，只取大學部的 rules 推斷 |

### 7.3 對使用者的實際回答策略

```
多系 when 一致 → 「建議在大一上修習」
多系 when 不一致 → 「各系安排不同，資工系通常在大二、電機系在大一」
只有 eligible_years → 「限大X年級以上修習」（用 eligibility 語言）
無法推斷 → 不提年級，說「建議以學校課程規劃公告為準」
```

---

## 八、Qdrant `parse_when()` 欄位分析與建議

### 8.1 現有欄位逐一檢視

```python
def parse_when(when_str: str, dept_id: str = "") -> dict:
    return {
        "when_raw":          when_str or "",
        "when_is_dept_scoped": True,
        "when_context":      f"{dept_id}@{when_str}" if (dept_id and when_str) else (when_str or ""),
        "when_year_start":   0,
        "when_year_end":     0,
        "when_sem_start":    0,
        "when_sem_end":      0,
        "when_semesters":    [],
    }
```

`load_schedule_lookup()` 的結果（`sched`）在 `build_course_doc()` 裡有**兩個用途**，需分開處理：

**用途 A：寫進 embedding document text**（影響向量搜尋）
```python
# 現在（單一系）
if sched.get("when_raw"):
    parts.append(f"建議修習：{sched['when_raw']}")
# → "建議修習：大一上"
```

**用途 B：寫進 Qdrant payload**（payload 欄位）
```python
"when_semesters":  sched.get("when_semesters", []),
"when_raw":        sched.get("when_raw", ""),
"when_year_start": sched.get("when_year_start", 0),
"when_year_end":   sched.get("when_year_end", 0),
"when_sem_start":  sched.get("when_sem_start", 0),
"when_sem_end":    sched.get("when_sem_end", 0),
"schedule_verified": sched.get("verified", False),   # ← 也在這，全部為 False（已失效）
```

各欄位問題與建議：

| 欄位 | 問題 | 建議 |
|------|------|------|
| `when_raw` | 只反映某一個系的排程 | **用途 A 保留，改為完整清單格式；payload 移除** |
| `when_is_dept_scoped` | 固定為 True，無過濾價值 | **移除** |
| `when_context` | 單一系格式，概念可用但需重設計 | **重新設計為 `dept_schedule` 清單**（見 8.2） |
| `when_year_start/end` | 哪個系的年？單獨過濾無意義 | **payload 移除**（圖譜邊保留） |
| `when_sem_start/end` | 同上 | **payload 移除**（圖譜邊保留） |
| `when_semesters` | 只有同時帶 dept filter 才有意義 | **移除**（連同 year/sem tool 參數一起拿掉） |
| `schedule_verified` | 對應 `verified` 欄位，全部為 False（未生效）或 True | **移除** |

### 8.2 `dept_schedule`：取代舊欄位的新設計

**用途 A（embedding text）改為完整清單**：

```python
# build_vector_index.py — 建立 document text 時
dept_schedule_lines = []
for dept_id, dept_courses in schedule_lookup.items():   # schedule_lookup 已改為 {dept_id: {code: ...}}
    if course_code in dept_courses:
        dept_name = dept_id_to_name[dept_id]
        when      = dept_courses[course_code]["when_raw"]
        dept_schedule_lines.append(f"{dept_name}: {when}")

if dept_schedule_lines:
    parts.append(f"建議修習：{'、'.join(dept_schedule_lines)}")
# → "建議修習：資工系: 大一上、電機系: 大一上、機械系_光機電組: 大一下"
# 向量搜尋時「大一」、「入門」等詞可正常命中
```

**用途 B（payload）改為 `dept_schedule` list**（顯示用，不過濾）：

```python
payload["dept_schedule"] = dept_schedule_lines
# 例：["資訊工程學系: 大一上", "電機工程學系: 大一上", "機械工程學系_光機電工程組: 大一下"]
```

LLM 在 `search_courses` / `get_course_detail` 收到後可直接引用，不需要再查圖譜就能回答「哪些系幾年級修這門課」。

### 8.3 `search_courses` year/sem filter 的處置

- `year`/`sem` 參數透過 `when_semesters` 做 MatchAny 過濾，移除 `when_semesters` 後此 filter 失效
- 建議：從 tool schema 移除 `year`/`sem` 參數；若有需要用年級過濾，改由圖譜查詢（指定 dept + 從 REQUIRED 邊的 `when_year_start` 過濾）

### 8.4 修改後 Qdrant 能回答的問題變化

| 問題 | 修改前 | 修改後 |
|------|--------|--------|
| 「大一上有哪些課？」（不指定系） | 不可靠結果 | 說明需指定系所，改由圖譜查詢 |
| 「資工系大一要修什麼？」（有 dept） | when_semesters filter（不準） | 直接查圖譜 REQUIRED 邊 ✓ |
| 「微積分哪些系要修、幾年級修？」 | 只有一個系的資訊 | `dept_schedule` 清單完整呈現 ✓ |
| 「有哪些機器學習相關課程？」 | 正常 | 完全不受影響 ✓ |
| 「有哪些適合大一的入門課？」 | 不可靠 | 留待 difficulty_level 實作後支援 |

---

## 九、實施優先順序

### 第一階段：修正設計缺陷（不改圖，只修 build_vector_index.py）

**B1. 修正 `load_schedule_lookup()`**

現在的問題：key 是 `course_code`（後者覆蓋前者），且結果只被用來取「某一個系的 when」。

修正後：key 改為 `{dept_id: {course_code: ...}}`，讓每個系所的 when 都被保留。輸出欄位只存圖譜與 embedding 需要的資訊，移除 `verified`、`when_auto`：

```python
# {dept_id: {course_code: {when_raw, when_year_start, when_sem_start, when_year_end, when_sem_end}}}
def load_schedule_lookup() -> dict[str, dict[str, dict]]:
    lookup: dict[str, dict[str, dict]] = {}
    for college_dir in SCHEDULE_DIR.iterdir():
        for dept_file in college_dir.glob("*.json"):
            data = load_json(dept_file)
            dept_id = data.get("id", dept_file.stem)
            def _index(courses, did):
                for rc in courses:
                    code = rc.get("code", "").strip()
                    when = rc.get("when", "")
                    if code and when:
                        y_start, s_start, y_end, s_end = parse_when_range(when)
                        lookup.setdefault(did, {})[code] = {
                            "when_raw":        when,
                            "when_year_start": y_start,
                            "when_sem_start":  s_start,
                            "when_year_end":   y_end,
                            "when_sem_end":    s_end,
                        }
            _index(data.get("required_courses", []), dept_id)
            for grp in data.get("groups", []):
                _index(grp.get("required_courses", []), grp.get("id", dept_id))
    return lookup
```

這個函式的結果在 `build_course_doc()` 有兩個用途（見第八章）：
- **用途 A**：組合所有系的 `when_raw` 寫進 embedding text（`"建議修習：資工系: 大一上、電機系: 大一上"`）
- **用途 B**：組合成 `dept_schedule` list 存入 payload（LLM 顯示用）

此外，這個 lookup 也提供給 `build_graph.py` 使用，在 REQUIRED 邊寫入 `when_raw` 與 start/end 屬性（第二階段）。

**B2. 修改 `build_course_doc()` 的 payload 與 document text**

移除舊欄位：`when_raw`、`when_is_dept_scoped`、`when_context`、`when_year_start/end`、`when_sem_start/end`、`when_semesters`、`schedule_verified`（原本全為 False/True 無意義）

新增：`dept_schedule` list（見 8.2）；document text 改用完整清單格式

**B3. 從 tool schema 移除 `year`/`sem` 參數**（`when_semesters` 移除後 filter 失效，直接拿掉）

### 第二階段：圖譜強化（需重建圖）

**G1. 以 B1 的 `load_schedule_lookup()` 結果為來源，寫入 REQUIRED 邊屬性**

**G2. REQUIRED 邊加 when 屬性**（per-dept）：

```python
# build_graph.py
sched = schedule_lookup.get(dept_id, {}).get(course_code, {})
ensure_edge(G, dept_nid, course_nid, relation="REQUIRED",
    when_raw        = sched.get("when_raw", ""),
    when_year_start = sched.get("when_year_start", 0),
    when_sem_start  = sched.get("when_sem_start", 0),
    when_year_end   = sched.get("when_year_end", 0),
    when_sem_end    = sched.get("when_sem_end", 0),
)
```

**G3. `get_dept_courses` 回傳加 `when_raw` 欄位**

LLM 看 `when_raw` 就夠（如 `"大一上"`、`"大三上~大三下"`），不需要 `when_year_start`。
`when_year_start` 只在 `graph_service.py` 內部排序用（讓課程列表按年級從小到大排），不回傳給 LLM：

```python
# graph_service.py
edge_data = G.es[G.get_eid(dept_nid, course_nid)].attributes()
courses.append({
    "name":     ...,
    "credits":  ...,
    "type":     "必修",
    "when_raw": edge_data.get("when_raw", ""),        # 回傳給 LLM
    "_sort_key": edge_data.get("when_year_start", 9), # 僅排序用，不輸出
})
# 最後 sorted(courses, key=lambda x: x.pop("_sort_key"))
```

**G4. 在 system prompt 加說明**，讓 LLM 能把 `when_raw` 轉成按年級分組的回答格式

### 第三階段：高階功能（選做）

- `SEQUENCE_BEFORE` 邊：整合 prereq 資料，建立課程前後修順序
- `difficulty_level` 作為圖譜 Course 節點屬性（跨系多數決，另行規劃）
- search_courses 新增 `difficulty` 過濾參數（`introductory`/`advanced`，待 difficulty_level 完成後）

---

## 十、能新增回答的問題清單

修正後可回答、但現在回答品質不佳的問題：

| 問題 | 目前問題 | 修正後 |
|------|---------|--------|
| 「資工系大一要修哪些課？」 | get_dept_courses 無 when 資訊 | 回傳含 `when_raw` 的課程清單（內部已按年級排序） |
| 「讀電機系第一年要準備什麼？」 | 同上 | 回傳大一上+大一下的必修清單 |
| 「A系和B系都有修微積分，哪個系排得比較早？」 | 無法跨系比較 when | 直接比較兩系 REQUIRED 邊的 `when_raw` |
| 「這門課適合幾年級修？」 | 靠 eligible_years 推斷不準確 | 圖譜 REQUIRED 邊 when_raw 提供系所相對資訊 |
| 「有沒有適合大一選的通識課？」 | year/sem filter 不可靠 | 待 difficulty_level 完成後支援 |
