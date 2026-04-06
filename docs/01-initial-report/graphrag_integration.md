# 知識圖譜 × RAG 系統整合設計

## 一、兩者的關聯性

### 1.1 傳統 RAG 的盲點

單純的向量 RAG 有幾個根本限制：

```
用戶問：「資工系大一修完計算機概論後，下一步應該上什麼？」

向量 RAG 做的事：
  → 把問題轉成向量
  → 找相似的課程描述文字
  → 把前 K 筆塞給 LLM 生答案

問題：
  ✗ 不知道「計算機概論 → 下一門」的先後關係
  ✗ 不知道「大一修完才能修大二」的年級限制鏈
  ✗ 沒辦法推理「跨三門課的學習路徑」
  ✗ 多跳查詢（A連B、B連C，問A和C的關係）完全不行
```

### 1.2 知識圖譜補的正好是這些缺口

```
Graph RAG 做的事：
  → 理解問題意圖（需要「路徑查詢」）
  → 在圖上走：計算機概論 → SERIES_NEXT → 計算機概論Ⅱ
                          → PREREQUISITE_OF → 資料結構
  → 把「路徑上的節點」+ 向量找到的「語意相關文字」一起給 LLM
  → 生成有結構的答案

  ✓ 能推理先後關係
  ✓ 能找 2-3 跳的間接關聯
  ✓ 能回答「哪條路徑最短」
```

### 1.3 對應到 rag_system_design.md 的每個元件

```
rag_system_design.md                   知識圖譜的角色
─────────────────────────────────────────────────────
Orchestrator Agent          ←→    判斷要用圖查詢還是向量查詢
Course Expert Agent         ←→    圖查詢的主要執行者
Planning Helper Agent       ←→    學習路徑規劃全靠圖遍歷
Career Advisor Agent        ←→    圖上的「技能→課程→領域」多跳查詢

Tool: search_courses()      →     向量搜尋（語意匹配）
Tool: find_similar()        →     圖的鄰居節點（結構相似）
Tool: check_conflict()      →     圖屬性查詢（時間欄位）
Tool: get_prerequisites()   →     圖路徑查詢（PREREQUISITE 邊）  ← 新增
Tool: find_learning_path()  →     圖最短路徑算法              ← 新增
Tool: get_department_map()  →     子圖萃取                    ← 新增

HybridRetriever             →     向量 + BM25 + 圖查詢 三合一
Knowledge Graph（設計圖中）  →     就是這份文件的主角
```

### 1.4 整合後的查詢流程

```
                    用戶問題
                       │
              ┌────────▼────────┐
              │  Orchestrator   │
              │  判斷查詢類型    │
              └────────┬────────┘
                       │
         ┌─────────────┼──────────────┐
         ▼             ▼              ▼
    「語意類」      「關係類」       「規劃類」
  （課程內容）    （先修/相關）    （路徑規劃）
         │             │              │
    向量搜尋        圖查詢          圖遍歷
    Qdrant         Neo4j         Shortest Path
         │             │              │
         └─────────────┴──────────────┘
                       │
               Context 組合（Fusion）
                       │
                  LLM 生成回答
```

---

## 二、Latency 分析

### 2.1 各步驟耗時拆解

#### 純向量 RAG（目前設計）

```
步驟                              耗時（估計）
────────────────────────────────────────────
Query Embedding                   50-100ms
Vector Search (Qdrant)            20-50ms
Reranking (Cross-Encoder)        100-300ms
LLM Generation (GPT-4)          1000-3000ms
─────────────────────────────────────────────
總計                            1.2s - 3.5s
```

#### Graph RAG（整合後）

```
步驟                              耗時（估計）
────────────────────────────────────────────
Query Embedding                   50-100ms
意圖分類（小模型）                  50-100ms   ← 新增
Vector Search (Qdrant)            20-50ms
Graph Query (Neo4j)               10-50ms    ← 新增，但很快
Context Fusion                    10-20ms    ← 新增
LLM Generation (GPT-4)          1000-3000ms
─────────────────────────────────────────────
總計                            1.1s - 3.3s  ← 幾乎沒差

原因：圖查詢本身非常快（10-50ms），
      LLM 才是真正的瓶頸（占 80% 時間）
```

### 2.2 三種查詢情境的 Latency 比較

| 查詢類型 | 純 RAG | Graph RAG | 差異 | 原因 |
|---------|-------|-----------|------|------|
| 單純課程查詢<br>「計算機概論學什麼？」 | 1.5s | 1.6s | **+0.1s** | 圖查詢很快 |
| 關係查詢<br>「資工系必修有哪些？」 | 2.0s | 1.8s | **-0.2s** | 圖查詢比向量更精準，LLM 輸入較少 |
| 多跳查詢<br>「從計概到 AI 的路徑？」 | ❌ 答不好 | 2.5s | 質的提升 | 只有圖能做 |
| 複雜規劃<br>「幫我規劃大一課表」 | ❌ 答不了 | 3.5s | 質的提升 | 需要圖遍歷 |

### 2.3 真正影響 Latency 的是這些

```
🔴 高影響：
  - LLM 模型大小（GPT-4 vs GPT-3.5 差 2-3 倍）
  - LLM 生成 token 數量
  - 同時呼叫多個 Agent（串行 vs 並行）

🟡 中影響：
  - Reranking（+100-300ms，但可選擇性關閉）
  - Cold start（第一次 embedding model 載入）

🟢 低影響：
  - 圖查詢（10-50ms，基本可忽略）
  - 向量搜尋（20-50ms）
  - 快取命中時趨近 0ms
```

### 2.4 Latency 優化策略

```
策略 1：快取（最有效）
├── 查詢快取：相同問題直接回快取結果（TTL: 1小時）
├── Embedding 快取：相同文字不重複計算
└── 圖查詢快取：熱門路徑預先算好存 Redis

策略 2：並行執行
├── 向量搜尋 + 圖查詢 同時跑，不要串行
└── Multi-Agent 可並行的部分同時執行

策略 3：分層模型
├── 簡單問題 → GPT-3.5 Turbo（~0.5s）
├── 複雜問題 → GPT-4（~2-3s）
└── 意圖分類用最小的模型

策略 4：Streaming
└── 用 streaming 讓用戶感覺「有在回答」
    實際 latency 不變，但感知 latency 大幅降低

策略 5：預熱
└── 常見問題（大一必修、熱門系所）預先計算好
```

---

## 三、部署建議

### 3.1 三種部署規模

---

#### 🟢 方案 A：單機輕量（Demo / 課程專題）

```
適合：課堂展示、小型 POC、幾十人同時使用

硬體需求：
  - 一台 VPS / 個人電腦
  - RAM: 8GB+
  - 不需要 GPU

架構：
┌─────────────────────────────────────┐
│           單台機器                   │
│                                     │
│  FastAPI ──→ LangChain              │
│                 │                   │
│          ┌──────┼──────┐            │
│          ▼      ▼      ▼            │
│      ChromaDB NetworkX Redis        │
│      (向量)   (圖譜)  (快取)         │
│                                     │
│  LLM: OpenAI API（外部呼叫）         │
└─────────────────────────────────────┘

成本：~$0（自己電腦） + OpenAI API 費用
啟動時間：30 分鐘
```

```bash
# 啟動方式
pip install fastapi chromadb networkx openai redis
python main.py
```

---

#### 🟡 方案 B：Docker Compose（小型生產）

```
適合：學校內部系統、幾百人使用

架構：
┌─────────────────────────────────────────┐
│            Docker Compose               │
│                                         │
│  ┌──────────┐  ┌──────────┐            │
│  │  FastAPI  │  │  Celery  │            │
│  │  (API)   │  │ (背景任務)│            │
│  └────┬─────┘  └────┬─────┘            │
│       │              │                  │
│  ┌────▼──────────────▼────┐             │
│  │         Redis          │             │
│  │    (快取 + 任務佇列)    │             │
│  └────────────────────────┘             │
│                                         │
│  ┌──────────┐  ┌──────────┐            │
│  │  Qdrant  │  │  Neo4j   │            │
│  │  (向量)  │  │  (圖譜)  │            │
│  └──────────┘  └──────────┘            │
│                                         │
│  ┌──────────┐                          │
│  │ Postgres │ (用戶資料、對話記錄)        │
│  └──────────┘                          │
└─────────────────────────────────────────┘

LLM: OpenAI API 或 Azure OpenAI
```

```yaml
# docker-compose.yml 結構
services:
  api:        # FastAPI
  worker:     # Celery
  qdrant:     # 向量資料庫
  neo4j:      # 知識圖譜
  redis:      # 快取
  postgres:   # 關聯式資料庫
```

```
成本估算（月）：
  VPS (4 core, 16GB RAM): ~$40-80
  OpenAI API: ~$50-200（視使用量）
  合計: ~$90-280/月
```

---

#### 🔴 方案 C：雲端微服務（大規模生產）

```
適合：全校使用、對外開放服務

┌────────────────────────────────────────────────────┐
│                   Cloud（GCP / AWS / Azure）         │
│                                                    │
│  ┌─────────────┐                                   │
│  │  CDN / WAF  │                                   │
│  └──────┬──────┘                                   │
│         │                                          │
│  ┌──────▼──────┐                                   │
│  │ Load Balancer│                                  │
│  └──────┬──────┘                                   │
│         │                                          │
│  ┌──────▼──────────────────┐                       │
│  │   API Gateway (Nginx)   │                       │
│  └──────┬──────────────────┘                       │
│         │                                          │
│  ┌──────▼──┐  ┌──────────┐  ┌──────────┐          │
│  │ API Pod │  │Agent Pod │  │Worker Pod│          │
│  │ x3      │  │ x2       │  │ x2       │          │
│  └─────────┘  └──────────┘  └──────────┘          │
│                                                    │
│  ┌──────────────────────────────────┐              │
│  │          Managed Services         │              │
│  │  Qdrant Cloud  Neo4j AuraDB      │              │
│  │  Redis Cloud   Cloud SQL         │              │
│  └──────────────────────────────────┘              │
│                                                    │
│  ┌──────────────────────────────────┐              │
│  │          Monitoring               │              │
│  │  LangSmith  Prometheus  Grafana  │              │
│  └──────────────────────────────────┘              │
└────────────────────────────────────────────────────┘

成本估算（月）：
  Compute (GKE): ~$200-400
  Qdrant Cloud: ~$25-100
  Neo4j AuraDB: ~$65-200
  Redis Cloud: ~$30
  Azure OpenAI: ~$200-500
  合計: ~$520-1230/月
```

### 3.2 圖譜資料庫部署細節

#### 開發環境：NetworkX（記憶體內）

```python
# 優點：零設定，直接 pip install
# 缺點：重啟後消失，不能持久化
import networkx as nx
G = nx.DiGraph()
```

#### 過渡環境：Neo4j Community（本機 Docker）

```bash
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  -v $PWD/neo4j_data:/data \
  neo4j:5.15-community

# 免費，有視覺化介面 http://localhost:7474
# 資料持久化到本機
```

#### 生產環境：Neo4j AuraDB Free 或 Self-hosted

```
Neo4j AuraDB Free:
  - 50k 節點，175k 關係（夠用！我們只有 3316 門課）
  - 免費
  - 雲端托管，不用維護

自架 Neo4j Enterprise：
  - 有叢集功能
  - 月費 $$$
  - 適合超大規模
```

### 3.3 推薦的部署路徑

```
現在（開發）
    │
    ▼
方案 A：本機 / Colab
  NetworkX + ChromaDB + OpenAI API
  目標：驗證圖譜設計，跑通流程
    │
    ▼ 確認可行後
方案 B：單台 VPS + Docker Compose
  Neo4j + Qdrant + Redis + FastAPI
  目標：給老師/同學 demo
    │
    ▼ 如果要對外開放
方案 C：雲端（視預算決定規模）
```

### 3.4 各元件的可替換方案

```
元件          推薦（免費優先）        備選（付費）
─────────────────────────────────────────────────
知識圖譜      NetworkX（開發）         Neo4j AuraDB
              Neo4j Community          Amazon Neptune
              Kuzu（嵌入式，超快）

向量資料庫    ChromaDB（開發）         Qdrant Cloud
              Qdrant（本機 Docker）    Pinecone

快取          記憶體 dict（開發）      Redis Cloud
              Redis（本機 Docker）

LLM           OpenAI API               Azure OpenAI
              Ollama + Llama3          Google Vertex AI
              （本地，免 API 費）

監控          LangSmith Free           Langfuse（自架）
              （1000 trace/月）
```

---

## 四、最終建議

```
對這個專題的建議：
┌────────────────────────────────────────────────────┐
│                                                    │
│  1. Latency 不是問題                               │
│     圖查詢本身 < 50ms，不影響用戶體驗               │
│     真正的瓶頸永遠是 LLM，用 Streaming 緩解即可     │
│                                                    │
│  2. 架構上：圖譜和 RAG 是互補關係                  │
│     語意問題 → 向量 RAG                            │
│     關係問題 → 圖查詢                              │
│     複雜規劃 → 兩者結合 + Agent 協調               │
│                                                    │
│  3. 部署從簡單開始                                 │
│     現在：NetworkX + ChromaDB（0 設定）            │
│     Demo：Neo4j Community + Qdrant（Docker）       │
│     未來：視需求擴展                               │
│                                                    │
│  4. 最快出效果的步驟                              │
│     先建圖 → 實作圖查詢 Tool → 接上現有 RAG        │
│     不需要全部改，Orchestrator 決定用哪條路         │
│                                                    │
└────────────────────────────────────────────────────┘
```
