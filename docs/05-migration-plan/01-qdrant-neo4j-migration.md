# 圖 + 向量 DB 遷移規劃

> 建立時間：2026-04-25  
> 現況：ChromaDB（本地）+ NetworkX（記憶體）  
> 部署架構：Firebase Hosting（前端）+ Render Web Service（後端）+ Cloudinary（PDF）

---

## 零、你的部署架構與 Neo4j 能不能放進去？

**現有架構：**
```
Firebase Hosting   → 只放前端靜態檔（HTML/JS/CSS），不能跑任何 server 程式
Render             → 後端 FastAPI，data/ 資料夨跟 repo 一起部署
Cloudinary         → 只放 PDF/圖片等媒體檔
```

**Neo4j 能放在哪？**

| 平台 | 能不能放 Neo4j？ | 原因 |
|------|:--------------:|------|
| Firebase Hosting | ❌ | 只能放靜態前端檔案，不能跑 server 程式 |
| Firebase Firestore | ❌ | 是文件型 DB（像 MongoDB），不是圖 DB，無法裝 Neo4j |
| Cloudinary | ❌ | 只能放媒體檔（圖片/PDF），不是 DB |
| Render（免費 Web Service） | ❌ | 免費方案只有 **512MB RAM**，Neo4j 最少需要 **1GB** |
| Render（Starter $7/月） | ✓ | 1GB RAM，可跑 Neo4j Community + GDS plugin |
| Neo4j AuraDB（獨立雲端） | ✓（免費，但**無 GDS**） | 200K 節點，無 PPR/Leiden |
| igraph（內嵌在 Render 後端） | ✓ **免費** | 純 Python 套件，跟後端一起跑，不需要額外 server |

**結論**：Neo4j 沒辦法「隨後端一起部署」像現在的 JSON 資料那樣。它是一個獨立的 server 程式，需要單獨的空間。**免費且最省事的圖計算選項是 igraph**——它就是一個 Python 套件，跟現在的 NetworkX 一樣內嵌在後端裡，不需要任何額外服務。

---

## 一、先讀這個：重要限制確認

在規劃之前，有幾個調查結果必須先確認清楚：

| 問題 | 結果 |
|------|------|
| Neo4j AuraDB 免費版節點上限 | 200,000 節點 / 400,000 邊（你的資料 14K/30K，✓ 合格） |
| **Neo4j AuraDB 免費版有 GDS（PPR、Leiden）嗎？** | **❌ 完全沒有**，GDS 只有付費版（AuraDS）才有 |
| Qdrant Cloud 免費版容量 | 1GB RAM + 4GB 磁碟，含未來圖節點 index 預估 471MB，✓ 夠用 |
| Qdrant Cloud 閒置政策 | **7 天不使用自動暫停，28 天刪除資料**（學術專案風險高） |
| Neo4j AuraDB 閒置政策 | 72 小時不使用暫停，90 天刪除 |
| Qdrant Cloud 查詢延遲 | p50: 30ms，p99: 38ms（新加坡 → 台灣約再加 30-50ms） |

**最重要的結論**：  
→ 如果換成 Neo4j AuraDB **免費版**，PPR 和 Leiden 社群分群都**無法使用**，需要自己在 Python 層實作（等於還是要用 igraph 或 scipy）。  
→ 真正的 GDS（免費）只有**自架 Neo4j Community Edition + 安裝 GDS plugin**。

---

## 二、架構方案比較（三選一）

### 方案 I：Qdrant Cloud + Neo4j AuraDB Free（全雲端 × 免費）

```
使用者
  → Backend（Render / Railway）
      ├── Qdrant Cloud（US-East / Singapore）     ← 向量搜尋
      └── Neo4j AuraDB Free（US-East）            ← 圖遍歷（無 GDS）
              ↓ PPR / Leiden 需要
      igraph（backend 記憶體，從 Neo4j 拉圖做計算）
```

| 項目 | 評估 |
|------|------|
| 費用 | **完全免費** |
| GDS（PPR、Leiden） | ❌ 需自己在 Python 用 igraph 計算（還是要裝 igraph） |
| Cypher 查詢 | ✓ 可以，filter / 多跳查詢語法清楚 |
| 延遲（同雲端區域） | Qdrant ~30-50ms，Neo4j ~30-80ms，**每次工具呼叫多 60-130ms** |
| 閒置風險 | ⚠️ 兩個服務都有閒置暫停政策 |
| 遷移工作量 | 大（要重寫 graph_service.py + retriever.py） |

**適合**：想要 Cypher 語法、不在意 GDS 缺失、接受稍高延遲

---

### 方案 II：Qdrant Cloud + Neo4j Community 自架（Render 免費 Docker）

```
使用者
  → Backend（Render Web Service）
      ├── Qdrant Cloud（US-East）                 ← 向量搜尋
      └── Neo4j Community（Render Docker Service）← 圖遍歷 + GDS plugin
              ↓ GDS 可用
      PPR、Leiden 直接在 Neo4j 內執行
```

| 項目 | 評估 |
|------|------|
| 費用 | Qdrant 免費；Render Docker 免費（限 750 hr/月，1 個 container） |
| GDS（PPR、Leiden） | ✓ 自架 Community Edition 可裝 GDS plugin |
| Neo4j 記憶體需求 | 1GB+ RAM → Render 免費方案只有 512MB RAM → **記憶體可能不夠** |
| 延遲（同 Render 區域） | Qdrant Cloud（US-East）→ Render（US-East）約 5-20ms 低延遲 |
| 閒置問題 | Render 免費服務 15 分鐘無流量會 spin down（冷啟動約 30 秒） |
| 遷移工作量 | 大 |

**問題**：Render 免費 Docker 只有 **512MB RAM**，Neo4j 最少需要 **1GB**，記憶體不足會 OOM。需要升級到 Render Starter（$7/月）。

**適合**：願意付小額費用（$7/月）換完整 GDS 功能

---

### 方案 III：Qdrant Cloud + igraph（backend 內嵌，無 Neo4j）★ 建議

```
使用者
  → Backend（任何雲端或本地）
      ├── Qdrant Cloud（US-East / Singapore）     ← 向量搜尋
      └── igraph（backend 記憶體，.igraph 檔案）  ← 圖遍歷 + PPR + Leiden
```

| 項目 | 評估 |
|------|------|
| 費用 | **完全免費** |
| GDS（PPR、Leiden） | ✓ igraph 內建，C 底層，秒級 |
| 向量搜尋 | ✓ Qdrant Cloud，hybrid search、強 filter |
| 延遲 | 只有 Qdrant 加 30-50ms，igraph 本地無網路延遲 |
| 閒置風險 | 只有 Qdrant Cloud 有（7 天暫停），igraph 是檔案無此問題 |
| 遷移工作量 | 中（graph_service.py + retriever.py） |

**適合**：想要 Qdrant 的 hybrid search + 強 filter，同時保留 PPR/Leiden 完整功能，不需要 Cypher 查詢語法

---

### 方案比較總表

| | 方案 I（Qdrant + AuraDB） | 方案 II（Qdrant + 自架 Neo4j） | 方案 III（Qdrant + igraph）★ |
|--|:-:|:-:|:-:|
| 費用 | 免費 | $0-7/月 | **免費** |
| Cypher 查詢 | ✓ | ✓ | ❌（Python API） |
| PPR（PageRank） | ⚠️ 需自建 | ✓ GDS | ✓ igraph 內建 |
| Leiden 社群分群 | ⚠️ 需自建 | ✓ GDS | ✓ igraph 內建 |
| Hybrid Search | ✓ | ✓ | ✓ |
| 節點向量搜尋 | ✓ | ✓ | ✓ |
| 閒置暫停風險 | 高（兩個服務） | 中（Qdrant + Render） | 低（只 Qdrant） |
| 延遲 | +60-130ms | +30-50ms | +30-50ms |
| 遷移工作量 | 大 | 大 | 中 |
| 推薦度 | ★★☆ | ★★★ | ★★★★ |

---

## 三、延遲（Latency）深度分析

### 現況延遲（全本地）

```
ChromaDB 查詢：<1ms（本地磁碟讀取）
NetworkX PPR：5-50ms（記憶體計算）
總工具延遲：~10-100ms
```

### 換雲端後的延遲

**最佳狀況（Backend 和 DB 在同一雲端區域）**：
```
Qdrant Cloud US-East → Backend Render US-East：~5-15ms
Neo4j AuraDB US-East → Backend Render US-East：~5-20ms
```

**最差狀況（Backend 在台灣本地，DB 在海外雲端）**：
```
台灣 → Qdrant Cloud Singapore：~30-50ms
台灣 → Qdrant Cloud US-East：~150-200ms
台灣 → Neo4j AuraDB US-East：~150-250ms
```

### 實際 API 響應時間影響

一次對話中 LLM Agent 可能呼叫 2-4 個工具，每個工具可能做 1-3 次 DB 查詢：

| 場景 | 現況 | 雲端 DB（同區域） | 雲端 DB（跨洲） |
|------|------|-----------------|---------------|
| 單工具呼叫（1 次查詢） | ~10ms | ~15-30ms | ~200-300ms |
| 單輪對話（3 工具 × 2 查詢） | ~60ms | ~90-180ms | ~1200-1800ms |
| **對用戶的感受** | 感覺不到 | **幾乎感覺不到** | **明顯慢 1-2 秒** |

**結論**：
- 如果 backend 和 DB **部署在同一雲端區域**（如全部 Render US-East）→ 延遲增加約 20-50ms，**不明顯**
- 如果 backend 在本地台灣、DB 在海外 → 每輪對話額外 **1-2 秒**，體驗變差
- **解法**：所有服務統一部署同一雲端區域，不要混搭本地和雲端

---

## 四、免費雲端部署方式（完整說明）

### Qdrant Cloud 免費部署

1. 前往 [cloud.qdrant.io](https://cloud.qdrant.io) 註冊
2. 建立 1 個 Free Cluster（選 AWS US-East 或 GCP Asia-Southeast）
3. 取得 API key 和 cluster URL
4. 設定 `.env`：
   ```
   QDRANT_URL=https://xxxx.aws.cloud.qdrant.io
   QDRANT_API_KEY=your-api-key
   ```
5. **防閒置**：設定 cron job 每 6 天 ping 一次（否則 7 天後暫停）

```python
# 本地開發：不需 API key
client = QdrantClient(path="./qdrant_data")

# 雲端：
client = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))
```

### Neo4j AuraDB 免費部署

1. 前往 [console.neo4j.io](https://console.neo4j.io) 註冊
2. 建立 Free Instance（US-East 或 EU-West）
3. 取得 Connection URI、Username、Password
4. 設定 `.env`：
   ```
   NEO4J_URI=neo4j+s://xxxx.databases.neo4j.io
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=your-password
   ```
5. **防閒置**：設定 cron job 每 48 小時執行一次查詢（否則 72 小時暫停）
6. ⚠️ **注意**：GDS 不可用，PPR / Leiden 需另行在 Python 實作

```python
from neo4j import GraphDatabase
driver = GraphDatabase.driver(os.getenv("NEO4J_URI"), 
                               auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")))
```

### 防閒置 Cron Job（兩個服務都需要）

```python
# scripts/keep_alive.py
import schedule, time, os
from qdrant_client import QdrantClient
from neo4j import GraphDatabase

def ping_qdrant():
    client = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))
    client.get_collections()
    print("Qdrant: alive")

def ping_neo4j():
    driver = GraphDatabase.driver(os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")))
    with driver.session() as s:
        s.run("RETURN 1")
    print("Neo4j: alive")

schedule.every(2).days.do(ping_qdrant)
schedule.every(2).days.do(ping_neo4j)

while True:
    schedule.run_pending()
    time.sleep(3600)
```

---

## 五、遷移步驟規劃

### Phase 1：Qdrant 遷移（1-2 天）

**Step 1-1**：安裝與設定
```bash
pip install qdrant-client
```

**Step 1-2**：建立新的 `scripts/rag/build_qdrant_index.py`
- 讀取現有課程/教師 JSON 資料
- 重新呼叫 embedding API（或用現有 ChromaDB 的 embedding 匯出）
- 建立 Qdrant collections：
  - `ncu_courses`（合併現有 ug + grad）
  - `ncu_teachers`
  - `ncu_departments`
  - `ncu_credit_programs`
  - `ncu_graph_nodes`（新，Concept + Technology + Field 節點）

**Step 1-3**：更新 `backend/app/services/retriever.py`
- 將 `chromadb.PersistentClient` → `QdrantClient`
- 更新 search API 呼叫語法

**Step 1-4**：測試所有工具確認回傳結果相同

### Phase 2：Neo4j 遷移（2-3 天）

> ⚠️ 決定前需確認：用 AuraDB Free（無 GDS）還是自架（有 GDS）？

**Step 2-1**：資料匯入
```python
# scripts/graph/export_to_neo4j.py
# 從現有 knowledge_graph.gpickle 讀取，批次寫入 Neo4j
```

建立 Cypher 節點：
```cypher
CREATE (:Course {code: $code, name: $name, credits: $credits, dept: $dept, level: $level})
CREATE (:Concept {name: $name})
CREATE (:Instructor {name: $name, dept: $dept, rank: $rank})
```

建立關係：
```cypher
MATCH (c:Course {code: $code}), (concept:Concept {name: $concept})
CREATE (c)-[:COVERS {source: 'nlp'}]->(concept)
```

建立索引（加速查詢）：
```cypher
CREATE INDEX course_code IF NOT EXISTS FOR (c:Course) ON (c.code)
CREATE INDEX concept_name IF NOT EXISTS FOR (c:Concept) ON (c.name)
CREATE FULLTEXT INDEX course_fulltext IF NOT EXISTS FOR (c:Course) ON EACH [c.name, c.dept]
```

**Step 2-2**：更新 `backend/app/services/graph_service.py`
- 將 `pickle.load(graph)` → Neo4j Cypher 查詢
- PPR：igraph 從 Neo4j dump 計算（或 scipy sparse）
- Filter：Cypher WHERE 條件

**Step 2-3**：測試所有圖工具

### Phase 3：整合與測試（1 天）

- E2E 測試：對話流程從頭到尾
- 延遲測量：記錄每個工具的回應時間
- 壓力測試：同時多個查詢

---

## 六、各架構 Embedding 費用估算

重跑 embedding 是遷移時唯一的費用（若使用 OpenAI text-embedding-3-large）：

| 項目 | 筆數 | Token 估算 | 費用（$0.13/1M tokens） |
|------|------|-----------|----------------------|
| ncu_courses（ug + grad） | 4,076 | ~2M tokens | ~$0.26 |
| ncu_teachers | 1,009 | ~0.5M tokens | ~$0.07 |
| ncu_departments | 32 | ~0.05M tokens | <$0.01 |
| ncu_credit_programs | 42 | ~0.05M tokens | <$0.01 |
| **圖節點 index（新增）** | 10,922 | ~1M tokens | ~$0.13 |
| **合計** | — | ~3.6M tokens | **~$0.50 USD** |

→ 總花費約 **台幣 16 元**，可接受。

---

## 七、建議決策

### 如果目標是「最省錢 + 功能最完整」

**選方案 III（Qdrant Cloud + igraph）**：
- 完全免費
- PPR、Leiden 完整可用（igraph C 底層，比 GDS 更快啟動）
- Hybrid search 可用
- 不需要學 Cypher
- 只加一個雲端依賴（Qdrant）

### 如果目標是「最有技術深度（論文/展示用）」

**選方案 II（Qdrant Cloud + 自架 Neo4j）**：
- Cypher 語法可在 md 和論文中展示
- GDS 完整功能
- 需要付 $7/月（Render Starter）或找其他有 1GB RAM 的免費雲端
- 遷移工作量最大

### 如果只想先試試 Qdrant

可以先只做 Phase 1（Qdrant），Neo4j 之後再決定：
- 先換向量層（Qdrant）
- 圖的部分先改成 igraph
- 之後視需求再考慮要不要加 Neo4j

---

## 八、igraph vs NetworkX 完整比較

兩者都是「圖計算套件」，功能類似但實作完全不同。

### 核心差異

| | **NetworkX**（現用） | **igraph** |
|--|:------------------:|:---------:|
| 底層語言 | 純 Python | **C**（Python 只是 binding） |
| PPR 速度（14K 節點） | ~50-200ms（手寫 loop） | **~2-10ms**（C 底層，快 20-50x） |
| Leiden 社群分群 | 不內建；`python-louvain` 要 2-21 分鐘 | **內建，秒級**（C 實作） |
| Weighted PageRank | 需手寫 | **一行 API**（`g.personalized_pagerank(weights=...)`） |
| Metadata filter | 需手寫 for loop | **原生語法**（`g.vs.select(node_type_eq="Course")`） |
| API 易用度 | ★★★（文件多，社群大） | ★★（需學新 API，vertex 用 int index） |
| 遷移難度（從 NetworkX） | — | 中：`ig.Graph.from_networkx(G)` 一行轉換，但 API 語法不同 |
| 套件大小 | 小 | 小（有 C 依賴，安裝略慢） |
| `pip install` | `pip install networkx` | `pip install igraph leidenalg` |

### 速度實測數字（來自 benchmark）

| 操作 | NetworkX | igraph | 差距 |
|------|----------|--------|------|
| PageRank（100K 節點） | ~10 秒 | ~0.3 秒 | **33x** |
| Louvain 社群（100K 節點） | 21 分鐘 | ~3 秒 | **420x** |
| BFS 遍歷（14K 節點） | ~5ms | ~0.1ms | **50x** |
| 圖載入（from file） | 相近 | 相近 | — |

> 你的圖只有 14K 節點，NetworkX 不會慢到讓使用者感覺到——**除了 PPR 的手寫 Python for loop**。這才是現在真正的瓶頸。

### igraph 的主要缺點

1. **Vertex 用整數 index 而非字串 ID**：NetworkX 可以用 `G.nodes["course::CS1001"]`，igraph 要維護一個 `id_to_index` dict 對應表
2. **API 文件較少**：Stack Overflow 上的範例比 NetworkX 少很多
3. **部分演算法 NetworkX 有但 igraph 沒有**：如果需要很特殊的圖演算法，NetworkX 較完整

### 什麼時候換 igraph 最值得？

| 情況 | 建議 |
|------|------|
| 只是加速 PPR | 換 igraph 或改用 `scipy.sparse`（後者改動更小） |
| 要加 Leiden 社群分群 | **換 igraph**，NetworkX 的 Louvain 太慢 |
| 要用 weighted PPR | **換 igraph**，一行搞定 |
| 只是加 SIMILAR_TO 邊查詢 | 不需要換，NetworkX 就夠 |

---

## 九、Neo4j 的真正優勢在哪？（重新評估）

根據你的部署限制（Firebase + Render 免費 + Cloudinary），重新評估 Neo4j 的實際價值：

| Neo4j 的優勢 | 對你的系統有用嗎？ |
|-------------|:---------------:|
| Cypher 查詢語法（可讀性高） | △ 有用，但不是必要 |
| 雲端持久化（不用載 gpickle） | △ Render 重啟時省幾秒，影響小 |
| 瀏覽器內建視覺化工具 | ✓ 開發時方便看圖 |
| GDS：PPR、Leiden | **❌ 免費版沒有**，等於沒有 |
| 向量節點搜尋 | ❌ 免費版沒有 vector index |
| Metadata filter（Cypher WHERE） | ✓ 比 Python for loop 漂亮 |
| 免費部署（你的架構下） | ❌ 不能放 Firebase/Cloudinary，Render 免費版記憶體不夠 |

**結論**：在你的架構限制下，Neo4j **免費版幾乎沒有勝過 igraph 的地方**。Cypher 語法漂亮，但要額外付費或管理一個 server 程式。

---

## 十、最終建議（針對你的實際架構）

**最適合你的組合：Qdrant Cloud + igraph**

```
Firebase Hosting     → 前端（不變）
Render Web Service   → 後端 FastAPI（不變）
  ├── igraph         → 圖計算（取代 NetworkX，套件安裝，不需額外 server）
  └── .igraph 檔案   → 從 gpickle 轉換，隨後端部署（跟現在 JSON 一樣）
Qdrant Cloud（免費） → 向量搜尋（取代 ChromaDB）
Cloudinary           → PDF（不變）
```

**為什麼不需要 Neo4j**：
- igraph 完全覆蓋 Neo4j GDS 的功能（PPR、Leiden、filter）
- igraph 是 Python 套件，跟現有後端一起跑，不需額外服務
- Neo4j 免費版的優點（Cypher 語法）對功能沒有實質幫助
- Neo4j 無法在你現有的免費架構內部署

**為什麼換 Qdrant**：
- Hybrid search（BM25 + 語意）改善搜尋品質
- Payload filter 更強（數值範圍、複合條件）
- 可以建圖節點向量 index（解決字串比對找不到概念的問題）
- 免費版 1GB RAM 對你的資料量（~471MB 含節點 index）夠用

**遷移順序建議**：
1. NetworkX → igraph（先做，不影響對外服務，純後端改動）
2. ChromaDB → Qdrant（之後做，需重跑 embedding，約 $0.5 USD）
3. 建立 `ncu_graph_nodes` Qdrant collection（解決向量找節點問題）

---

## 十一、目前未解決的問題

| 問題 | 狀態 |
|------|------|
| Qdrant 7 天閒置刪除 → 如何防止學術 demo 被刪？ | 需設定 keep-alive cron job 或用本地模式開發 |
| igraph vertex int index → ID 對應表要怎麼設計？ | 需在 graph_service.py 啟動時建 `{node_id: igraph_index}` dict |
| embedding 重跑的時間成本 | 約 1-2 小時（含 API 呼叫速率限制），費用 ~$0.5 USD |
| Render 免費版記憶體 512MB → igraph + gpickle 夠嗎？ | igraph 載入 14K 節點約 50-100MB，應該夠用，需實測 |
