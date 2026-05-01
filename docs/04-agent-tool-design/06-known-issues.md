# Tool 整合與 Hybrid Retrieval 設計

> 更新時間：2026-04-30  
> 目的：按功能分組分析 17 個 tool，評估合併機會、hybrid 改進方向、top-k / rerank 策略，以及相似課程的更好算法。

---

## 一、功能分組現況

| 組別 | 工具 | 目前信號來源 |
|------|------|------------|
| **找課程** | search_courses, get_dept_courses, get_course_eligibility, get_prereq_info, get_course_syllabus | Qdrant 向量 / 圖 JSON walk / eligibility JSON |
| **找學程** | get_program_courses, get_program_description, search_programs | 圖 JSON walk / program JSON / Qdrant 向量 |
| **課程深度探索** | find_similar_courses, get_course_knowledge_map, explore_concept_neighborhood, ppr_explore | 圖 RRF+向量 / 圖 JSON / Qdrant+BFS / igraph PPR |
| **找系所** | get_dept_info, get_depts_by_tech | Qdrant 向量 / 圖多跳 |
| **找教師** | get_teacher_info, search_teachers | Qdrant 精確+圖 / Qdrant 向量 |
| **修業規定** | get_graduation_requirements | schedule_draft JSON + requirements_notes JSON |

---

## 二、分組詳細分析

---

### 2.1 找課程群（5 個工具）

#### 現有工具對比

| 工具 | 輸入 | 信號 | 適用場景 |
|------|------|------|---------|
| `search_courses` | 自然語言 query + 過濾條件 | Qdrant 向量（無 tech）/ 圖精確（有 tech） | 廣泛課程搜尋 |
| `get_dept_courses` | dept_name, course_type | 圖 JSON walk（→ Qdrant fallback） | 系所必/選修結構化清單 |
| `get_course_eligibility` | course_query | Qdrant 精確+向量 → eligibility JSON | 查修課資格 |
| `get_prereq_info` | course_query | Qdrant 向量 top-1 → prereq_codes 展開 | 查先修條件 |
| `get_course_syllabus` | name_zh / course_code / dept | Qdrant 精確+消歧義 | 查官方課綱 |

#### 合併機會

**`get_course_eligibility` + `get_prereq_info` + `get_course_syllabus` → `get_course_detail`**

三個工具的輸入形式相同（課程名稱/課號），且常被 LLM 連續呼叫。整合後一次回傳：
```
課綱（objective / content / textbook）
+ 修課資格（raw_conditions）
+ 先修課號展開（prereq_details）
```

> 目前已有 `course_index.json` 統一索引，後端 `/api/chat/course_detail` 已實作，可直接對接。
> 整合後 LLM 只需 1 次呼叫，而非 2-3 次。

#### `search_courses` 的 Hybrid 改進

**現況問題**：無 tech 參數時，純 Qdrant 向量搜尋課程文字 embedding，可能漏掉「名稱不出現在課綱但在知識圖譜中有節點」的技術課程。

**Query Expansion via Graph**（低風險）：
```
query → _search_concept_nodes(query, top_k=3)   ← Qdrant ncu_graph_nodes
      → 取得 top-3 概念節點的 name（如「深度神經網路」「卷積」）
      → 展開 query：expanded = query + " " + " ".join(concept_names)
      → retriever.search_courses(expanded, filters, n_results)
```

**實作位置**：`tools.py` `tool_search_courses()` 無 tech 分支，在呼叫 `retriever.search_courses` 前加 3 行。

**top-k 選擇**：
- 目前 n=8（預設），已足夠 LLM 摘要
- Query expansion 後建議先取 n×2=16，再做 MMR 縮回 n（見第四節）

---

### 2.2 找學程群（3 個工具）

#### 現有工具對比

| 工具 | 輸入 | 信號 |
|------|------|------|
| `get_program_courses` | program_name | 圖 JSON walk |
| `get_program_description` | program_name | program_descriptions.json |
| `search_programs` | query | Qdrant ncu_credit_programs 向量 |

#### 合併機會

**`get_program_courses` + `get_program_description` → `get_program_info`**

兩者輸入相同（學程名稱），且幾乎總是被 LLM 連續呼叫。整合後：
```json
{
  "program_name": "...",
  "description": "完整說明",
  "required_courses": [...],
  "elective_courses": [...]
}
```

`search_programs` 保持獨立（輸入為 query，用於「找哪些學程和 AI 有關」場景）。

#### Hybrid 改進

`search_programs` 目前純 Qdrant 向量，無圖信號。可加：
- 用 query 走圖找相關 CreditProgram 節點（如 `ppr_explore(focus="credit_program")`）
- 兩路 RRF 融合（不急，效益中等）

---

### 2.3 課程深度探索群（4 個工具）

#### 現有工具對比

| 工具 | 輸入 | 算法 | 回傳粒度 |
|------|------|------|---------|
| `find_similar_courses` | course_name | RRF(圖共概念 + Qdrant 向量) | 課程列表 |
| `get_course_knowledge_map` | course_name | 圖出向邊 + 共概念課程(純圖) | 課程結構地圖（字串） |
| `explore_concept_neighborhood` | query（概念詞） | Qdrant ncu_graph_nodes → BFS N 跳 | 概念鄰域課程 |
| `ppr_explore` | seed（概念/課程名） | Qdrant 種子 + igraph Weighted PPR | 跨類型節點（課+師+系+概念） |

#### 工具邊界分析

四個工具的使用場景**互補而非重疊**：

```
「有哪些課和A相似？」        → find_similar_courses（輸入：課程名）
「A這門課在學什麼？」         → get_course_knowledge_map（輸入：課程名）
「有哪些課涵蓋X概念？」       → explore_concept_neighborhood（輸入：概念詞）
「和X相關的一切是什麼？」     → ppr_explore（輸入：概念/課程，跨類型）
```

**不建議合併**，但可改善個別工具。

#### `get_course_knowledge_map` 的相似課程改進

目前相似課程段落仍是純圖（`search_courses_by_concept_cluster` 純共概念數）。應與 `find_similar_courses` 使用相同的 RRF 邏輯：

```python
# tool_get_course_knowledge_map 修改：
similar = graph_service.search_courses_by_concept_cluster(course_name, top_n=25)
vec_sim  = retriever.search_courses(course_name, n_results=20)
# RRF 融合（與 find_similar_courses 共用相同邏輯，可抽為 _rrf_similar_courses(name)）
```

**建議抽出 `_rrf_similar_courses(course_name, top_n=15)` 輔助函式**，讓兩個工具共用。

---

### 2.4 找系所群（2 個工具）

| 工具 | 輸入 | 信號 |
|------|------|------|
| `get_dept_info` | query | Qdrant ncu_departments 向量 |
| `get_depts_by_tech` | tech_name | 圖多跳（Course → CurriculumPlan → Dept） |

兩者**場景完全不同**（介紹 vs 技術分布），不合併。

`get_depts_by_tech` 可選性優化：課程列表目前無排序，可用 tech_name 做 Qdrant 向量搜尋後 rerank（效益低，不急）。

---

### 2.5 找教師群（2 個工具）

| 工具 | 輸入 | 信號 |
|------|------|------|
| `get_teacher_info` | teacher_name（精確） | Qdrant 精確查 + 圖開課清單 |
| `search_teachers` | query（語意） | Qdrant ncu_teachers 向量 |

已是最精簡形式，不合併（輸入語義不同）。

---

## 三、相似課程：更好的算法選項

### 3.1 現況（已實作）

**RRF(k=60)**：圖共概念 top-25 + Qdrant 課程向量 top-20 → 融合排序。

優點：無需訓練，即插即用。  
缺點：圖路徑依賴手動標注的 Concept 節點（覆蓋率有限）；向量路徑使用課程文字 embedding，語意偏向課程描述風格。

---

### 3.2 改進選項（按實作難度）

#### Option A：概念集合 Embedding（中難度）⭐ 推薦

每門課程的概念節點在 `ncu_graph_nodes` 中已有向量。可計算**概念集合的平均 embedding** 作為課程的「概念向量」：

```python
# 建構時（build_qdrant_index.py）：
course_concept_vec = mean([ncu_graph_nodes[c] for c in course.concepts])
# 儲存到 ncu_courses 的額外向量欄位，或獨立 collection
```

查詢相似課程時：
```
課程 A 的概念向量 → ncu_courses payload filter / 額外向量搜尋
→ cosine 相似度排序
```

**優點**：捕捉概念語意密度（「深度學習」的 embedding 和「機器學習」更近，而非只看是否共享同一節點）。  
**論文依據**：「Knowledge Graph Embeddings」類工作的降維思路；SET2VEC / PoolBERT 的集合 embedding 方法。

---

#### Option B：BM25 on Concept List（低難度）

把每門課的概念清單當作「詞袋」，用 BM25 計算課程間相似度：

```python
# concepts_A = ["機器學習", "神經網路", "梯度下降"]
# concepts_B = ["深度學習", "反向傳播", "神經網路"]
# BM25(A, B) 以 concepts_A 為 query，concepts_B 為 document
```

**優點**：不需額外向量；BM25 對罕見概念有 IDF 加權（罕見概念貢獻更大）。  
**缺點**：純詞彙匹配，「梯度下降」和「SGD」不會被視為相近。  
**可直接用 `rank_bm25` 套件實作**，不依賴 Qdrant。

---

#### Option C：Graph Embedding（高難度，需訓練）

在知識圖譜上訓練 **Node2Vec** 或 **LINE** embedding，讓圖中鄰近的節點 embedding 也接近：

```
Course_A ──COVERS──► Concept_X ◄──COVERS── Course_B
→ Node2Vec 遊走後 Course_A 和 Course_B embedding 相近
```

**論文依據**：
- Node2Vec（Grover & Leskovec, 2016）— 圖隨機遊走產生節點 embedding
- LINE（Tang et al., 2015）— 大型資訊網路 embedding，保持一階/二階近鄰
- LightGCN（He et al., 2020）— 協同過濾風格的圖卷積，適合推薦場景

**缺點**：需要持續重訓（圖更新時）；開發成本高。目前規模（~4000 課程）優先用 RRF，此選項留未來。

---

#### Option D：課程 Syllabus 的多向量搜尋（中難度）

目前課程 Qdrant 的向量是整段 `_text`（課綱摘要）。可改為**多欄位分段 embedding**：
- `objective_vec`：課程目標 embedding
- `content_vec`：授課內容 embedding
- `concepts_vec`：概念集合平均 embedding（同 Option A）

查詢時同時搜三個欄位，再用 RRF 融合。  
**論文依據**：ColBERT（Khattab & Zaharia, 2020）的多向量精細化思路；SPLADE 的稀疏+稠密混合。

---

### 3.3 推薦路線

```
短期（改動小）：
  Option B（BM25 概念）加入現有 RRF → 三路融合
  ① 圖共概念（shared_count，rank）
  ② Qdrant 課程向量（distance，rank）
  ③ BM25 概念列表（bm25_score，rank）
  → RRF(k=60) 三路融合

中期（需 build pipeline 改動）：
  Option A（概念集合 embedding）替換③
  → 概念語意相似度比純 BM25 更精準

長期（需訓練）：
  Option C（Node2Vec/LightGCN）
  → 全圖結構相似度，覆蓋「沒有共同概念但結構位置相近」的課程
```

---

## 四、top-k 與 Rerank 策略

### 4.1 目前問題

| 工具 | top-k 策略 | 問題 |
|------|-----------|------|
| `search_courses` | Qdrant top-n（無 rerank） | 結果可能高度重複（同課程不同班） |
| `find_similar_courses` | RRF top-15 | 可能有相似但非相關（同字詞） |
| `ppr_explore` | PPR top-k（無過濾） | 分數差距小時排名不穩定 |
| `explore_concept_neighborhood` | BFS depth-score top-k | 淺層節點可能過多 |

---

### 4.2 MMR（Maximal Marginal Relevance）

適合 `search_courses`、`find_similar_courses` 結果多樣化：

```python
def mmr(candidates: list[dict], query_vec: list[float],
        lambda_: float = 0.5, top_k: int = 8) -> list[dict]:
    """
    每次選分數最高且與已選集合最不相似的候選。
    candidates 需含 'vec' 欄位（embedding）和 'score'（relevance）。
    lambda_: 0 = 純多樣化，1 = 純相關性
    """
    selected, remaining = [], list(candidates)
    while len(selected) < top_k and remaining:
        mmr_scores = []
        for c in remaining:
            rel = c['score']
            if selected:
                max_sim = max(cosine_sim(c['vec'], s['vec']) for s in selected)
            else:
                max_sim = 0.0
            mmr_scores.append(lambda_ * rel - (1 - lambda_) * max_sim)
        best = remaining[max(range(len(remaining)), key=lambda i: mmr_scores[i])]
        selected.append(best)
        remaining.remove(best)
    return selected
```

**論文依據**：Carbonell & Goldstein（1998）— "The Use of MMR, Diversity-Based Reranking for Reordering Documents and Producing Summaries"

**限制**：需要各結果的 embedding，目前 `_fmt_search` 沒有回傳向量。需修改 `retriever.search_courses` 加 `with_vectors=True` 選項。

---

### 4.3 PPR 分數截斷

`ppr_explore` 的 PPR 分數差距小時，排名末端可能是噪音。建議加 **gap 截斷**：

```python
# graph_service.ppr_explore() 結果後處理
scores = [r['score'] for r in results]
if scores:
    mean_s, std_s = statistics.mean(scores), statistics.stdev(scores) if len(scores) > 1 else 0
    results = [r for r in results if r['score'] > mean_s - 0.5 * std_s]
```

---

### 4.4 各工具 top-k 建議

| 工具 | 建議內部 top-k | 最終回傳 | 說明 |
|------|-------------|---------|------|
| `search_courses` | Qdrant n×2 | MMR→n | 多樣化去重 |
| `find_similar_courses` | 圖 25 + 向量 20 | RRF→15 | 現況已合理 |
| `get_course_knowledge_map` | 圖 25 + 向量 20 | RRF→8 | 與 find_similar 共用 |
| `explore_concept_neighborhood` | BFS unlimited | score 截斷→top_k | 目前無截斷 |
| `ppr_explore` | PPR all | gap 截斷→top_k | 加 mean-std filter |

---

## 五、現有 Hybrid 實作（已完成）

| 工具 | 已實作 | 說明 |
|------|--------|------|
| `search_courses` | 3 層 Hybrid（query expansion + RRF） | 2026-04-30：Layer 1 ncu_graph_nodes 擴展 + Layer 2 Signal A/B + Layer 3 RRF(k=60) |
| `find_similar_courses` | RRF(圖共概念 + Qdrant 向量) | 2026-04-30 實裝，委派 `_rrf_similar_courses()` |
| `get_course_knowledge_map` | 相似課程段落改用 RRF | 2026-04-30：改用 `_rrf_similar_courses()` |
| `explore_concept_neighborhood` | Qdrant ncu_graph_nodes 入口 + igraph BFS | 已完成 |
| `ppr_explore` | Qdrant 種子 + igraph Weighted PPR + gap truncation | 2026-04-30：種子改 Qdrant 優先 + mean-0.5σ gap filter |

---

## 六、實作優先順序

| 優先 | 項目 | 狀態 | 效益 |
|------|------|------|------|
| ✅ | `search_courses` 3 層 Hybrid（query expansion + RRF） | **已完成** 2026-04-30 | 語意搜尋命中率提升 |
| ✅ | 抽出 `_rrf_similar_courses()` + 修 `get_course_knowledge_map` | **已完成** 2026-04-30 | 兩工具一致、地圖相似課程更準 |
| ✅ | `ppr_explore` gap 截斷（mean-0.5σ） | **已完成** 2026-04-30 | 排名末端雜訊減少 |
| ✅ | Option A 概念平均向量（`ncu_course_concept_vecs`） | **已完成** build_qdrant_index.py --phase3 | 概念語意相似度，需執行 Phase 3 |
| ★★★ | `get_course_detail` 整合（syllabus+eligibility+prereq） | 待實作 | LLM 少 2 次呼叫 |
| ★★☆ | `get_program_info` 整合（description+courses） | 待實作 | 學程查詢少 1 次呼叫 |
| ★★☆ | `find_similar_courses` 加入 BM25 概念列表（三路 RRF） | 待實作 | 相似度更精準（需 rank_bm25） |
| ★☆☆ | MMR 多樣化 | 待實作 | 需修改 with_vectors，成本中等 |

---

## 七、融合策略速查

### RRF（現有）
```python
# k=60，兩路以上皆適用，不需分數可比性
score[name] += 1 / (60 + rank)
```
論文：Cormack, Clarke, Buettcher (2009)

### 加權線性融合
```python
# 需先正規化至 [0,1]
score = α × graph_score + (1-α) × vector_score
# α=0.6（偏圖精確）；α=0.4（偏語意探索）
```

### BM25 概念詞袋
```python
# pip install rank_bm25
from rank_bm25 import BM25Okapi
corpus = [c['concepts'] for c in all_courses]   # list of list[str]
bm25   = BM25Okapi(corpus)
scores = bm25.get_scores(query_course['concepts'])
```
論文：Robertson & Zaragoza (2009) — BM25 原始論文

### MMR 多樣化
論文：Carbonell & Goldstein (1998)

---

## 八、可直接呼叫的現有接口

```python
# retriever.py
retriever.search_courses(query, filters, n_results, collection)
retriever.get_courses_by_name(name)
retriever.get_courses_by_code(code)
retriever.get_courses_by_dept_type(dept, type_, collection, limit)

# graph_service.py
graph_service._search_concept_nodes(query, top_k)        # Qdrant ncu_graph_nodes
graph_service.search_courses_by_tech(tech_name)          # 圖精確技術查詢
graph_service.search_courses_by_concept_cluster(course)  # 圖共概念排序 → list[dict]
graph_service.ppr_explore(seed_names, top_k, filter)     # igraph PPR
graph_service.explore_by_concept_neighborhood(query, hops, top_k)  # igraph BFS
```
