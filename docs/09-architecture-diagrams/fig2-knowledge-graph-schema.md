# Fig 2 — 知識圖譜 Schema

## 論文定位

課程推薦領域的客製化知識圖譜資料模型。
不同於通用知識圖譜（如 DBpedia、Wikidata），
本圖譜以「課程」為核心，連結概念、技術、系所、教師與能力五個維度，
支援多跳查詢、Personalized PageRank 探索、社群分群等圖演算法應用。

---

## 圖表類型建議

Entity-Relationship 風格的節點-邊關係圖，或 UML Class Diagram 變體。
重點呈現：不同節點類型間的邊方向與權重，以及 ID 命名空間。
建議搭配一個小範例子圖（如「機器學習」相關的實際節點）作為說明。

---

## 圖譜規模

| 指標 | 數值 |
|---|---|
| 總節點數 | **27,447 個** |
| 總邊數 | **103,111 條** |
| 節點類型 | 10 種 |
| 邊類型 | 7 種 |
| 計算後台 | igraph（C 實作）+ Python 封裝 |
| PPR 執行時間 | 0.23 秒/次（Weighted PPR） |

---

## 節點類型（10 種）

### 核心節點

| 節點類型 | ID 命名空間 | 說明 | 典型屬性 |
|---|---|---|---|
| `Course` | 課號（如 `CS1001`） | 課程本體 | name, dept, credits, level(ugrad/grad), college |
| `Concept` | `concept::xxx` | 學術概念（如「機率論」「梯度下降」） | name |
| `Technology` | `tech::xxx` | 技術工具（如「Python」「PyTorch」） | name |
| `Field` | `field::xxx` | 研究領域（如「機器學習」「電腦視覺」） | name |
| `Competency` | `comp::xxx` | 核心能力（如「資料分析能力」「批判思考」） | name |

### 結構節點（組織架構）

| 節點類型 | ID 命名空間 | 說明 |
|---|---|---|
| `Department` | `dept::xxx` | 系所（如「資訊工程學系」） |
| `DeptGroup` | `deptgroup::xxx` | 系所集合（如「電機資訊學群」） |
| `CollegeBachelorProgram` | `college_bachelor::xxx` | 學院學士班（如「理學院學士班」） |
| `CreditProgram` | `program::xxx` | 學分學程（如「人工智慧技術應用學分學程」） |
| `Instructor` | `instructor::xxx` | 教師（如「陳某某_資訊工程學系」） |

---

## 邊類型（7 種，含方向與權重）

| 邊類型 | 起點 | 終點 | 權重 | 說明 |
|---|---|---|---|---|
| `REQUIRES` | Department | Course | **1.0** | 必修課關係（課程規劃圖中標示為必修） |
| `ELECTIVE` | Department | Course | **0.5** | 選修課關係 |
| `TEACHES` | Course | Technology | **1.2** | 課程使用/教授的技術（最高權重，技術查詢的核心邊） |
| `COVERS` | Course | Concept | **1.0** | 課程涵蓋的學術概念 |
| `COVERS_FIELD` | Course | Field | **0.5–1.5** | 依 Agent2 的 relevance（high=1.5/medium=1.0/low=0.5）動態加權 |
| `SIMILAR_TO` | Concept | Concept | **0.8** | 概念相似性（雙向邊，連結語意相近的概念） |
| `DEVELOPS` | Course | Competency | **0.3** | 課程培養的核心能力（通識/跨域課程較常見） |

**邊權重設計理念**：
- `TEACHES` 權重最高（1.2）：技術是最明確的課程特徵，圖遍歷應優先走此邊
- `DEVELOPS` 權重最低（0.3）：能力標籤較抽象，PPR 中希望弱化影響
- `COVERS_FIELD` 動態加權：Agent2 給出 relevance 分數，高相關的領域邊應比低相關更容易被遍歷

---

## 圖儲存與快取

| 檔案 | 格式 | 用途 |
|---|---|---|
| `knowledge_graph.json` | JSON | 原始節點/邊字典（啟動時一次讀入記憶體） |
| `knowledge_graph.pkl` | igraph pkl | igraph 序列化快取（C 實作，避免重複建圖） |

**記憶體中的圖結構（Python dict）**：
```python
{
  "nodes": {node_id: node_dict},          # 節點索引
  "edges": [edge_dict],                   # 邊列表
  "edge_attrs": {(src, tgt): edge_dict},  # 邊屬性快查
  "out":  {src: [(tgt, relation)]},       # 出向鄰接表
  "in":   {tgt: [(src, relation)]}        # 入向鄰接表（反向）
}
```

**Leiden 社群分群**（`compute_communities.py`）：
- 對圖進行 Leiden 演算法分群
- 每門課程歸屬一個「課程社群」（如「AI 與資料科學類」）
- 社群 ID 和標籤寫回節點屬性，支援 `get_course_community()` 查詢

---

## 典型多跳查詢路徑（論文中建議配具體範例）

### 路徑 1：技術→課程→系所（3 跳）
**問題**：「Python 在哪些系是必修課？」

```
tech::python
   ←[TEACHES]←
Course（Python 程式設計、資料科學導論 等）
   ←[REQUIRES]←
Department（資訊工程學系、統計研究所 等）
```

**對應工具**：`tool_get_depts_by_tech("Python")`
**輸出**：必修科系清單 + 選修科系清單 + 相關課程

---

### 路徑 2：課程概念地圖（2 跳，共享概念計數）
**問題**：「有哪些課和機器學習概念最像？」

```
Course（機器學習）
   ─[COVERS]→
Concept（梯度下降、神經網路、支持向量機 等）
   ←[COVERS]─
Course（深度學習、資料探勘、模式識別 等）
```

**共享概念數**：兩門課之間共享的 Concept 節點數 → 相似度指標
**對應工具**：`tool_get_course_knowledge_map("機器學習")`

---

### 路徑 3：PPR 全景探索（全圖擴散）
**問題**：「和 AI 相關的系所、課程、老師有哪些？」

```
種子節點：field::machine_learning, concept::neural_network
   ↓
igraph Weighted PPR（α=0.85，25 次迭代）
   ↓
按 PPR 分數排序的相關節點
   ─ Course: 深度學習、自然語言處理...
   ─ Instructor: 專長 AI/ML 的教授...
   ─ Department: 資工系、電機系...
   ─ CreditProgram: 人工智慧技術應用學分學程...
```

**對應工具**：`tool_ppr_explore(seed="機器學習", focus="overview")`

---

### 路徑 4：概念鄰域 BFS（N 跳精確鄰域）
**問題**：「哪些課涵蓋卷積神經網路？」

```
query "卷積神經網路"
   → Qdrant ncu_graph_nodes 向量搜尋 → concept::cnn 節點
   ─ BFS 2 跳 ─
   → 所有 COVERS←[concept::cnn]←Course 的課程
```

**對應工具**：`tool_explore_concept_neighborhood("卷積神經網路", hops=2)`

---

## NLP Pipeline 與圖譜的關係

此圖譜的節點和邊主要來自 Fig1 NLP Pipeline 的輸出：

| 來源 | 圖譜中的產出 |
|---|---|
| Agent1 `concepts`/`languages`/`tools` | `Concept`/`Technology` 節點 + `COVERS`/`TEACHES` 邊 |
| Agent2 `domain_tags` + `relevance` | `Field` 節點 + `COVERS_FIELD` 邊（含動態權重） |
| Agent2 `professor_links` | `Instructor` 節點（確認與課程的關聯） |
| 課程規劃 JSON（schedule_draft） | `REQUIRES`/`ELECTIVE` 邊（系所必選修關係） |
| 學分學程說明 | `CreditProgram` 節點 + 學程課程關係 |

---

## 設計決策補充說明

- **為何設計多種節點而非平面標籤**：Concept 和 Technology 在語意上不同（前者是理論，後者是工具），分開有助於後續「哪些課有教 Python」（Technology 查詢）與「哪些課涵蓋梯度下降」（Concept 查詢）的精確區分
- **邊權重的設計**：PPR 在有權重邊的圖上能更準確反映課程間的「知識流動」強度，比無權重版本更能突顯技術核心課程
- **SIMILAR_TO 雙向邊**：概念之間的相似性是對稱的（「機率論」相似於「統計學」且反之亦然），雙向邊讓 PPR 可雙向傳播
- **ID 命名空間**：`concept::xxx` 和 `tech::xxx` 的前綴確保不同類型節點不會因為同名（如 Python 可能既是概念又被列為工具）產生 ID 衝突
