# Fig 4 — Graph-first + Hybrid Retrieval 三路整合架構

## 論文定位

展示本系統的三層檢索整合策略：
1. **圖精確查詢**（Graph-First）：有明確技術/概念時走圖，零語意損失
2. **圖語意 Query Expansion**：以知識圖譜節點擴展查詢詞彙，橋接詞彙不一致問題
3. **Qdrant Hybrid Search**：Dense（語意）+ BM25（關鍵字）內層 RRF

三路結果再由 Fig3 的多信號 RRF 做外層融合。
整體設計形成「圖為骨架，向量為血肉，多信號排序為靈魂」的複合架構。

---

## 圖表類型建議

三欄式架構圖：左側「圖查詢路徑」、中間「查詢入口與路由」、右側「Qdrant Hybrid 路徑」。
或用 Decision Tree 風格呈現三種路徑的選擇邏輯。
建議在右側加入 Qdrant 內部結構（Prefetch → FusionQuery）的細節。

---

## Qdrant 6 個 Collection

| Collection | 儲存內容 | 向量類型 | 備注 |
|---|---|---|---|
| `ncu_courses_ug` | 大學部課程（含 NLP 萃取的標籤） | Dense + BM25 | 主要查詢目標 |
| `ncu_courses_grad` | 研究所課程 | Dense + BM25 | `is_grad=True` 時切換 |
| `ncu_credit_programs` | 學分學程（說明文字） | Dense + BM25 | `search_programs()` 使用 |
| `ncu_departments` | 系所簡介（Collego 資料） | Dense + BM25 | `search_departments()` 使用 |
| `ncu_teachers` | 教師專長描述 | Dense + BM25 | `search_teachers()` 使用 |
| `ncu_graph_nodes` | 圖節點名稱（Concept/Tech/Field）| **Dense only** | Query Expansion 使用 |

**ncu_graph_nodes 設計選擇**：
- 只用 Dense，不用 BM25
- 理由：圖節點多為 1-4 字短詞（如「梯度下降」「PyTorch」），BM25 對短文本效果差，語意向量更能捕捉縮寫/同義詞（如「CNN」≈「卷積神經網路」）

---

## 路徑 1：Graph-First 精確路徑

**觸發條件**：`tech` 參數有值（使用者指定了特定技術/工具）

```
tech = "PyTorch"
    │
    ▼
graph_service.search_courses_by_tech("PyTorch")
    │
    ├─[精確查找] tech::pytorch 節點（ID 完全匹配）
    ├─[大小寫] node.name.lower() == "pytorch"
    └─[語意補充] Qdrant ncu_graph_nodes 向量搜尋
              → 找到別名/縮寫（如 "Torch"、"PyTorch Framework"）
    │
    ▼
找到 tech 節點後，走反向邊：
    tech::pytorch ←[TEACHES]← Course A
    tech::pytorch ←[TEACHES]← Course B
    tech::pytorch ←[COVERS]←  Course C  （concept 型節點也支援）
    tech::pytorch ←[COVERS_FIELD]← Course D
    tech::pytorch ←[DEVELOPS]← Course E
    │
    ▼
按 level 過濾（ugrad / grad）
    ▼
_enrich_courses_metadata() 補齊語意欄位
    ▼
直接回傳（不進入 Qdrant 搜尋）
```

**優勢**：圖中的 `TEACHES` 邊是由 Agent1 LLM 精確標注的，
技術-課程關係沒有向量搜尋的模糊性，精確度最高。

---

## 路徑 2：Query Expansion via Graph（圖語意橋樑）

**觸發條件**：一般文字查詢（無 tech 參數）

```
query = "機器學習"
    │
    ▼
Qdrant ncu_graph_nodes 向量搜尋（top_k=25）
    向量：Azure OpenAI text-embedding-3-large("機器學習")
    Collection：ncu_graph_nodes（Dense only）
    │
    ▼ 回傳 scored_nodes（25 筆，各有 score）
    │
    ├── Track A（節點類型 ∈ {Concept, Technology, Field, Competency}）
    │       擷取節點名稱 → extra_terms（排除與 query 相同的詞）
    │       取最多 5 個補充詞
    │       expanded_query = "機器學習 深度學習 神經網路 PyTorch 特徵工程"
    │
    └── Track B（節點類型 = Course，score ≥ 0.65）
            記為 direct_course_items = [(course_id, score), ...]
            → 後續 Signal C 的種子（Fig3 L6 使用）

expanded_query → 進入路徑 3 Qdrant Hybrid Search
original_query → 同時進入路徑 3（Signal B，防稀釋）
```

**設計意義**：
- 解決「使用者說深度學習但課程描述寫神經網路」的詞彙不一致問題
- 圖節點作為「知識橋樑」，把查詢從自然語言擴展到圖的語意空間

---

## 路徑 3：Qdrant Hybrid Search 內部架構

**每次 Qdrant 搜尋的內部流程**：

```
query string（可能是 expanded_query 或 original_query）
    │
    ├──►  Azure OpenAI text-embedding-3-large
    │     Input: query text
    │     Output: dense vector（3072 維）
    │     Cache: @lru_cache(maxsize=512)（相同 query 只 embed 一次）
    │
    └──►  Qdrant 內建 BM25 模型
          Input: query text
          Output: sparse vector（詞頻/逆文件頻率權重）
    │
    ▼
Qdrant Query：
    Prefetch(
        query=dense_vector,
        using="dense",
        limit=n×3           ← 取 3 倍數量以供後續 RRF 有足夠候選
    )
    Prefetch(
        query=sparse_vector,
        using="bm25",
        limit=n×3
    )
    query=FusionQuery(fusion=Fusion.RRF)   ← Qdrant 內層 RRF 融合
    
    可選 filter（Qdrant must 條件）：
    - {"dept": {"$eq": "資訊工程學系"}}
    - {"is_grad_only": {"$eq": False}}
    - {"$or": [...student_college 修課資格條件...]}
    
    可選 must_not 條件（Signal A_excl 路徑）：
    - {"dept_exclude": {"$contains": dept}} for dept in depts_in_college
    - {"college_exclude": {"$contains": student_college}}
    │
    ▼
回傳：list of {id, document, metadata, distance}
```

**距離定義**：`distance = 1 - cosine_similarity`（越小越相似）

---

## 兩層 RRF 結構

```
┌─────────────────────────────────────────────┐
│           Qdrant 內層 RRF                   │
│  Dense Prefetch + BM25 Prefetch             │
│  → FusionQuery(RRF)                         │
│  → Hybrid 排序（語意 + 關鍵字融合）          │
└──────────────────┬──────────────────────────┘
                   │ Signal A / Signal B / Signal A_excl
                   ▼
┌─────────────────────────────────────────────┐
│           tools.py 外層 RRF                 │
│  + Signal N（課名精確匹配 Boost +0.15）      │
│  + Signal N2（課名包含查詢 Boost +0.05）     │
│  + Signal C（圖節點 score Boost）            │
│  → 最終排序                                 │
└─────────────────────────────────────────────┘
```

**兩層 RRF 的設計理由**：
- **內層**（Qdrant）：語意 vs 關鍵字的融合，由 Qdrant 原生支援，效率高
- **外層**（tools.py）：多個異質信號的融合，需要業務邏輯（課名置頂、修課資格驗證），在 Python 層控制

---

## NLP Pipeline → Qdrant Payload 的閉環

這張圖與 Fig1 NLP Pipeline 形成完整的「建構→查詢」閉環：

```
[離線建構階段（Fig1 NLP Pipeline）]
    Agent1 → concepts/languages/tools
    Agent2 → domain_tags + relevance
    Agent3 → topic_tags + core_questions
    Agent4 → simplified_concepts
         │
         ▼ 建圖腳本整合
    knowledge_graph.json（節點/邊）
    + Qdrant payload（課程 metadata 寫入）
         │
         ▼
[線上查詢階段（Fig4 Hybrid Retrieval）]
    Qdrant payload.concepts 可做 "$contains": "梯度下降" 過濾
    Qdrant payload.tools    可做 "$contains": "PyTorch" 過濾
    ncu_graph_nodes 節點    可做 Query Expansion 向量搜尋
    knowledge_graph.pkl     可做 Graph-First 技術查詢
```

**NLP 標籤在 Qdrant 的用途**：
- `tools`/`languages` → `$contains` filter（tech 查詢的 Qdrant 側過濾）
- `topic_tags` → `$contains` filter（通識課主題標籤篩選）
- `domain_tags_rich` → 向量搜尋文件的一部分（增強語意匹配覆蓋）

---

## Qdrant Payload 關鍵欄位（ncu_courses_ug）

### 識別欄位
```
course_code, name_zh, name_en, dept, college, credits, type, teacher
```

### NLP 萃取欄位（來自 Fig1 Pipeline）
```
concepts[]          ← Agent1：學術概念
languages[]         ← Agent1：程式語言
tools[]             ← Agent1：技術工具
domain_tags_rich[]  ← Agent2：研究領域（含 relevance）
domain_tags[]       ← Agent2：簡化版領域標籤
topic_tags[]        ← Agent3：通識課主題（25 類）
core_questions[]    ← Agent3：通識課核心議題
simplified_concepts[]  ← Agent4：高中橋接說法
```

### 時程欄位
```
when_raw           ← 建議修習時機（"大一上"）
when_contexts[]    ← 格式 "dept_id@大一上"（多系所時有多筆）
dept_schedule[]    ← 已格式化的時程字串
```

### 修課資格欄位（v3 格式）
```
access_rules[]  每筆包含：
    program_types[]    ← ["bachelor"] or ["master"]
    years[]            ← [1, 2] 表示大一大二可修
    dept_include[]     ← 允許的系所清單
    college_include[]  ← 允許的學院清單
    dept_exclude[]     ← 排除的系所清單
    college_exclude[]  ← 排除的學院清單
    open_to_minor      ← 輔系生可否修
    open_to_double_major  ← 雙主修生可否修
```

### 特殊旗標
```
is_open_to_all_undergrad  ← True = 全體大學部學生可修
is_open_with_exclusions   ← True = 全開但有排除特定系所/學院
is_grad_only              ← True = 限研究所學生修
```

---

## 技術選型決策說明（論文 Discussion 可引用）

| 決策 | 選擇 | 理由 |
|---|---|---|
| 向量模型 | Azure OpenAI text-embedding-3-large（3072d） | 中文語意理解佳，3072 維精度高於 1536 維 |
| 稀疏向量 | Qdrant 內建 BM25 | 關鍵字查詢（如課號、精確課名）BM25 比 Dense 更精確 |
| 融合策略 | RRF（k=60） | 對不同量級的分數穩健，不需調參 |
| 圖後端 | igraph（C 實作）| Weighted PPR 0.23s/次，比 NetworkX 快 10x 以上 |
| 快取策略 | LRU(512) + 單例 Qdrant client | 相同查詢零重算，節省 Azure API 費用 |
| ncu_graph_nodes 不用 BM25 | Dense only | 短詞節點 BM25 效果差，語意向量更能找到縮寫/同義 |
