# Graph 設計優化與已知問題

> 更新時間：2026-04-25（最後更新：2026-04-25）
> 現況：圖有 14,602 節點 / 29,567 邊，21 個工具（含 5 個新工具）

---

## 現況確認（程式碼分析結果）

| 問題 | 現狀 |
|------|------|
| PPR 加權 | ✅ igraph Weighted PPR（C 底層），邊權重依 relation 分級（0.3–1.5），0.23s/次 |
| SIMILAR_TO 邊 | ✅ 已啟用：igraph PPR directed=False 自然納入，BFS 也走 SIMILAR_TO 邊 |
| 圖節點查詢 | ✅ Qdrant ncu_graph_nodes（10,922 節點，dim=3072），向量入口 + 字串 fallback |
| 圖 metadata filter | ✅ igraph `vs.select()` 原生語法（取代 NetworkX for loop） |

---

## 一、已知問題解決方案

### ✅ 問題 1：向量找圖節點（Vector Node Entry）— 已完成

**實作**：Qdrant 本地模式 `ncu_graph_nodes` collection（取代原 ChromaDB 方案）
- 10,922 個 Concept/Technology/Field 節點，dim=3072，Cosine 距離
- 資料位置：`data/processed/qdrant_data/`
- 建立腳本：`scripts/rag/build_qdrant_index.py`
- 查詢流程：Qdrant 向量搜尋 → node_id → 走圖 BFS/PPR
- Fallback：字串比對（Qdrant 未建立時自動退回）

**影響工具**：`explore_concept_neighborhood`（新工具）、`ppr_explore`（種子查找）

---

### 問題 2：圖的 Metadata Filter

**痛點**：無法直接在圖上做 `WHERE level='ugrad' AND node_type='Course'` 的過濾，部分資料流需要繞道 ChromaDB。

**方案（不換套件）**：在 `graph_service.py` 新增 `filter_nodes` 工具函式，用 Python generator 過濾：

```python
def filter_nodes(G, node_type=None, **attr_filter):
    for nid, data in G.nodes(data=True):
        if node_type and data.get("node_type") != node_type:
            continue
        if all(data.get(k) == v for k, v in attr_filter.items()):
            yield nid, data
```

效能評估：14K 節點的線性掃描在 Python 中約 5-20ms，API 延遲可接受。

**若需要更快速的過濾**：用 DuckDB 在記憶體中建節點屬性的 columnar index，支援 SQL WHERE 語法，查詢效能可達微秒級。

---

### ✅ 問題 3：Weighted PPR（加權邊）— 已完成

**實作**：igraph `personalized_pagerank(directed=False, damping=α, reset=v, weights="weight")` C 底層，效能 0.23s/次。

**痛點（已解）**：現有 PPR 將 TEACHES（教技術）和 HAS_CURRICULUM（課程計畫結構）視為等權，導致結構性節點（CurriculumPlan、ElectiveGroup）得到不合理的高分。

**設計：新增邊權重對應表**

| 邊類型 | weight | 理由 |
|--------|--------|------|
| `COVERS_FIELD` relevance=high | 1.5 | 高相關領域，強語意連結 |
| `COVERS_FIELD` relevance=medium | 1.0 | 中相關 |
| `COVERS_FIELD` relevance=low | 0.5 | 低相關，弱化影響 |
| `TEACHES`（技術邊） | 1.2 | 技術是核心教學內容 |
| `COVERS`（概念邊） | 1.0 | 標準概念連結 |
| `SIMILAR_TO` | ratio 值（0.7~1.0） | 使用字串相似度作為天然權重 |
| `PREREQUISITE_OF` | 0.8 | 先修關係，稍弱 |
| `EXPERT_IN` / `RELEVANT_EXPERT` | 1.0 | 教師-領域關係 |
| 結構邊（REQUIRES、HAS_* 等） | 0.3 | 降低行政結構邊干擾 |

**修改位置**：`backend/app/services/graph_service.py` 的 PPR power iteration（約 line 598-620）

```python
# 改前
spread = alpha * score / len(nbrs)

# 改後
total_w = sum(get_edge_weight(G, nid, nbr) for nbr in nbrs)
for nbr in nbrs:
    w = get_edge_weight(G, nid, nbr)
    new_scores[nbr] += alpha * score * (w / total_w)
```

---

### ✅ 問題 4：啟用 SIMILAR_TO 邊 — 已完成

**實作**：igraph 建圖時 SIMILAR_TO 邊已去重並納入（seen_similar set 防止雙向重複計權），PPR 以 `directed=False` 自然雙向遍歷，BFS 工具 `explore_concept_neighborhood` 也走 SIMILAR_TO 邊。

**現狀（已解）**：圖中有 5,064 條 SIMILAR_TO 邊（字串相似度 ≥ 0.70），完全未被使用。

**三種啟用方式**：

**A. PPR 整合（最簡單）**：PPR 已在無向模式遍歷，只需確認 SIMILAR_TO 邊不被過濾即可。加入後同義概念自然在 PPR 中獲得高分。

**B. 查詢擴展（search_courses graph-first）**：找到種子 tech 節點後，透過 SIMILAR_TO 擴展種子集合再一起走反向邊：

```python
# 找到 concept::深度學習
seed_nodes = {concept_node}
# 透過 SIMILAR_TO 擴展
for neighbor in G.successors(concept_node):
    if G.edges[concept_node, neighbor].get("relation") == "SIMILAR_TO":
        seed_nodes.add(neighbor)
# 再從所有種子走反向邊找課程
```

**C. 新工具 `expand_concept_synonyms`**：給定概念，找出整個 SIMILAR_TO 連通分量，回傳語意相近的概念群。

**建議**：同時做 A + B，效益最大且改動最小。

---

## ✅ 二、GraphRAG 社群分群（已完成）

**適用場景**：「AI 相關課程有哪些主要類別？」「學校課程大致分幾個領域？」這類整體性問題。

**實作成果**：
1. Course+Concept+Technology 語意子圖上執行 **Leiden 演算法**（leidenalg 0.11.0）
2. 加權邊（COVERS_FIELD high=1.5/medium=1.0/low=0.5，TEACHES=1.2，COVERS=1.0）
3. modularity=0.8756，共 48 個社群（≥3 門課），全部已命名
4. 離線儲存：`data/processed/graph/communities.json`
5. 建立腳本：`scripts/graph/compute_communities.py`（計算）、`scripts/graph/label_communities.py`（命名）
6. **新工具**：
   - `get_course_community(course_name)` — 找一門課所在社群及同類別課程
   - `list_course_communities()` — 列出所有 48 個類別（整體性問題入口）

---

## 三、新工具設計（6 個）

### 工具 17：`get_learning_path` — 學習路徑展開

| 項目 | 說明 |
|------|------|
| 功能 | 給定目標課程，遞迴展開先修鏈 |
| 算法 | BFS 走 `PREREQUISITE_OF` 反向邊，最多 3 層 |
| 資料源 | 知識圖譜（PREREQUISITE_OF 邊，160 條） |
| 使用場景 | 「我想修機器學習，需要先修哪些課？」 |

回傳範例：
```
【機器學習概論】的先修路徑：
  ← 先修（必要）：資料結構（資工系，大二上）
  ← 先修（必要）：線性代數（數學系，大一下）
共需先修 2 門課
```

---

### ✅ 工具 18：`explore_concept_neighborhood` — 概念鄰域探索（已完成）

| 項目 | 說明 |
|------|------|
| 功能 | 語意找入口節點 + 圖展開 N 跳鄰域 |
| 算法 | Qdrant `ncu_graph_nodes` 向量搜尋 → top-5 節點 → SIMILAR_TO + COVERS + TEACHES + COVERS_FIELD 展開 2 跳 |
| 資料源 | Qdrant 本地（新建）+ 知識圖譜 |
| 使用場景 | 「和神經網路有關的課程？」（解決字串比對盲點） |
| 狀態 | ✅ `tools.py` 已實作，`graph_service.py` `explore_by_concept_neighborhood()` 已完成 |

---

### 工具 19：`get_dept_concept_coverage` — 系所概念覆蓋地圖

| 項目 | 說明 |
|------|------|
| 功能 | 統計系所課程覆蓋的技術/概念，依頻率排名 |
| 算法 | 找系所所有課程 → 彙整 TEACHES + COVERS 出邊 → 計數排序 |
| 資料源 | 知識圖譜 |
| 使用場景 | 「資工系的課程主要教哪些技術？」「哪個系最常教統計？」 |

---

### 工具 20：`find_expert_courses` — 教師專長對應課程

| 項目 | 說明 |
|------|------|
| 功能 | 找與教師專長最相關的課程（不限該教師開授） |
| 算法 | 取教師 EXPERT_IN + RELEVANT_EXPERT Field 節點 → 反向 COVERS_FIELD 找課程 → 加入 COURSE_EXPERT 直連課程 |
| 資料源 | 知識圖譜 |
| 使用場景 | 「誰最適合教人工智慧？」「這門課的推薦顧問是哪位老師？」 |

與現有工具的差異：`get_teacher_info` 只查「此教師開授哪些課」，本工具查「哪些課與此教師的研究方向最相關」。

---

### 工具 21：`compare_courses_by_concepts` — 課程概念比較

| 項目 | 說明 |
|------|------|
| 功能 | 比較兩門課的概念重疊與差異 |
| 算法 | 集合運算：A∩B（共同）、A−B（課A獨有）、B−A（課B獨有） |
| 資料源 | 知識圖譜（COVERS + TEACHES 邊） |
| 使用場景 | 「資料結構和演算法的差別是什麼？」「機器學習和深度學習哪裡不同？」 |

---

### 工具 22：`get_cross_dept_concept_bridges` — 跨系橋接概念

| 項目 | 說明 |
|------|------|
| 功能 | 找兩個系所之間的橋接概念（共同覆蓋的概念） |
| 算法 | 系所 A 課程概念集合 ∩ 系所 B 課程概念集合 |
| 資料源 | 知識圖譜 |
| 使用場景 | 「資工和數學系有什麼共同的學習內容？」「跨域學習哪些概念最能銜接？」 |

---

## 四、論文參考

| 論文 | 年份 | 核心貢獻 | 對本系統的啟發 |
|------|------|---------|--------------|
| **Microsoft GraphRAG** (Edge et al.) | 2024 | 社群偵測 → 分層摘要，處理整體性問題 | 離線預計算社群，回答「課程體系是什麼」 |
| **HippoRAG** (Guo et al.) | 2024 | PPR 做語意擴散，解決多跳查詢 | 本系統已部分實作，加入 SIMILAR_TO + weighted 可完整對齊 |
| **G-Retriever** (He et al.) | 2024 | GNN + RAG，從問句提取相關子圖 | 未來可用於「自動提取最小相關子圖」 |
| **SubgraphRAG** (Li et al.) | 2024 | 最小相關子圖提取，減少 LLM context 長度 | 複雜多跳查詢時精準截取子圖傳給 LLM |
| **Think-on-Graph / ToG** (Sun et al.) | 2023 | 在圖上做束搜尋（beam search），更精準多跳推理 | 可取代目前 PPR，做到路徑可解釋的推理 |
| **Entity-Centric RAG** | 2024 | 先 NER 識別實體再走圖 | 本系統已實作，可用 NER 強化 entity 辨識精度 |

---

## 五、實作優先順序

| 優先級 | 功能 | 效益 | 改動範圍 |
|--------|------|------|---------|
| ✅ 已完成 | 啟用 SIMILAR_TO 邊（PPR + BFS） | 立即改善「找不到概念」問題 | igraph directed=False |
| ✅ 已完成 | Weighted PPR（igraph） | 搜尋結果更精準，結構節點干擾降低 | graph_service.py 完整改寫 |
| ✅ 已完成 | 工具 18：`explore_concept_neighborhood` | 根本解決字串比對盲點 | Qdrant ncu_graph_nodes + BFS |
| ✅ 已完成 | GraphRAG 社群分群（Leiden）+ 兩個工具 | 整體性問題入口 | compute_communities.py + tools.py |
| ★★★ 高 | 工具 17：`get_learning_path` | 填補缺失的「學習規劃」場景 | 新工具，BFS on PREREQUISITE_OF，低風險 |
| ★★☆ 中 | 工具 19：`get_dept_concept_coverage` | 「系所比較」、「哪個系教什麼」 | 新工具，統計邊，低風險 |
| ★★☆ 中 | 工具 20：`find_expert_courses` | 強化教師-課程語意連結 | 新工具，利用現有邊 |
| ★★☆ 中 | 工具 21：`compare_courses_by_concepts` | 補充「課程比較」場景 | 新工具，集合運算 |
| ★☆☆ 低 | 工具 22：`get_cross_dept_concept_bridges` | 補充跨系查詢場景 | 新工具，集合運算 |

---

## 六、向量資料庫比較（ChromaDB vs Qdrant vs 其他）

### 現有 ChromaDB 資料量（實測）

| Collection | 筆數 | 維度 | 純向量 RAM |
|------------|------|------|----------|
| ncu_courses_ug | 3,119 | 3072 | ~37 MB |
| ncu_courses_grad | 957 | 3072 | ~11 MB |
| ncu_teachers | 1,009 | 3072 | ~12 MB |
| ncu_departments | 32 | 3072 | <1 MB |
| ncu_credit_programs | 42 | 3072 | <1 MB |
| **合計（現有）** | **5,159** | 3072 | **~60 MB** |
| + HNSW index 估算（×2.5） | — | — | **~151 MB** |
| + 未來圖節點 index（10,922 節點）| — | — | **~471 MB 合計** |

→ **Qdrant Cloud 免費版 1GB RAM 完全足夠**（~471 MB，含未來節點 index 後仍有 50% 餘裕）  
→ 若啟用 Qdrant **Scalar Quantization（int8）**：記憶體壓縮至 ~118 MB，更輕鬆

---

### 向量資料庫功能比較

| 功能 | **ChromaDB（現用）** | **Qdrant** | Weaviate | Milvus/Zilliz |
|------|:------------------:|:----------:|:--------:|:------------:|
| 底層語言 | Python | **Rust** | Go | C++ |
| 向量搜尋速度 | 普通 | **快**（HNSW C++ binding） | 快 | 最快 |
| Payload filter | 基本（等值、in） | **強**（範圍、巢狀、geo、全文） | GraphQL | 強 |
| Hybrid search（BM25 + dense） | ❌ | ✓ | ✓ | ✓ |
| Named Vectors（多向量空間/文件） | ❌ | ✓ | ✓ | ✓ |
| Scalar Quantization（省記憶體） | ❌ | ✓（int8，記憶體 ÷4） | ✓ | ✓ |
| 本地嵌入式（無 server） | ✓ | ✓（`QdrantClient(":memory:")` 或 local path） | ❌ | ❌ |
| Cloud 免費方案 | ChromaDB Cloud | **1 cluster, 1GB RAM** | Sandbox（14天） | Zilliz 免費（1GB） |
| Python SDK 易用度 | ★★★ | ★★★ | ★★ | ★★ |
| 遷移成本（從 ChromaDB） | — | **低**（API 相似） | 高（GraphQL） | 中 |

### Qdrant 對本系統的具體改善

**1. Payload filter 更強**

現在 `search_courses` 用 ChromaDB `where` 只能做等值比對：
```python
# ChromaDB 現況（只能等值）
collection.query(where={"dept": "資訊工程學系"})

# Qdrant 可做範圍、複合條件
client.search(
    collection_name="ncu_courses",
    query_filter=Filter(
        must=[
            FieldCondition(key="credits", range=Range(gte=2, lte=3)),
            FieldCondition(key="level", match=MatchValue(value="ugrad")),
        ]
    )
)
```

**2. Hybrid Search（現在完全沒有）**

Qdrant 可同時用關鍵字（BM25 sparse）+ 語意（dense）搜尋，對「演算法課程」這類查詢效果更好：
```python
client.query_points(
    collection_name="ncu_courses",
    prefetch=[
        Prefetch(query=sparse_vector, using="bm25"),   # 關鍵字
        Prefetch(query=dense_vector, using="dense"),    # 語意
    ],
    query=FusionQuery(fusion=Fusion.RRF),  # Reciprocal Rank Fusion 合併
)
```

**3. Named Vectors（未來擴充）**

可以為同一門課程存多個 embedding（課程名稱向量 / 課程內容向量 / 概念向量），查詢時指定用哪個：
```python
client.search(collection_name="ncu_courses", using="concept_vector", ...)
```

### Qdrant 遷移評估

| 項目 | 評估 |
|------|------|
| **遷移工作量** | 中：`chromadb` API → `qdrant-client` API，邏輯不變，語法換 |
| **本地開發** | `QdrantClient(path="./qdrant_data")` 或 `":memory:"`，不需 Docker |
| **雲端部署** | `QdrantClient(url="...", api_key="...")` 指向 Qdrant Cloud |
| **資料重建** | 需重跑 embedding（現有 3072 維 embedding 無法直接匯出轉入，要重新生成）|
| **主要風險** | 重跑 embedding 的 API 費用（~5159 筆 × dim 3072 = 約 $0.05-0.2 USD） |

### 建議：是否換 Qdrant？

**換的理由**（效益）：
- Hybrid search 可明顯改善「搜尋不到」的問題
- Payload filter 更強，部分現在要繞道圖的查詢可直接在向量 DB 做
- 1GB 免費雲端，部署更乾淨
- 記憶體壓縮（quantization）對圖節點 index 很有幫助

**不換的理由**（成本）：
- 需重跑所有 embedding（費用小但需時間）
- `retriever.py` 或 `build_vector_index.py` 要重寫
- 現有 ChromaDB 功能對基本需求已夠用

**結論**：如果同時要做「圖節點 index」（問題 1），建議直接用 Qdrant 建，一步到位；現有課程/教師 collection 可以之後再遷移。

---

## 七、套件組合方案（含改動大小 × 雲端部署評估）

> 背景調查結論（2026-04-25）：
> - **Kuzu DB**：已於 2025/10 宣布棄用，不建議採用
> - **Neo4j AuraDB 免費版**：不含 GDS plugin（PPR、Leiden 要付費）；自架 Community Edition 可裝免費 GDS plugin
> - **NetworkX Louvain**：大型圖要跑 21 分鐘，不可接受；igraph Leiden 只需秒級
> - **scipy sparse PPR**：比手寫 Python for loop 快 10-100 倍，改動最小

---

### 方案 A：最小改動（保留 NetworkX，只加速 PPR）

**組合**：NetworkX（現有）+ scipy sparse（PPR 加速）+ python-louvain（社群）+ ChromaDB 新 collection（向量節點查找）

| 需求 | 解法 | 工具 |
|------|------|------|
| 向量找節點 | 新建 `ncu_graph_nodes` ChromaDB collection | ChromaDB |
| Metadata filter | `filter_nodes()` generator（Python comprehension） | 現有 Python |
| PPR 加速 | 換用 `scipy.sparse` CSR 矩陣乘法，10-100x 加速 | `scipy` |
| 社群分群 | `community.best_partition(G)` | `python-louvain` |

**改動範圍**：
- `graph_service.py`：PPR 改用 sparse matrix，加 `filter_nodes` 函式
- 新增腳本：`scripts/rag/build_node_index.py`
- 新增 collection：`ncu_graph_nodes`

**雲端部署**：無新增 server，純 Python 套件，Render/Railway/fly.io 直接部署  
**缺點**：Louvain 品質不如 Leiden；sparse matrix PPR 仍在 Python 層，不如 C 底層快  
**適合**：時間緊迫，只想局部改善

---

### 方案 B：換 igraph（推薦，改動中等）★ 建議

**組合**：python-igraph（圖計算）+ ChromaDB（向量）+ FAISS 或 ChromaDB 新 collection（節點向量）

| 需求 | 解法 | 工具 |
|------|------|------|
| 向量找節點 | ChromaDB 新 collection 或 FAISS 記憶體 index | ChromaDB / faiss-cpu |
| Metadata filter | `g.vs.select(node_type_eq="Course", level_eq="ugrad")` 原生語法 | igraph |
| PPR（加權） | `g.personalized_pagerank(reset_vertices=seeds, weights=g.es["weight"])` 一行 C 底層 | igraph |
| 社群分群 | `igraph.Graph.community_leiden(weights=g.es["weight"])` 秒級 Leiden | igraph + leidenalg |

**從 NetworkX 遷移**：
```python
import igraph as ig
import pickle

G_nx = pickle.load(open("knowledge_graph.gpickle", "rb"))
G_ig = ig.Graph.from_networkx(G_nx)  # 一行轉換
G_ig.save("knowledge_graph.igraph")
```

**igraph vertex filter 範例**：
```python
# 找所有大學部課程
courses = g.vs.select(node_type_eq="Course", level_eq="ugrad")
# 找所有高相關 COVERS_FIELD 邊
high_rel = g.es.select(relation_eq="COVERS_FIELD", relevance_eq="high")
```

**改動範圍**：
- `graph_service.py`：全面改 igraph API（邏輯不變，API 不同）
- `build_graph.py`：輸出新增 igraph 格式（可同時保留 gpickle）
- 新增 `requirements.txt`：`python-igraph`, `leidenalg`, `faiss-cpu`

**雲端部署**：純 Python 套件，無需 server，部署難度與現況相同  
**缺點**：`graph_service.py` 需要完整重寫 API 呼叫（邏輯保留，語法換掉）；igraph vertex/edge 用 integer index，需維護 ID ↔ index 對應表  
**適合**：想要完整改善 PPR + filter + 社群，又不想架 DB server

---

### 方案 C：Neo4j 自架（最強，改動大）

**組合**：Neo4j Community Edition（自架）+ GDS plugin（免費，含 PPR / Leiden）+ 內建 vector index（Neo4j 5.x）

| 需求 | 解法 | 工具 |
|------|------|------|
| 向量找節點 | `CREATE VECTOR INDEX` + `db.index.vector.queryNodes()` | Neo4j 5.x 內建 |
| Metadata filter | Cypher `MATCH (c:Course {level: 'ugrad'}) WHERE c.dept = '...'` | Cypher |
| PPR | `gds.pageRank.stream({sourceNodes: [...]})` | GDS plugin |
| 社群分群 | `gds.leiden.stream({relationshipWeightProperty: 'weight'})` | GDS plugin |

**AuraDB vs 自架比較**：

| | AuraDB 免費 | AuraDB 付費 | 自架 Community |
|--|------------|------------|--------------|
| 節點上限 | 50K ✓ | 無限 | 無限 |
| GDS（PPR/Leiden） | ❌ | ✓（$65+/月） | ✓（免費 plugin） |
| 向量搜尋 | ✓ | ✓ | ✓ |
| 維護難度 | 零 | 零 | 需自管 server |
| 雲端 | 託管 | 託管 | Railway/Render/VPS |

**資料匯入**：
```python
# 從現有 graph 匯出後用 neo4j-admin import 或 py2neo 逐筆寫入
from neo4j import GraphDatabase
driver = GraphDatabase.driver("bolt://localhost:7687")
# 批次寫入節點/邊
```

**Railway 自架參考**：Railway 有 Neo4j template，一鍵部署 Community Edition + GDS plugin  
**改動範圍**：圖查詢邏輯完全重寫（Cypher 語言）、`graph_service.py` 改為 Neo4j driver 呼叫  
**缺點**：學習 Cypher 成本；服務需常駐（記憶體至少 1-2GB）；匯入需時  
**適合**：長期維護、需要完整 OLAP 圖查詢、未來可能擴大資料規模

---

### 方案 D：Hybrid（igraph + DuckDB，兼顧彈性）

**組合**：igraph（圖遍歷 + PPR）+ DuckDB（節點屬性 SQL 查詢）+ FAISS（向量）

| 需求 | 解法 |
|------|------|
| 向量找節點 | FAISS in-memory index（啟動時預建，約 3-5 秒） |
| Metadata filter | DuckDB SQL：`SELECT nid FROM nodes WHERE node_type='Course' AND level='ugrad'` |
| PPR | igraph weighted PPR |
| 社群分群 | igraph Leiden |

**DuckDB 節點索引建立**：
```python
import duckdb
con = duckdb.connect(":memory:")  # 純記憶體，不落磁碟
# 從圖匯出節點屬性 DataFrame
nodes_df = pd.DataFrame([{"nid": n, **G.nodes[n]} for n in G.nodes()])
con.execute("CREATE TABLE nodes AS SELECT * FROM nodes_df")
# 之後可用 SQL 查詢
result = con.execute("SELECT nid FROM nodes WHERE node_type='Course' AND level='ugrad'").fetchall()
```

**雲端部署**：純記憶體，無需額外服務  
**缺點**：要同時維護 igraph 圖和 DuckDB index（兩份資料需同步）  
**適合**：想要 SQL 風格查詢又不想架 Neo4j server

---

### 方案比較總表

| | 方案 A（最小改） | 方案 B（igraph）★ | 方案 C（Neo4j） | 方案 D（Hybrid） |
|--|:-:|:-:|:-:|:-:|
| 向量找節點 | ChromaDB | ChromaDB/FAISS | 內建 | FAISS |
| Metadata filter | Python generator | igraph 原生 | Cypher | DuckDB SQL |
| PPR 速度 | ★★☆（scipy） | ★★★（C底層） | ★★★（GDS） | ★★★（C底層） |
| Louvain/Leiden | Louvain（慢） | Leiden（快） | Leiden（GDS） | Leiden（快） |
| 改動幅度 | 小 | 中 | 大 | 中 |
| 需要 server | ❌ | ❌ | ✓ | ❌ |
| 雲端部署難度 | 低 | 低 | 中 | 低 |
| 長期維護性 | 普通 | 好 | 最好 | 好 |

---

### 套件視覺化推薦

| 需求 | 推薦 | 說明 |
|------|------|------|
| 互動式 Web 視覺化 | `pyvis` | 輸出 HTML，可在 notebook 或瀏覽器開啟 |
| 靜態論文圖 | `matplotlib` + `networkx.draw` | 現有 NetworkX 即可 |
| 離線大圖分析 | Gephi（獨立軟體） | 開啟 graphml/gexf 格式，支援 force-directed layout |
| 社群著色 | `igraph` + `plotly` | 社群分群後按 community ID 著色 |
