# 三種評分系統

> 文件版本：2026-04-21

系統共有三種分數，分別來自不同的資料源和算法。

---

## 1. ChromaDB `distance`（向量距離）

### 算法

**Euclidean Distance（L2 norm）**：

```
distance = sqrt( Σ(embedding_i - query_i)² )
```

ChromaDB 將文字嵌入為向量，搜尋時計算查詢向量與資料庫向量的 L2 距離。

### 特性

| 特性 | 說明 |
|------|------|
| 範圍 | 0 ~ ∞（無上限） |
| 0 的含義 | 完全相同的向量 |
| **越小越好** | distance 越小 = 語意越相似 |
| 無法跨 collection 比較 | 不同嵌入模型/collection 的 distance 不可互比 |

### 典型數值參考（大致範圍）

| distance 範圍 | 語意相似度 |
|-------------|-----------|
| 0.0 ~ 0.8 | 非常相似（幾乎相同內容） |
| 0.8 ~ 1.5 | 相關（主題相近） |
| 1.5 ~ 2.5 | 弱相關 |
| > 2.5 | 不相關 |

> ⚠️ 實際閾值因嵌入模型而異，以上為參考值。

### 使用工具

- `search_courses`（`n_results` 筆，ChromaDB 預設依 distance 升序排列）
- `search_teachers`
- `get_dept_info`
- `get_prereq_info`（內部搜尋，取最近似 3 筆）
- `get_course_eligibility`（語意搜尋 fallback，5 筆）

### 目前狀態

`distance` 值由 `retriever.search_courses()` 回傳，包含在 raw result 的 `distance` 欄位。  
**但目前未傳遞至 SSE `tool_done` 事件**，前端 DebugTracePanel 看不到此分數（待補強）。

---

## 2. 知識圖譜 `shared_concepts`（共享概念數）

### 算法

**概念節點交集大小（Jaccard-like）**：

```
shared_concepts(A, B) = |concepts(A) ∩ concepts(B)|
```

其中 `concepts(X)` 是課程 X 的 `COVERS_CONCEPT`/`TEACHES_TECH` 出向邊所連到的 Concept/Technology 節點集合。

### 計算流程

1. 找種子課程 A 的所有概念節點集合 `S`
2. 從 `S` 的每個概念節點走反向邊，找有連到它們的其他課程 B
3. 計算每門課 B 與 A 的共享概念數（`shared_concepts`）
4. 依 `shared_concepts` 降序排列

```python
for concept_id in seed_concepts:
    for (src, rel) in in_adj[concept_id]:
        if rel in ("COVERS", "TEACHES"):
            score[src] = score.get(src, 0) + 1  # 每多一個共享概念 +1
```

### 特性

| 特性 | 說明 |
|------|------|
| 範圍 | 0 ~ ∞（整數） |
| **越大越好** | 共享概念越多 = 課程越相似 |
| 完全圖結構決定 | 只取決於知識圖譜中標注的概念邊 |

### 典型數值參考

| shared_concepts | 課程相似程度 |
|----------------|------------|
| 0 | 無共享概念（不相關） |
| 1 ~ 2 | 弱相關 |
| 3 ~ 5 | 相關（有共同主題） |
| 6 ~ 10 | 高度相關 |
| 10+ | 幾乎同一主題 |

### 使用工具

- `find_similar_courses`：`top_n=15`，回傳字串中包含 `[共享概念：N 個]`
- `get_course_knowledge_map`：相似課程部分（top 8）包含 `[共享 N 個概念]`

### 限制

- 只計算知識圖譜中**已建立概念邊**的課程，未收錄的課程不會出現
- 不同學院可能有不同的概念標注粒度

---

## 3. PPR `score`（Personalized PageRank 分數）

### 算法

**Personalized PageRank（帶重置的隨機遊走）**：

```
PPR(v) = α × Σ [PPR(u)/out_degree(u)] + (1-α) × personalization(v)
```

其中：
- `α = 0.85`（阻尼係數，表示從種子重置的概率為 1-0.85=0.15）
- `personalization[seed_id] = 1/len(seeds)`（種子節點均分）
- 其他節點 `personalization = 0`
- `n_iter = 25`（收斂迭代次數）

### 輸出分數

```python
score = round(raw_ppr_score * 1000, 4)  # 乘以 1000 讓數字可讀
```

### 特性

| 特性 | 說明 |
|------|------|
| 範圍 | 0 ~ 1000（原始 PPR 為 0~1 的概率） |
| **越大越好** | 分數越高 = 與種子概念越相關 |
| 跨類型比較 | 可同時比較課程、教師、系所、概念節點的相關性 |
| 多跳擴散 | 能捕捉間接關係（A→B→C 的間接相關性） |

### 典型數值參考

| score 範圍 | 相關程度 |
|-----------|---------|
| 100 ~ 1000 | 強相關（直接連接或高度間接相關） |
| 10 ~ 100 | 相關 |
| 1 ~ 10 | 弱相關 |
| < 1 | 基本不相關 |

> ⚠️ 分數分布會受圖的大小和結構影響，不同種子的分數範圍可能差異很大。

### 使用工具

- `ppr_explore`：`top_k=15`（工具預設值），目前回傳字串中**未顯示 score**（待補強）

### 與 `shared_concepts` 的比較

| 面向 | shared_concepts | PPR score |
|------|----------------|-----------|
| 搜尋範圍 | 只找課程 | 跨課程、教師、系所、概念 |
| 關係深度 | 直接共享概念 | 多跳間接關係 |
| 可解釋性 | 高（有幾個共同概念） | 中（PageRank 概率） |
| 適合問題 | 「哪些課和 X 最像？」 | 「和 X 相關的一切是什麼？」 |

---

## 三種分數在前端的顯示計畫

目前 DebugTracePanel 只顯示工具名稱和 `courses_found`（課程名稱列表），**尚未顯示分數**。

**計畫補強**（待實作）：

| 工具 | 分數欄位 | 顯示位置 |
|------|---------|---------|
| `search_courses` | `distance`（Euclidean，越小越好） | 課程 badge 後面，如 `dist=0.92` |
| `search_teachers` | `distance` | 同上 |
| `find_similar_courses` | `shared_concepts`（整數，越大越好） | badge 後，如 `concepts=8` |
| `get_course_knowledge_map` | `shared_concepts` | 同上 |
| `ppr_explore` | `score`（×1000，越大越好） | badge 後，如 `ppr=342.5` |

需要的後端修改：`tool_done` SSE 事件新增 `scores: list[float]` 欄位（與 `courses_found` 一一對應）。
