# 分發條件欄位全覽與知識圖譜整合策略

> 更新：2026-04-08
> 資料來源：`data/raw/courses/114_1+2`、`data/raw/graduate_courses/114_1+2`
> 解析腳本：`scripts/graph/parse_distribution_conditions.py`
> 輸出：`data/processed/course_eligibility.json`

---

## 一、原始格式說明

每門課的 `分發條件.優先順序列表` 是一個陣列，每個元素有一行文字：

```
系所:限資訊工程學系、雙主修-資訊工程學系。年級:限三年級、四年級。學制:限學士班。指定課程:必須先修CI2004。
```

格式規律：`欄位名:限內容。欄位名:限內容。...`（以「。」分隔欄位）

多個優先序代表「任一條件符合即可修」，解析時取聯集。

---

## 二、所有欄位類型（共 9 種）

### ✅ 已解析 → 存入 course_eligibility.json

| 欄位 | 出現次數 | 輸出欄位 | 說明 |
|------|---------|---------|------|
| `系所` | 5,981 | `dept_include` / `dept_exclude` / 各 open_to_* | 含 5 種特殊前綴 |
| `年級` | 3,770 | `eligible_years: list[int]` | 1=大一，99=延修生；空=不限 |
| `學制` | 1,962 | `program_types: list[str]` | bachelor/master/phd/master_inservice/master_industry |
| `身份` | 1,159 | `open_to_cross_school` / `identity_flags` | 申請校學士/交換生/外籍生/重修生 |
| `指定課程` | 642 | `prereq_codes` / `coreq_codes` / `conflict_codes` / `forbidden_codes` | 見第三節 |
| `學院` | 580 | `college_include` / `college_exclude` | 含「非」排除邏輯 |

### ⚪ 略過（不影響 RAG 問答）

| 欄位 | 出現次數 | 原因 |
|------|---------|------|
| `班別` | 393 | A/B/C 分班，RAG 查詢不需要 |
| `性別` | 378 | 體育課限男/女，非課程推薦主要維度 |
| `學號` | 136 | 單/雙號分班，與班別同性質 |

---

## 三、指定課程欄位詳細說明

### 動詞類型與語意

| 動詞 | 涉及課號數 | 輸出欄位 | 語意 |
|------|----------|---------|------|
| `先修` | 149 個課號，139 門課有此需求 | `prereq_codes` | 「必須先修 A 才能選這門課」|
| `同修` | 15 個課號，16 門課有此需求 | `coreq_codes` | 「必須同一學期也選 A」（通常是實驗課配講授課）|
| `擋修` | 55 個課號，48 門課有此限制 | `conflict_codes` | 「已修過 A 就不能再選」（學分相似/課程衝突）|
| `禁修` | 19 個課號，18 門課有此限制 | `forbidden_codes` | 「禁止同時選」（同一課不同班別互斥）|

### 範例

```
AP2007 應用數學       → prereq_codes: ['MA1003', 'MA1004']
CI3067 計算機視覺     → coreq_codes:  ['CI3066']           # 需同修實驗
BA7127 AI深度學習理論  → conflict_codes: ['BA7126']          # 已修進階版就擋修
CC0216 通識課程 B     → forbidden_codes: ['CC0205']         # 兩班互選一
```

---

## 四、系所欄位的特殊前綴

```
輔系-資訊工程學系      → open_to_minor = True（且記錄輔系系所）
雙主修-電機工程學系    → open_to_double_major = True
學分學程-量子技術學程  → open_to_credit_prog = True
第二專長-教育學程      → open_to_2nd_spec = True
非企業管理學系         → dept_exclude: ['企業管理學系']
資訊工程學系           → dept_include: ['資訊工程學系']
```

---

## 五、如何整合進知識圖譜

### 5.1 節點屬性擴充（Course 節點）

將 course_eligibility.json 的欄位附加到既有 Course 節點：

```python
# 腳本：scripts/graph/enrich_graph_eligibility.py
for record in eligibility_data:
    node_id = f"Course_{record['course_code']}"
    if G.has_node(node_id):
        G.nodes[node_id].update({
            'eligible_years':       record['eligible_years'],
            'program_types':        record['program_types'],
            'dept_include':         record['dept_include'],
            'dept_exclude':         record['dept_exclude'],
            'college_include':      record['college_include'],
            'college_exclude':      record['college_exclude'],
            'open_to_minor':        record['open_to_minor'],
            'open_to_double_major': record['open_to_double_major'],
            'open_to_credit_prog':  record['open_to_credit_prog'],
            'open_to_2nd_spec':     record['open_to_2nd_spec'],
            'open_to_cross_school': record['open_to_cross_school'],
        })
```

### 5.2 新增邊（關係擴充）

| 欄位 | 圖中邊類型 | 方向 | 屬性 |
|------|----------|------|------|
| `prereq_codes` | `PREREQUISITE_OF` | A → B（A 是 B 的先修） | `source: 'registration_rule'` |
| `coreq_codes` | `COREQUISITE_OF` | 雙向 | `source: 'registration_rule'` |
| `conflict_codes` | `CONFLICTS_WITH` | 雙向 | `source: 'registration_rule'` |
| `forbidden_codes` | `MUTUALLY_EXCLUSIVE` | 雙向 | `source: 'registration_rule'` |

```python
# 新增先修邊
for record in eligibility_data:
    course_node = f"Course_{record['course_code']}"
    for prereq_code in record['prereq_codes']:
        prereq_node = f"Course_{prereq_code}"
        if G.has_node(prereq_node) and G.has_node(course_node):
            G.add_edge(prereq_node, course_node,
                       type='PREREQUISITE_OF',
                       source='registration_rule')

# 新增擋修邊（雙向）
for record in eligibility_data:
    course_node = f"Course_{record['course_code']}"
    for conflict_code in record['conflict_codes']:
        conflict_node = f"Course_{conflict_code}"
        if G.has_node(conflict_node) and G.has_node(course_node):
            G.add_edge(course_node, conflict_node,
                       type='CONFLICTS_WITH', source='registration_rule')
            G.add_edge(conflict_node, course_node,
                       type='CONFLICTS_WITH', source='registration_rule')
```

---

## 六、對問答系統的效益

### 因為 `eligible_years` + `program_types`（節點屬性）
- 「大二可以修的資工系選修有哪些？」→ 過濾 `eligible_years ∋ 2`
- 「碩士班可以選的通識課有哪些？」→ 過濾 `program_types ∋ master`
- 「輔系學生可以修電機系的哪些課？」→ 過濾 `open_to_minor=True AND dept='EE'`

### 因為 `PREREQUISITE_OF`（先修邊）⭐⭐⭐
- 「修深度學習之前要先修什麼？」→ 沿邊回溯前驅節點
- 「我已經修了線性代數，下一步能修什麼？」→ 沿邊找後繼節點
- 「幫我規劃從零到修完機器學習的路徑」→ 最短路徑 / 拓撲排序

### 因為 `CONFLICTS_WITH`（擋修邊）⭐⭐
- 「我已經修了 BA7126，BA7127 我還能選嗎？」→ 查 `CONFLICTS_WITH` 邊
- 選課規劃時自動排除已修課程的擋修課

### 因為 `COREQUISITE_OF`（同修邊）⭐
- 「CI3067 計算機視覺是不是有對應的實驗課？」→ 查 `COREQUISITE_OF` 邊
- 推薦時附帶提示：「這門課需要同時選 CI3066 實驗課」

### 因為 `MUTUALLY_EXCLUSIVE`（禁修邊）
- 選課規劃時防止使用者選到互斥的兩門課

---

## 七、欄位完整統計（114 學年）

| 欄位/旗標 | 有此條件的課號數 |
|----------|--------------|
| eligible_years（有年級限制） | 535 |
| program_types（有學制限制） | 1,019 |
| dept_include（指定可修系所） | 2,532 |
| dept_exclude（排除系所） | 41 |
| college_include（指定可修學院） | 363 |
| college_exclude（排除學院） | 56 |
| open_to_minor（輔系可修） | 272 |
| open_to_double_major（雙主修可修） | 341 |
| open_to_credit_prog（學分學程可修） | 167 |
| open_to_2nd_spec（第二專長可修） | — |
| open_to_cross_school（申請校學士） | 22 |
| prereq_codes（先修要求） | 139 |
| coreq_codes（同修要求） | 16 |
| conflict_codes（擋修限制） | 48 |
| forbidden_codes（禁修限制） | 18 |
| 無分發條件（全開放） | 591 |
