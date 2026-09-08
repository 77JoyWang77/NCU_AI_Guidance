# Fig 3 — 多信號 RRF 課程搜尋演算法

## 論文定位

本系統最核心的技術貢獻。`tool_search_courses` 整合了知識圖譜精確查詢、
向量語意搜尋（兩路）、Query Expansion、課名精確匹配、修課資格驗證六種異質信號，
以 Reciprocal Rank Fusion（RRF）統一排序。
比純向量搜尋更精確，比純圖查詢覆蓋更廣，同時解決課程推薦中的修課資格過濾問題。

---

## 圖表類型建議

垂直流程圖（Top-Down Flowchart），分 8 個 Layer。
重點標示：Graph-First 分支（右側快速路徑）vs 一般查詢路徑（左側主路徑），
以及 6 個 Signal 在哪個 Layer 匯入 RRF Pool。
建議用不同顏色區分：圖查詢信號（藍）、向量搜尋信號（橙）、精確匹配信號（綠）。

---

## 函式簽名

```python
def tool_search_courses(
    query: str,                        # 必填：搜尋關鍵詞或自然語言描述
    dept: str = None,                  # 限縮開課系所
    college: str = None,               # 限縮開課學院
    student_college: str = None,       # 學生所屬學院（修課資格過濾）
    course_type: str = None,           # "必修" or "選修"
    tech: str = None,                  # 技術/工具名稱（觸發 Graph-First）
    topic_tag: str = None,             # 通識課主題標籤
    is_grad: bool = False,             # True = 研究所課程
    exclude_grad_only: bool = True,    # True = 排除限研究所的課
    n: int = 16,                       # 回傳筆數
) -> list[dict]
```

---

## 完整 8 Layer 流程

### [L0] 別名解析

```
dept / college / student_college
    │
    ▼ dept_aliases.json 查表
正規系所名稱（如「資電學院」→「資訊電機學院」）
```

**意義**：使用者常用縮寫輸入，解析確保後續查詢用正確的系所名稱匹配

---

### [Branch] Graph-First 快速路徑（tech 參數存在時）

```
tech 參數 ≠ None
    │
    ▼
graph_service.search_courses_by_tech(tech)
    ├─ 精確節點查找：tech::xxx / concept::xxx / field::xxx
    ├─ 大小寫不敏感匹配（node.name.lower() == tech.lower()）
    └─ 語義補充：Qdrant ncu_graph_nodes 向量搜索（別名/縮寫）
    
    ─[反向 TEACHES/COVERS/COVERS_FIELD/DEVELOPS 邊]─►課程節點
    
    ▼
依 is_grad 過濾等級（ugrad/grad）
    ▼
_enrich_courses_metadata()（補齊語意欄位）
    ▼
直接 return（不進入後續 Layer）
```

**為何設計此分支**：技術查詢（如「Python 的課」）在圖中有精確的 `tech::python` 節點，
圖遍歷的精確度遠優於向量搜尋，應優先走圖。

---

### [L1] Query Expansion：雙軌圖語意擴展

```
Qdrant ncu_graph_nodes 向量搜尋（top_k=25）
    │
    ├── Track A：Concept / Technology / Field / Competency 節點
    │       取節點名稱補充到 expanded_query（最多 5 個詞）
    │       例：「機器學習」→ expanded_query = "機器學習 深度學習 神經網路 PyTorch 特徵工程"
    │
    └── Track B：Course 節點，score ≥ 0.65
            記為 direct_course_items（list of (course_id, score)）
            → Signal C 的種子（後續 L6 使用）
```

**設計意義**：
- Track A 解決了「搜尋詞與課程描述詞彙不一致」問題（e.g., 搜尋「深度學習」但課程寫「神經網路」）
- Track B 讓語意高度相關的課程（圖節點 score ≥ 0.65）在後續獲得額外 boost
- 篩除與 query 相同的詞避免重複：`seen_term_names = {query.lower()}`

---

### [L2] Qdrant Filter 建構

根據使用者傳入的過濾條件，組裝 Qdrant must 條件：

```python
conditions = []

# 開課系所/學院過濾
if dept:    conditions.append({"dept":    {"$eq": dept}})
if college: conditions.append({"college": {"$eq": college}})

# 課程類型
if course_type: conditions.append({"type": {"$eq": course_type}})

# 年級層級
if exclude_grad_only and not is_grad:
    conditions.append({"is_grad_only": {"$eq": False}})

# 通識課主題
if topic_tag: conditions.append({"topic_tags": {"$contains": topic_tag}})
```

**student_college 修課資格過濾（OR 條件組合）**：
```python
student_college_or = [
    {"is_open_to_all_undergrad": {"$eq": True}},           # 全校開放
    {"college_include": {"$contains": student_college}},    # 學院直接開放
    *[{"dept_include": {"$contains": d}} for d in depts_in_college]  # 系所展開
]
conditions.append({"$or": student_college_or})
```

---

### [L3] 三路向量搜尋

#### Signal A：擴展查詢 + filters

```
retriever.search_courses(expanded_query, filters, n_results=n*3)
```

在 Qdrant ncu_courses_ug（或 grad）中進行 Hybrid Search：
- Dense（text-embedding-3-large, 3072d）+ BM25 → Qdrant 內層 RRF

#### Signal B：原始查詢 + filters（僅在 expanded_query ≠ query 時啟動）

```
retriever.search_courses(original_query, filters, n_results=n*3)
```

**設計意義**：擴展詞可能稀釋原始語意，Signal B 確保原始意圖不被淹沒。

#### Signal A_excl：開放但有排除限制的課程（student_college 指定時）

```
Filter: is_open_with_exclusions = True
must_not: dept_exclude ∋ any(depts) OR college_exclude ∋ student_college
```

**背景**：部分課程對全體學士開放但排除特定系所/學院（`is_open_with_exclusions=True`），
這類課程的 `dept_include=[]` 和 `college_include=[]`，
無法被 L2 的正向 OR filter 命中，需獨立搜尋再用 must_not 驗證。

**距離門檻**：`distance ≤ 0.65`（避免語意無關的課程混入 pool，尤其在 pool 較小時）

---

### [L4] 基礎 RRF 融合

```
RRF_K = 60

for Signal in [A, B, A_excl]:
    for rank, result in enumerate(Signal, start=1):
        code = result.course_code
        code_scores[code] += 1 / (RRF_K + rank)
        code_meta.setdefault(code, result)
```

**RRF 公式**：`score(doc) = Σᵢ 1/(60 + rankᵢ)`

三個 Signal 的結果合併到 `code_scores` dict，同一課程的分數累加。

---

### [L5] Signal N：課程名稱完全匹配 Boost

```
exact_name_hits = retriever.get_courses_by_name(query)
NAME_EXACT_BOOST = 0.15   # 遠高於 Signal A/B 最大值 ≈ 1/61 ≈ 0.016

for result in exact_name_hits:
    通過 student_college 正向/負向驗證？
        YES → code_scores[code] += 0.15
              exact_match_codes.add(code)    ← 記錄置頂集合
```

**student_college 驗證邏輯**（Signal N/C 補入前必做）：

正向條件（任一成立即通過）：
- `is_open_to_all_undergrad = True`
- `student_college ∈ college_include`
- `any(depts_in_college) ∈ dept_include`
- `is_open_with_exclusions = True`

負向排除（任一成立即拒絕）：
- `student_college ∈ college_exclude`
- `student_college ∈ dept_exclude`
- `any(depts_in_college) ∈ dept_exclude`

### [L5'] Signal N2：課名包含 query Boost

```
PARTIAL_BOOST = 0.05

for code in code_meta:
    if code not in exact_match_codes and query in name_zh:
        通過 dept/college 條件？
            YES → code_scores[code] += 0.05
```

---

### [L6] Signal C：Graph Score Boost（圖先驗知識注入）

```
for (course_code, sig_score) in direct_course_items:  # 來自 L1 Track B
    
    跳過：graph node 名稱含「[已停開]」的課程
    
    boost = sig_score / (RRF_K + 1)
    
    if course_code in code_scores:
        code_scores[course_code] += boost        ← 已在 pool 中，直接加分
    else:
        hits = retriever.get_courses_by_code(course_code)
        通過 student_college 驗證？
            YES → code_scores[course_code] = boost
                  code_meta[course_code] = hits[0]  ← 補入 pool
```

**設計意義**：圖中語意高度相似的課程（score ≥ 0.65）即使未在向量搜尋中排前面，
也能透過此 boost 提升排名，彌補向量搜尋的盲區。

---

### [L7] 最終排序與輸出

```
ranked_all = sorted(code_scores, key=score, reverse=True)

# exact_match 課程置頂（不佔 n 名額）
exact_ranked   = [c for c in ranked_all if c in exact_match_codes]

# 語意結果：排除 exact_match + 排除 SC 前綴（服務學習誤標全開放問題）
semantic_ranked = [c for c in ranked_all 
                   if c not in exact_match_codes and not c.startswith("SC")][:n]

results = [code_meta[c] for c in exact_ranked + semantic_ranked]
return _fmt_courses(results, exact_match_codes)
```

---

## 6 Signal 特性完整對照

| Signal | 來源 | 觸發條件 | 最大 Boost | 設計目的 |
|---|---|---|---|---|
| **A** | Qdrant，擴展查詢 | 一般查詢 | ~0.016 | 語意廣覆蓋（含擴展詞） |
| **B** | Qdrant，原始查詢 | expanded≠query | ~0.016 | 防擴展詞稀釋原意 |
| **A_excl** | Qdrant，must_not | student_college 指定 | ~0.016 | 補回「全開但有排除」型 |
| **N** | 課名精確匹配 | 任何查詢 | **+0.150** | 同名課程置頂（最高優先） |
| **N2** | 課名包含查詢 | 任何查詢 | +0.050 | 部分名稱課程提升 |
| **C** | 圖節點 score | L1 Track B 有結果 | sig_score/61 | 圖結構語意強化 |

**Signal N boost 量 0.15 的設計理由**：
RRF 單 Signal 最大分數 ≈ 1/(60+1) ≈ 0.016，
0.15 相當於三個 Signal 各排第 1 名的分數總和，確保完全同名的課程必然置頂。

---

## 互補性分析（論文 Discussion 可引用）

| 場景 | 主要信號 | 補充信號 |
|---|---|---|
| 搜尋「Python 的課」（tech 指定） | Graph-First | — |
| 搜尋「機器學習」（一般查詢） | Signal A+B | Signal C（圖語意）|
| 搜尋「演算法」（課名） | Signal N（置頂）| Signal A（其他相關）|
| 資電學院學生搜尋全校課程 | Signal A + A_excl | Signal N/C 驗證資格 |
| 課名部分匹配「程式設計-Python」 | Signal N2（+0.05）| Signal A（語意）|

---

## 結果格式

每筆結果包含：

```python
{
  "course_code":   "CS4001",
  "name_zh":       "機器學習",
  "name_en":       "Machine Learning",
  "dept":          "資訊工程學系",
  "college":       "資訊電機學院",
  "credits":       3,
  "type":          "選修",
  "teacher":       "張三",
  "when":          "大三上（資訊工程學系）",
  "concepts":      "梯度下降, 支持向量機, 神經網路",
  "technologies":  "Python, scikit-learn, TensorFlow",
  "domain_tags":   "機器學習, 資料科學",
  "summary":       "核心概念：梯度下降, SVM\n技術工具：Python, scikit-learn",
  "distance":      0.1234,
  "exact_match":   True   ← 只有 Signal N 命中的課才有此欄
}
```
