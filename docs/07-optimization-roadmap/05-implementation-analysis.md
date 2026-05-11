# 實作分析：v5 測試後修正方案

> 撰寫日期：2026-05-11  
> 狀態：**分析完成，等待確認後再實作**

---

## 一、已完成的小修正（本文件產出前已做）

以下修正工作量極小，已在分析過程中順手完成，供確認：

| 項目 | 狀態 | 說明 |
|------|------|------|
| **B2** `dept_aliases.json` 加 `"客家語文學系"` | ✅ 已完成 | 一行 alias |
| **B4/P1** system prompt 加「兩系比較必查兩個系」 | ✅ 已完成 | 加在「工具選用指引→系所課程查詢」之後 |
| **B5** system prompt 加「found=False 禁止補全系所名稱」 | ✅ 已完成 | 加在「回答規則」第 4 條 |
| **G1** system prompt 強化通識課警告 | ✅ 已完成 | elective 包含跨開課警告 |
| **O4/O8** system prompt 加 domain_profile 引用說明 | ✅ 已完成 | 加在「工具回傳欄位說明」區塊 |
| **E1** system prompt 改寫 PPR 說明（多種子推薦） | ✅ 已完成 | 範例 12 也一併更新 |

---

## 二、前端分班課程 per-section syllabus（F1 → F2 → F3）

### 資料確認（F1）

**已確認：原始資料有差異**

從 `data/raw/courses/114_1/理學院_數學系.json` 確認：

| 課號班別 | 教師 | 課程目標（前 60 字） | 教科書 |
|---------|------|---------------------|--------|
| MA1001-A | 許正雄 | "學習微分與積分的基本知識..." | G. B. Thomas, Calculus, 14th Ed |
| MA1001-B | 俞韋亘 | 學習微分與積分的基本知識... | 湯馬士 微積分 14版 |
| MA1001-C | 姚美琳 | 同A | Thomas' Calculus 14/e |
| MA1001-E | 陳宣毅 | **"This course introduces various basic mathematical techniques..."** | Thomas' Calculus, 14th Edition |

MA1001-E 的課程目標與其他班完全不同（英文 vs 中文，不同描述角度）。

**統計（453 個有分班課程）：**
- 課程目標不同的：227 組（50%）
- 授課內容不同的：252 組（55%）  
- 教科書不同的：249 組（54%）
- **任一欄位有差異的：279 組（62%）**

結論：**有必要做 per-section 顯示**，62% 的分班課程至少有一個欄位不同。

---

### 修正方案

#### 方案 A（建議）：build_course_index.py 加 per-section syllabus，前端 accordion

**步驟 1：`scripts/rag/build_course_index.py`（已改）**  
在 sections 陣列的每個 section 加入 `course_objective / course_content / textbook` 三個欄位（從 `c.get('課程綱要', {})` 取出）。  
> 已修改，尚未重建 index（等使用者確認後執行）。

**步驟 2：重建 `data/processed/course_index.json`**  
執行 `python3 scripts/rag/build_course_index.py`。  
預計耗時 < 1 分鐘。  
> ⚠️ 會覆寫現有 index，但此動作可重做，無破壞性。

**步驟 3：後端 `backend/app/routes/chat.py`**  
目前後端 `/chat/course_detail` 直接 pass `entry.get("sections", [])` 回前端，不需額外改動。重建 index 後，sections 就自動帶上 syllabus 欄位。

**步驟 4：前端 `CourseDetailModal.tsx`**  
在現有 `hasMultiSections` 條件下，新增判斷：
```typescript
// 判斷各班 syllabus 是否有差異
const hasDifferentSyllabus = hasMultiSections && detail.sections.some(
  s => (s.course_objective && s.course_objective !== detail.course_objective) ||
       (s.course_content  && s.course_content  !== detail.course_content)  ||
       (s.course_textbook && s.course_textbook !== detail.textbook)
);
```

- **若 `hasDifferentSyllabus === true`**：顯示 per-section accordion  
  - 每個班一個摺疊區塊，標題：`第 A 班（許正雄）`  
  - 展開後顯示：課程目標 / 授課內容 / 教科書  
  - eligibility_text 仍放在標題旁
- **若 `hasDifferentSyllabus === false`**：維持現有顯示（共用一個區塊）

**SectionInfo interface 需擴充：**
```typescript
interface SectionInfo {
  section:          string;
  teacher:          string;
  dept:             string;
  college:          string;
  type:             string;
  eligibility_text: string;
  course_objective?: string;  // 新增（可選）
  course_content?:  string;   // 新增（可選）
  textbook?:        string;   // 新增（可選）
}
```

#### 方案 B：不重建 index，改直接讀 raw data on-demand

當 `/chat/course_detail` 被呼叫時，即時從 `data/raw/courses/114_1/*.json` 撈 per-section syllabus。  
**缺點**：需要 file I/O on request；raw data 路徑有學期依賴（114_1 要更換時得改）。**不建議**。

---

## 三、B3 中文學系畢業規定資料污染調查

### 調查結果

**當前資料狀態：已是乾淨的**

| 資料來源 | 內容 |
|---------|------|
| `data/processed/requirements_notes.json['中國文學系']` | 368字，僅含共同必修/系訂必修/雙主修，無地科字眼 |
| `data/processed/schedule_draft/文學院/中國文學系.json` | certifications: []，graduation_rules 乾淨 |

**污染的可能根因**（Q48 時的行為，可能現在已改善）：

- **根因一：alias 解析未套用於 `tool_get_graduation_requirements`**  
  LLM 可能呼叫 `get_graduation_requirements("中文學系")`（縮寫），而 `tool_get_graduation_requirements` 和底層 `get_graduation_rules` 都沒有套用 `dept_aliases`，導致 `"中文學系" in "中國文學系"` 為 False（中文字串子集判斷失敗），資料取不到。
  
- **根因二：fallback 匹配太鬆散**  
  `tool_get_graduation_requirements` 第二輪 fallback：  
  ```python
  if any(c in dept for c in dept_name if len(c.encode()) > 1):
  ```  
  邏輯是「dept_name 裡任意一個中文字元出現在 dept 裡就算匹配」。  
  「中文學系」的字元 `中`, `文`, `學`, `系` 幾乎每個 dept 都有，所以第一個出現的 dept 就會被當成答案 → 回傳了錯誤系所的資料。

- **根因三：取到錯誤資料後，LLM 讀到不屬於中文系的 certifications（地球科學資訊學分學程等），當成中文系規定輸出**

### 修正方向

#### 方案 A（建議）：`tool_get_graduation_requirements` 先套用 alias 正規化

```python
from app.services.graph_service import _normalize_dept_name  # 現有 alias 正規化函式

def tool_get_graduation_requirements(dept_name: str) -> dict:
    normalized = _normalize_dept_name(dept_name) or dept_name
    rules = graph_service.get_graduation_rules(normalized)
    ...
```

同時移除過鬆的 fallback（單字元匹配），改為嚴格匹配或包含子字串匹配：
```python
# 舊的過鬆 fallback（移除）：
if any(c in dept for c in dept_name if len(c.encode()) > 1):

# 改為：只有 dept_name 是 dept 的子字串（或反向）才算匹配
if dept_name in dept or dept in dept_name:
```

#### 方案 B：在 `get_graduation_rules` 中加入 alias 解析

修改 `graph_service.get_graduation_rules`：
```python
def get_graduation_rules(dept_name: str) -> dict:
    # 先 normalize
    normalized = _normalize_dept_name(dept_name) or dept_name
    for college_dir in SCHEDULE_DIR.iterdir():
        for fp in college_dir.glob("*.json"):
            data = json.loads(fp.read_text(...))
            if normalized in data.get("name", "") or data.get("name", "") == normalized:
                return { ... }
```

**建議：方案 A**（在工具層統一處理，`graph_service` 不需關心業務邏輯）。

---

## 四、P2 截斷透明度：search_courses 加 total_found 欄位

### 現狀

`tool_search_courses` 回傳 `list[dict]`（最多 `n=8` 筆），無法告知 LLM 總命中數。  
`tool_get_dept_courses` 回傳 `{"dept_name": ..., "courses": [...]}` 也沒有 total_found。

### 兩個修正子項目

**P2-a：`tool_get_dept_courses` 加 total_found**（較簡單）

```python
return {
    "dept_name":   dept_name,
    "course_type": course_type,
    "total_found": len(courses_before_truncation),   # dedup 後總數
    "courses":     courses,                           # 回傳全部（通常已是全量）
}
```
> 注意：`get_dept_courses` 目前回傳全量課程（無截斷），但 LLM 自行選 top-N 輸出。  
> 加 `total_found` 後，system prompt 可提示 LLM：如果 `len(courses) > 15`，說明「共有 X 門課，以下列出...」。

**P2-b：`tool_search_courses` 改回傳 dict（中等改動）**

目前 `_collect_course_pool` 中依賴 `search_courses` 回傳 `list`，改為 `dict` 需同時修改：
1. `tools.py` `tool_search_courses` 回傳格式
2. `llm_service.py` `_collect_course_pool` 中解析 search_courses 回傳的邏輯
3. `TOOL_MAP` 中對應的處理

**回傳格式改為：**
```python
{
    "courses":       [...n筆...],
    "total_found":   len_before_rrf_cutoff,
    "query_info": {
        "expanded_query": expanded_query,
        "concept_nodes_used": [concept_node_names],
    }
}
```

**System prompt 補充：**
```
`search_courses` 回傳的 `total_found` 是符合條件的總命中數（向量搜尋全集）。
若 total_found > len(courses)，在回答中說明「共找到 X 門相關課程，以下列出最相關的前 N 門」。
若 total_found == len(courses)，無需特別說明截斷。
```

#### 建議優先序：P2-a 先做（影響面小），P2-b 確認架構後再做

---

## 五、search_courses 重設計（D）

### 現狀問題

```
query → _search_concept_nodes(top_k=3) → 取3個 concept 名稱 → 附加到查詢
     → expanded_query + original_query → Qdrant RRF 融合 → top_n
```

問題：
- 只取 3 個 concept，對 domain_tags 類查詢（Q32「資料科學相關課程」）效果差
- 3 個 concept 固定，不管分數高低都取，低分 concept 反而稀釋查詢語意
- Qdrant payload 中有 `domain_tags_rich`（帶 relevance 的領域標籤），但 search 時未利用

### 三種方向

#### D1：Dynamic top_k（最小改動，建議先做）

**改動：** `_search_concept_nodes(query, top_k=3)` → 動態決定：

```python
concept_results = _search_concept_nodes_with_scores(query, top_k=6)
# 根據分數決定取幾個
threshold_high = 0.82
threshold_low  = 0.65
filtered = [r for r in concept_results if r["score"] >= threshold_low][:5]
# 若最高分 < 0.65，不做擴展（低信心，擴展反而稀釋）
if not filtered or concept_results[0]["score"] < threshold_low:
    expanded_query = query
else:
    names = [g["nodes"][r["id"]].get("name","") for r in filtered]
    extra_terms = [n for n in names if n.lower() not in query.lower()]
    expanded_query = (query + " " + " ".join(extra_terms)).strip()
```

- **優點**：程式改動 < 20 行，不需重建 index
- **缺點**：仍是 Qdrant 向量搜尋，對精確領域 keyword 效果有限

> 需先確認 `_search_concept_nodes` 目前是否有回傳分數（若有 → 直接改 threshold；若無 → 需改函式 signature）

#### D2：Graph Concept Direct Path（中等改動）

在現有 RRF 之前，新增第三路 Signal C：

```python
# Signal C：透過 Concept 節點反查課程（圖直接路徑）
concept_hits = []
for concept_id in concept_node_ids:
    concept_score = concept_scores.get(concept_id, 0.0)
    for src_id, rel in g["in"].get(concept_id, []):
        if rel == "COVERS" and g["nodes"].get(src_id, {}).get("node_type") == "Course":
            concept_hits.append({
                "course_id": src_id,
                "matched_concept": g["nodes"][concept_id].get("name", ""),
                "score": concept_score,
            })
# 去重，取分數最高的
```

然後把 concept_hits 加入 RRF 融合：
```
Signal A（expanded query Qdrant）+ Signal B（original query Qdrant）+ Signal C（graph concept match）→ RRF → top_n
```

- **優點**：精確命中，`matched_via` 可解釋為何出現；特別適合「哪些課教 OO」
- **缺點**：需確認 COVERS 邊的覆蓋率（不是所有課程都有 Concept 邊）；需要修改 `_collect_course_pool` 解析

> 先評估：有多少 Course 節點有至少一條 COVERS 邊？

#### D3：Hybrid BM25（大改動，需重建 Qdrant index）

在 Qdrant collection 加入 sparse vector，做 dense + sparse 混合搜尋。

| 項目 | 評估 |
|------|------|
| 工作量 | ~8 小時（重建 index + 測試） |
| 依賴 | fastembed 或自建 tokenizer；qdrant-client ≥ 1.9 |
| 效果 | keyword 精確度大幅提升（「資料科學」不再被稀釋） |
| 風險 | index 重建需停服；sparse tokenizer 對中文效果需驗證 |

**不建議目前做**，等 D1/D2 驗證後再決定。

### 建議執行順序：D1 → 驗證效果 → 視情況做 D2

---

## 六、B3 調查補充：COVERS 邊覆蓋率（D2 可行性前置）

> 此調查結果供 D2 方案決策參考

需執行：
```python
g = _g()
courses_with_covers = sum(
    1 for nid, n in g["nodes"].items()
    if n.get("node_type") == "Course"
    and any(rel == "COVERS" for _, rel in g["out"].get(nid, []))
)
total_courses = sum(1 for n in g["nodes"].values() if n.get("node_type") == "Course")
print(f"有 COVERS 邊的課程：{courses_with_covers}/{total_courses} ({courses_with_covers*100//total_courses}%)")
```

> ⚠️ 若覆蓋率 < 30%，D2 效果不佳，應先做 D1。

---

## 七、PPR 工具層改進（E2）

### 現狀

`tool_ppr_explore` 在找不到種子節點時回傳：`"找不到以「{seed}」為起點的相關節點（請確認概念名稱是否正確）。"`

LLM 看到此訊息後通常不知道怎麼 retry（很少主動嘗試英文或多種子）。

### 修正方案

**E2-a：seed 信心提示（建議）**

在 `tool_ppr_explore` 中，於回傳之前加入種子質量說明：

```python
# 在 graph_service.ppr_explore 呼叫前
seed_count = len([s for s in seed_list if graph_service.find_node_by_name(s)])
if seed_count == 0:
    return f"找不到以「{seed}」為起點的節點。建議：(1) 嘗試英文（如 'machine learning'）；(2) 改用更短的核心詞；(3) 改用 search_courses 向量搜尋。"
elif seed_count < len(seed_list):
    missing = [s for s in seed_list if not graph_service.find_node_by_name(s)]
    result_str = ...  # 正常繼續
    return result_str + f"\n\n⚠️ 注意：種子「{', '.join(missing)}」在圖中未找到節點，已忽略；結果僅基於其他種子。"
```

**E2-b：回傳加 seed_resolved 欄位**

在回傳字串最前面加：`已解析種子：{已找到的種子名稱}`，讓 LLM 知道哪些種子有效。

**建議做 E2-a**（對 LLM 引導更有幫助）。

---

## 八、摘要：等待確認的項目

| 項目 | 說明 | 影響面 | 確認後動作 |
|------|------|--------|-----------|
| **F1→F3**（前端 accordion） | `build_course_index.py` 已改，待重建 index + 改前端 | 中 | 執行 rebuild script → 改 CourseDetailModal.tsx |
| **B3 修正** | `tool_get_graduation_requirements` 加 alias 正規化；移除過鬆 fallback | 低 | 改 tools.py 5行 |
| **P2-a**（get_dept_courses total_found） | 加一個 metadata 欄位 | 低 | 改 tools.py ~3行 + system prompt |
| **P2-b**（search_courses 改回傳 dict） | 需同步改 tools.py + llm_service.py | 中 | 改 2 個函式 |
| **D1**（dynamic concept expansion） | 先確認 _search_concept_nodes 有沒有回傳分數 | 低 | 改 tools.py ~20行 |
| **D2**（graph concept direct path） | 先確認 COVERS 邊覆蓋率 | 中 | 改 tools.py ~40行 |
| **E2-a**（PPR seed confidence hint） | 工具回傳加提示 | 低 | 改 tools.py ~15行 |

---

## 附：已完成的 system prompt 修改摘要

以下是本次已插入 `llm_service.py SYSTEM_PROMPT` 的內容：

1. **B5 幻覺防範**（回答規則第 4 條）  
   `found=False` 時只能回傳 fallback_candidates，不得補全系所名稱

2. **G1 通識課警告**（Filter 使用原則）  
   `get_dept_courses(通識教育中心, elective)` 包含跨開課，主題查詢改用 search_courses

3. **O8/O4 domain_profile**（工具回傳欄位說明）  
   說明 `domain_profile` 的用途，介紹系所時應主動引用，「哪些領域為主」優先 get_dept_info

4. **B4/P1 兩系比較**（工具選用指引）  
   必須並行呼叫兩個系的 get_dept_info；domain_profile 已夠用不需 get_dept_courses(all)

5. **E1 PPR 說明改寫**（工具選用指引）  
   多種子推薦、overview 只在明確要全貌時使用、範例 12 更新

---

*建立日期：2026-05-11*
