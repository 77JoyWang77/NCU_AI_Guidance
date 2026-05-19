# tool_search_courses 完整邏輯與優化分析

> 最後更新：2026-05-15

---

## 1. 函式概述

`tool_search_courses` 是 RAG 系統中最核心的搜尋工具，整合 Qdrant 向量搜尋、BM25 全文搜尋與知識圖譜三個資料源，透過 RRF（Reciprocal Rank Fusion）多訊號融合回傳最相關課程清單。

---

## 2. 輸入參數

| 參數 | 型別 | 說明 | 預設 |
|------|------|------|------|
| `query` | str | 搜尋關鍵詞（必填） | — |
| `dept` | str | 限縮開課系所，如「資訊工程學系」 | None |
| `college` | str | 限縮開課學院，如「資訊電機學院」 | None |
| `student_college` | str | 學生所屬學院，只回傳可修課程 | None |
| `course_type` | str | 必修/選修 | None |
| `year` | int | 開課年級（1-4） | None |
| `sem` | int | 學期（1=上、2=下） | None |
| `tech` | str | 技術/工具名稱，走 graph_tech 快速路徑 | None |
| `is_grad` | bool | True = 搜研究所課程 | False |
| `exclude_grad_only` | bool | True = 排除限研究所才能修的課 | True |
| `n` | int | 最終回傳筆數 | 16 |

所有字串參數在函式開頭透過 `_resolve_name()` 做別名正規化（如「資電學院」→「資訊電機學院」）。

---

## 3. 執行流程

### Layer 0：tech 快速路徑（Graph-first）
若 `tech` 有值，走圖的技術節點直接查詢：
```
graph_service.search_courses_by_tech(tech)
    → 依 level 篩選（ugrad / grad）
    → _enrich_courses_metadata()
    → 直接回傳，不執行後續 Layer
```
適合「用 PyTorch 的課」這類精確技術查詢，比向量搜尋更精確。

---

### Layer 1：Query Expansion（知識圖譜雙軌擴展）

呼叫 `graph_service._search_concept_nodes_with_scores(query, top_k=25)` 取得相關節點與語意相似度分數。

**Track A（術語擴展）**：
- 節點類型為 `Concept / Field / Technology / Competency`
- score ≥ 0.65 才收入
- 最多取 5 個唯一名詞，附加在 query 後形成 `expanded_query`
- 目的：補捉同義詞、近義術語（如「常微分方程」→ 擴展到「偏微分方程」）

**Track B（課程直達）**：
- 節點類型為 `Course`，score ≥ 0.65
- 收集為 `direct_course_items = [(nid, score), ...]`
- 後在 Layer 3 注入為 Signal C

---

### Layer 2：Qdrant Filters 組裝

依傳入參數逐條組裝，以 `$and` 串接：

| 條件 | Qdrant 過濾欄位 |
|------|---------------|
| `dept` | `dept == X` |
| `college` | `college == X` |
| `course_type` | `type == 必修/選修` |
| `year + sem` | `when_semesters contains {year}_{sem}` |
| `exclude_grad_only` | `is_grad_only == False` |
| `student_college` | 見下方說明 |

**student_college 展開邏輯**：
從 `dept_college_map.json` 取出該學院下所有系所，組成 OR 條件：
```
is_open_to_all_undergrad == True
OR college_include contains {student_college}
OR dept_include contains {系所1}
OR dept_include contains {系所2}
...
```
這保障三種開放方式都能命中。

⚠️ **注意**：`is_open_with_exclusions=True` 的課程（開放全體但排除特定系）**不包含在此 OR 中**，需另走 Signal A_excl / B_excl。

---

### Layer 3：四路 Qdrant 搜尋 + RRF 融合

RRF 公式：`score += 1 / (RRF_K + rank)`，其中 `RRF_K = 60`。

| Signal | 查詢詞 | Filter | Pool 大小 | 說明 |
|--------|--------|--------|-----------|------|
| **A** | `expanded_query` | 完整 filters | `n*3` | 主力訊號，擴展後語意搜尋 |
| **B** | `query` | 完整 filters | `n*3` | 保障原始語意不被擴展稀釋 |
| **A_excl** | `expanded_query` | `is_open_with_exclusions=True` + `must_not` | `n*2` | 補回「全體可修但排除特定系」課程 |
| **B_excl** | `query` | 同 A_excl | `n*2` | 確保精確課名（如 CC0328）也能被找到 |

B 只在 `expanded_query != query` 時才執行（避免重複查詢）。

**A_excl / B_excl 的 must_not 條件**：
對 `student_college` 所屬的所有系所，加入 `dept_exclude not contains {系所名}` + `college_exclude not contains {student_college}`，確保被排除學院的學生看不到這些課程。

**excl 距離門檻**：只有 `distance ≤ 0.65` 的 excl 結果才納入 RRF，防止語意不相關課程（如搜尋「機器學習」卻把「探索太空」帶進來，因為 excl pool 只有 9 筆課程）。

---

### Layer 4：Signal N（精確名稱匹配 Boost）

```python
NAME_EXACT_BOOST = 0.15
exact_name_hits = retriever.get_courses_by_name(query, collection=collection)
```

精確比對課程名稱（`name_zh == query`），通過 `student_college` 正/負向驗證後，給予 0.15 固定加分。

對比：A/B 單一訊號最大分數 = `1/(60+1) ≈ 0.016`，Signal N 的 0.15 高出約 **9 倍**，確保名稱完全匹配的課程排在第一位。

---

### Layer 5：Signal C（知識圖譜概念直達 Boost）

對 Layer 1 Track B 收集的 `direct_course_items`：

```python
boost = sig_score / (RRF_K + 1)  # sig_score 為圖語意相似度
```

- 若 course_code 已在 RRF pool：直接疊加 boost
- 若不在：`get_courses_by_code()` 取 payload，驗證 student_college 後注入新節點

`sig_score` 最大 = 1.0，則最大 boost = `1.0 / 61 ≈ 0.016`，與一個完美排第一的 Qdrant Signal 等量——確保圖的優質節點有實質影響力，但不會壓過多路訊號的累積分數。

---

### 最終輸出

```python
ranked_codes = sorted(code_scores, key=score.__getitem__, reverse=True)[:n]
results = [code_meta[c] for c in ranked_codes if c in code_meta]
return _fmt_courses(results, exact_match_codes=exact_match_codes)
```

`_fmt_courses()` 將每筆 Qdrant payload 轉換為標準化 dict，欄位包含：
`course_code, name_zh, name_en, dept, college, credits, type, teacher, when, concepts, technologies, domain_tags, course_domain, topic_tags, summary, distance, exact_match`

---

## 4. 測試結果分析（25 queries，2026-05-15 01:30）

### 4.1 Signal C（圖概念直達）貢獻

| Query | 圖獨有命中數 | 代表課程 |
|-------|------------|---------|
| 資料結構 | 4 | BM1011, EE1003, IP1001, CE1001 |
| 微分方程 | 8 | BM2010, CO2011, PH1031 等跨院 |
| 機器學習 | 5 | ME6109, GA1002, IM1001 等 |
| 深度學習 | 6 | ME5208, ME5301, BA7127 等 |
| 量子力學 | 7 | EE4028, PH6048, CM1002 等 |
| 語言學 | 6 | FR4029, EL3063, NL7074 等 |

**結論**：每個 query 平均帶來 5 筆 Qdrant 找不到的跨院課程，Signal C 價值顯著，應維持。

### 4.2 score ≥ 0.65 threshold 效果

| Query 類型 | ≥0.65 節點數 | 說明 |
|-----------|------------|------|
| 精確概念（機器學習、深度學習） | 18-25 | 全部命中，擴展效果佳 |
| 中等精確（資料結構、量子力學） | 11-25 | 擴展合理 |
| 冷門概念（元宇宙） | 1 | 只有自身，實際上不擴展 |
| 廣泛詞（統計） | 25 | 全部命中，仍聚焦相關概念 |
| 縮寫（GIS） | 1 | 類似元宇宙，擴展無效 |

threshold 0.65 表現良好，不需要更動。

### 4.3 元宇宙 query 分析（稀疏節點典型案例）

- 圖中「元宇宙」相關概念稀少，≥0.65 只有自身（score=1.0）
- A+B 向量搜尋命中天文/太空課程（embedding 空間上「宇宙」語意接近「太空」，屬正常現象）
- Signal C 從「元宇宙」概念節點 BFS 找到「生成式AI & 元宇宙智財權專題」（IE8014）
- **元宇宙** 是 Qdrant 語意搜尋的弱點，Signal C 是關鍵補救機制
- n 增大可讓 LLM 有更多候選，從中找到真正相關課程

### 4.4 已停開課程問題

圖 BFS 不區分是否停開，以下課程出現在 Signal C 結果中：

| 課號 | 課名 | 出現在 query |
|------|------|------------|
| ME5209 | 人工智慧與設計思考 [已停開] | 機器學習 |
| TC5003 | 資料探勘與應用 [已停開] | 機器學習 |
| IE8015 | 生成式AI & 元宇宙智財權專題與案例研究 [已停開] | 元宇宙 |
| EC4081 | 知行合一：AI的應用與實踐 [已停開] | 深度學習 |
| NLA014 | 科技英文 [已停開] | 語言學 |

**修正方式**：在 Signal C 注入迴圈中，檢查 graph 節點名稱是否含 `[已停開]`，是則跳過。

---

## 5. 參數決策

### 5.1 回傳數量 n

| 選項 | 優點 | 缺點 |
|------|------|------|
| n=8（舊 schema 描述） | token 省 | 覆蓋不足，尤其跨院查詢 |
| n=12（舊程式碼預設） | 平衡 | 稍嫌不足 |
| **n=16（建議）** | LLM 候選更豐富，判斷更準確 | 稍多 token |
| n=20 | 最豐富 | 可能稀釋主題，LLM 負擔增加 |

**決定：n=16**。LLM（Claude Sonnet）有充足的判斷能力，token 成本可接受。

### 5.2 Pool 大小

現有 n*3（Signal A/B），n=16 時 pool=48，已足夠（目前 n=12 時 pool=36 即表現良好）。維持 n*3 不變。

### 5.3 extra_terms 上限

維持 `extra_terms[:5]`。原因：
- 對高頻概念：top-8 與 top-5 差異不大（仍是同語意叢）
- 對跨域查詢（如「生物領域的機器學習」）：增加上限無法解決根本問題（graph expansion 無法從一個查詢提取兩個獨立域的概念）
- 對冷門詞：graph 本來就只有 1-2 個 ≥0.65 節點，取更多也沒差

### 5.4 RRF_K = 60

維持不變。60 是 RRF 論文的標準值，適合候選池大小 30-50 的情境。

### 5.5 Signal C threshold（score ≥ 0.65）

維持 0.65。測試顯示 0.65 以下的 Course 節點多為語意模糊的邊緣相關課程，加入會帶來雜訊。

### 5.6 excl distance threshold（≤ 0.65）

維持 0.65。主要作用是防止「探索太空」這類課程因 excl pool 太小（只有 9 筆）而無差別進入機器學習搜尋結果。

---

## 6. 跨域查詢能力評估

**問題**：「生物領域的機器學習」這類複雜跨域查詢

**現有行為**：
1. Graph expansion 從「機器學習」出發，top-25 概念全是 ML 相關詞
2. expanded_query 充滿 ML 術語，Signal A 對「生物」語意稀釋
3. Signal B（原始 query）能保留「生物領域的機器學習」整體語意
4. Qdrant dense embedding 能理解複合語意，可能找到生物資訊學、生醫資料分析等課程

**限制**：BM25 對「生物」不敏感（圖中沒有「生物領域的機器學習」這個概念節點）

**建議做法**：
- 現有 search_courses 對此類查詢有一定能力（Signal B + dense embedding）
- 若使用者不滿意，引導改用 `ppr_explore(seed="機器學習,生物", focus="course")`，多種子 PPR 能更精準捕捉跨域

---

## 7. Signal N（精確名稱匹配）使用方式

**對 LLM 的建議呈現方式**：
- Signal N 確保名稱完全匹配的課程排第一
- `exact_match: true` 欄位讓 LLM 可以明確標注「以下是您詢問的課程：」
- 若 student_college 過濾使該課不符合資格，Signal N 自動跳過（不強制顯示不可修的課）

---

## 8. filter_search 測試發現的問題（2026-05-15，36 cases）

> 測試腳本：`scripts/test_filter_search.py`
> 測試結果：`data/test_results/20260515_192053_filter_search.md`

腳本層面的驗證（must_contain / must_not_contain / min_results）全部通過，但人工審視結果後發現以下四個系統性問題：

---

### Issue 1：exact_match 課程佔滿 n 個回傳名額

**現象**：
- 查詢「統計學」回傳 16 筆，其中 14 筆均為 `★exact`（課名完全等於「統計學」）
- 加上 `student_college` 時，服務學習課程（SC0003/SC0004）也可能以 exact_match 身份出現
- 語意相關但非同名課程（如「統計方法」、「應用統計」）幾乎沒有名額

**根本原因**：
Signal N 對所有同名課程加 0.15 boost，結果擠進 n=16 的前段，把同名課程掃進來後語意搜尋結果名額被壓縮。`_fmt_courses()` 單一 list 無法讓 LLM 分辨哪些是「你要找的」vs「主題相關的」。

**建議修正（方案 A，輸出格式分離）**：
```python
# 回傳格式改為
{
    "exact_matches": [...]   # Signal N 命中的課程，不佔 n 名額
    "results": [...]         # 語意搜尋結果，固定 n 筆
}
```
- `exact_matches`：Signal N 命中且通過所有 filter 驗證的課程（可能 0-N 筆）
- `results`：僅從 A/B/C RRF pool 排名，Signal N 命中的課不進入此 list
- LLM 收到後可明確說「以下是完全符合的課程 / 以下是相關課程」

**API 影響**：`tool_search_courses` 回傳型別從 `list[dict]` 改為 `dict`，LLM prompt 的 tool description 與所有呼叫端均需同步更新。

---

### Issue 2：Signal N 完全不理會 college / dept filter（嚴重 bug）

**現象（測試案例：機器學習 + college=生醫理工學院）**：
```
1  CC0328  機器學習  通識教育中心  中心、處室  ★exact  ?college=中心、處室
2  CEA011  機器學習  電機工程學系  資訊電機學院  ★exact  ?college=資訊電機學院
3  CE6102  機器學習  電機工程學系  資訊電機學院  ★exact
4  TC5001  機器學習（三）  通識教育中心  中心、處室  ★exact
5  ME6109  機器學習  機械工程學系  工學院  ★exact
```
前 5 名全為 ★exact，但沒有任何一筆隸屬「生醫理工學院」——`?college=...` flag 表示 filter 完全無效。

**根本原因（tools.py 第 463-492 行）**：
Signal N 的迴圈（`for r in exact_name_hits`）在給予 boost 前只驗證 `student_college`（教學目的：學生有沒有資格選），完全沒有判斷 `college` 或 `dept` 參數（教學目的：課程是否由指定單位開設）。

```python
# 現有程式碼（僅 student_college）
if student_college:
    ...  # 驗證修課資格
# ← 缺少 college / dept 驗證
code_scores[code] += NAME_EXACT_BOOST
```

**建議修正（在 boost 前插入）**：
```python
# Signal N：驗證 college / dept filter（第 489 行後、第 490 行前插入）
if college and meta.get("college", "") != college:
    continue
if dept and meta.get("dept", "") != dept:
    continue
```
這保持與 Signal A/B Qdrant filter 的一致性：college/dept 是「硬性條件」，exact_match boost 不得繞過。

**優先級**：Critical，應最先修。

---

### Issue 3：服務學習課程（SC0003 / SC0004）頻繁出現在不相關查詢

**現象**：
加上任何 `student_college` filter 後，查詢「機器學習」、「程式設計」、「創業」等主題，SC0003 / SC0004（服務學習課程）幾乎穩定出現在前 2 名。

#### 根本原因分析：BM25 vs Dense Embedding 各貢獻多少？

Qdrant 目前的 hybrid 架構：
```
Prefetch dense (limit=n*3)  ┐
                             ├→ RRF（等權融合）→ 最終排名
Prefetch BM25  (limit=n*3)  ┘
```
RRF 對兩路等權，但兩者的「誤觸發」機制不同：

**Dense Embedding（主因）**：
- 「服務學習課程」在 embedding 空間落在「通用教育」區域，對機器學習、程式設計、創業等**任何**教育主題查詢都有中等相似度
- 查詢「程式設計」時 dense 仍會把 SC 課帶進來，但 BM25 此時分數為 0（無共同 token）
- 若 SC 課在「程式設計」查詢下還排前列 → 純 dense 的問題

**BM25（次要加速器）**：
- 僅在 query 含「學習」字元時才有貢獻（如「機器學習」、「深度學習」→ 與「服務學習」共享「學習」token）
- BM25 IDF 對「學習」這種高頻字懲罰低，給 SC 課額外加分
- 對「程式設計」、「創業」等 query，BM25 對 SC 課的分數為 0

**結論**：BM25 是在特定 query（含「學習」）的放大器，但 dense embedding 才是 SC 課全面干擾的根本原因。

#### 降低 BM25 貢獻的分析

目前架構下，降低 BM25 影響有幾個選項：

| 方案 | 做法 | 效果 | 副作用 |
|------|------|------|--------|
| 縮小 BM25 pool | `limit=n*1` (原 n*3) | 減少 BM25 在 RRF 的比重 | 削弱所有 exact keyword 搜尋（課號、特殊術語） |
| 換 DBSF 融合 | `Fusion.DBSF` | 依分數分布正規化，BM25/dense 差異更合理 | 行為改變大，需完整重測 |
| BM25 分數門檻 | Qdrant prefetch 暫不支援直接閾值 | — | 需自行取 sparse vector 分數後篩 |

**結論**：全局調降 BM25 會傷害精確術語搜尋（這是 BM25 最有價值的場景）。針對 SC 課程的問題，更適合用**課程層級**的解法而非調整全局參數。

#### 建議修正方案

**方案 A：Payload 標記 + Qdrant filter 排除（推薦，長期乾淨）**

在 Qdrant payload 加 `course_category: "service_learning"` 欄位，
`tool_search_courses` 組裝 filter 時預設加入 must_not 排除：
```python
# 預設排除服務學習課程（除非明確要找服務學習）
if not kwargs.get("include_service_learning"):
    base_filters.append(FieldCondition(
        key="course_category",
        match=MatchValue(value="service_learning"),
    ))
    # 在 Qdrant 的 must_not 區段加入
```
這樣 SC 課從 A/B/A_excl/B_excl 四路均被排除，Signal C 也不會帶入。

**方案 B：課號前綴快速過濾（最快，短期用）**

在最終排名輸出前：
```python
ranked_codes = [c for c in ranked_codes if not c.startswith("SC")]
```
缺點：硬編碼，未來新增服務學習課需手動維護。

**推薦執行順序**：先用方案 B 快速消除干擾，同時規劃方案 A 的 payload 更新腳本。
方案 A 需執行 `scripts/rag/update_XXX_payload.py` 更新 Qdrant，與方案 B 不衝突可並行。

---

### Issue 4：課名「包含 query」的課程未獲加分（Partial Name Match 缺失）

**現象（測試案例：程式設計 + student_college=文學院）**：
- 最佳答案「程式設計-Python」（GS4719）沒有 ★exact，排在第 5 名以後
- 但課名完整包含 query 字串「程式設計」，語意上屬於非常精確的匹配

**現有機制的限制**：
Signal N 僅在 `name_zh == query`（完全相等）時加分。`程式設計-Python != 程式設計`，故不觸發。

**建議修正（新增 Signal N2：Partial Name Match）**：
```python
PARTIAL_BOOST = 0.05  # vs NAME_EXACT_BOOST = 0.15（只有 1/3 強度，不搶第一名）

partial_match_codes: set[str] = set()
for r in exact_name_hits_expanded:  # 用 get_courses_by_name_contains(query) 或從既有 Qdrant pool 篩選
    meta = r.get("metadata", {})
    name_zh = meta.get("name_zh", "")
    if query in name_zh and name_zh != query:  # partial（非 exact）
        code = meta.get("course_code", "")
        # 通過 college / dept / student_college 驗證
        ...
        code_scores[code] = code_scores.get(code, 0.0) + PARTIAL_BOOST
        partial_match_codes.add(code)
```
輸出欄位可加 `"partial_match": True`，讓 LLM 理解這是「課名含查詢詞」的課程。

**實作選項**：
- Option 1：在 Qdrant 使用 `match_text` filter（`name_zh` 字串含 `query`）做額外搜尋，pool=n*2
- Option 2：從 Signal A/B 已回傳的結果中，後處理篩選 `query in name_zh`，不另做 Qdrant query（較輕量）
- **推薦 Option 2**，因為相關課程幾乎已在 A/B pool 中，不需要新的 Qdrant call。

---

---

## 9. 多班別課程：目前儲存方式與 LLM 回傳分析

> 分析時間：2026-05-15

### 9.1 Qdrant 怎麼存多班別課程

`build_vector_index.py` 的關鍵邏輯：

```python
code_raw = course.get("課號-班別", "")   # → "SC0003-A"
code     = clean_code(code_raw)           # → "SC0003"（去掉班別後綴）

doc_id   = f"{year}{semester}_{serial}_{code_raw}"   # → "1141_08001_SC0003-A"（唯一）
payload["course_code"] = code                         # → "SC0003"（無班別）
payload["dept"]        = course.get("系所")           # → "學務處-服務學習發展中心"（開課單位，全班共用）
payload["teacher"]     = course.get("授課教師")       # → 每班不同 ✓
payload["class_time"]  = course.get("上課時間")       # → 每班不同 ✓（但沒有進入 _fmt_courses）
payload["objective"]   = syllabus.get("課程目標")     # → 每班不同 ✓（進入 summary）
```

**結論：每個班別在 Qdrant 是獨立的一個向量點，但 payload 裡沒有存班別字母（-A / -B）。**

| 欄位 | 單班還是多班共用 | 說明 |
|------|----------------|------|
| `doc_id` | 每班唯一 | 含班別後綴（SC0003-A），但 LLM 不可見 |
| `course_code` | 全班共用 | 去掉 -A/-B（SC0003） |
| `dept` | 全班共用 | 開課單位（服務學習發展中心） |
| `college` | 全班共用 | 中心、處室 |
| `teacher` | 每班不同 ✓ | 不同老師 |
| `class_time` | 每班不同 ✓ | 存在 payload，但未進 `_fmt_courses` |
| `when_contexts` | course_code 層級聚合 | `update_schedule_payload.py` 按 course_code 彙整，所有班別共用同一份 |
| `objective` / `content` | 每班不同 ✓ | 各班綱要不同，進入 summary |
| eligibility | course_code 層級 | `eligibility_lookup.get(code)` — 所有班別共用同一份 eligibility |

---

### 9.2 LLM 從 `tool_search_courses` 看到什麼

`_fmt_courses()` 目前回傳的欄位：

```python
{
  "course_code":   "SC0003",            # 無班別字母，所有班看起來一樣
  "name_zh":       "服務學習課程",
  "name_en":       "Student Service-Learning",
  "dept":          "學務處-服務學習發展中心",  # 開課單位，所有班一樣
  "college":       "中心、處室",
  "credits":       0,
  "type":          "必修",
  "teacher":       "李婉歆",            # 唯一的班別識別資訊 ✓
  "when":          "大一上（共 N 系必修）", # course_code 層級聚合，非班別特定
  "concepts":      "...",
  "technologies":  "...",
  "summary":       "課程目標：...",      # 來自各班綱要，每班不同 ✓
  "distance":      0.xxxx
  # ← 沒有 class_section，LLM 無法知道這是「A班」或「B班」
  # ← 沒有 class_time，LLM 無法告訴使用者上課時間
  # ← 沒有 serial（流水號），使用者無法查選課系統
}
```

**SC0003 搜尋結果的 LLM 視角**：
- 多筆資料都叫 `course_code="SC0003"`、`name_zh="服務學習課程"`、`dept="學務處-服務學習發展中心"`
- 唯一差異是 `teacher` 和 `summary`（課程目標的細節）
- LLM 無法判斷這些是「同課程的不同班別」還是「不同課」
- LLM 不知道哪個班是給哪個系的（因為 dept 都是服務學習發展中心，不是目標科系）

**一般科目多班別的 LLM 視角**（如資工系程式設計有 A/B 班）：
- 兩筆都叫 `course_code="CE1001"`、`name_zh="程式設計"`、`dept="資訊工程學系"`
- 唯一差異是 `teacher`、`summary`
- LLM 無法說出「A班 李老師 週二34節、B班 王老師 週四56節」

---

### 9.3 資訊缺口與需要改什麼

**缺口 1：無班別字母（class_section）**

`doc_id` 有班別字母（SC0003-A）但 LLM 不可見。payload 裡沒有存 `-A`。
LLM 無法區分同課號的不同班別，也無法引導使用者用正確班別去選課。

**缺口 2：無流水號（serial）**

流水號是 NCU 課務系統的唯一識別碼，使用者查選課需要它。
目前只用在 doc_id 構成，沒有放進 payload 供 LLM 輸出。

**缺口 3：class_time 不進 `_fmt_courses`**

`class_time`（上課時間，如 "Wed8A"）存在 payload 但 `_fmt_courses` 沒有回傳它。
LLM 無法告訴使用者這門課幾點上。

**缺口 4：`tool_search_courses` 不做班別去重**

同課號多班別全部進入 16 筆 pool，同一門課佔多個名額。
`_deduplicate_courses_by_name` 函式存在但只在 `tool_get_course_details` 被呼叫，
`tool_search_courses` 不去重。

**缺口 5：eligibility 以 course_code 為鍵（SC0003 的根本問題）**

`eligibility_lookup.get(code)` 用去班別的 course_code 查，
所有 SC0003-X 共用同一份 eligibility → 聚合後誤標 `is_open_to_all_undergrad: true`。
實際上每個班別只對一個系所開放。

---

### 9.4 建議修改清單

#### 改動 A：payload 加 `class_section` 和 `serial` 欄位（build_vector_index.py）

```python
# 在 payload dict 中加入：
"class_section": code_raw.split("-")[1] if "-" in code_raw else "",  # "A", "B", "" for no-section courses
"serial":        serial,   # 流水號（已從 course.get("流水號") 讀取，只是沒存進 payload）
```

**重新 build Qdrant index 才生效。**

#### 改動 B：`_fmt_courses` 加 `class_section`、`serial`、`class_time`（tools.py）

```python
entry = {
    ...現有欄位...,
    "class_section": m.get("class_section", ""),  # "A" / "B" / "" 
    "serial":        m.get("serial", ""),          # 流水號，供使用者查選課
    "class_time":    m.get("class_time", ""),      # 原始上課時間字串
}
```

#### 改動 C：`tool_search_courses` 加班別去重/分組（tools.py）

在 `_fmt_courses` 之後，對同 `course_code` 的多筆結果分組：

```python
# 方案：保留得分最高的班別為代表，其餘附在 other_sections
from collections import defaultdict
grouped: dict[str, list] = defaultdict(list)
for entry in fmt_results:
    grouped[entry["course_code"]].append(entry)

final = []
for code, entries in grouped.items():
    rep = entries[0]  # 最高分班別（已排序）
    if len(entries) > 1:
        rep["other_sections"] = [
            {"class_section": e["class_section"], "teacher": e["teacher"],
             "class_time": e["class_time"], "serial": e["serial"]}
            for e in entries[1:]
        ]
    final.append(rep)
```

這樣 LLM 收到一筆 SC0003，知道它有 N 個其他班別，可以說「此課程共有 X 個班別，請依所屬系所選對應班別」。

#### 改動 D：eligibility per section（長期，複雜）

將 eligibility pipeline 改為以 `code_raw`（含班別）為鍵，而非 `code`。
每個班別獨立記錄 `dept_include`、`is_open_to_all_undergrad` 等。
**優先低**，目前 SC0003 問題用 Issue 3 的 `course_category` 排除法先解。

---

### 9.5 優先順序

| 改動 | 難度 | 影響 | 建議順序 |
|------|------|------|---------|
| A：payload 加 class_section/serial | 中（需重建 index） | 解缺口 1/2，是後面改動的前提 | 1st |
| B：`_fmt_courses` 輸出新欄位 | 低 | LLM 看到班別/流水號 | 1st（同 A） |
| C：`tool_search_courses` 班別分組 | 中 | 解缺口 4，減少名額浪費 | 2nd |
| D：eligibility per section | 高 | 根本修 SC0003 問題 | 暫緩 |

---

### 問題摘要與優先順序

| # | 問題 | 嚴重度 | 修正複雜度 | 建議優先 |
|---|------|--------|-----------|---------|
| 2 | Signal N 忽略 college/dept filter | Critical | 低（2 行 continue） | **最優先** |
| 1 | exact_match 佔滿 n 名額 | High | 高（API 格式改動） | 次優先 |
| 3 | 服務學習課程誤闖 | Medium | 中（payload 標記） | 第三 |
| 4 | Partial Name Match 缺失 | Low-Medium | 中（後處理篩選） | 最後 |

**建議執行順序**：先修 Issue 2（Critical，一行改動無副作用），確認測試通過後再處理 Issue 1 的 API 格式重構（影響面廣，需同步更新 LLM tool description）。
