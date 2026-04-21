# 探索模式設計文件

> 實作日期：2026-04-21  
> 對應程式碼：`backend/app/services/graph_service.py`、`backend/app/services/tools.py`、`scripts/graph/build_graph.py`

---

## 一、背景與動機

系統原本設計以**精確查找**為主（大學生選課場景）：查系所必修、找特定課程、確認修課資格。

但目標使用者包含**高中生**，他們的問法更傾向探索性：

| 問題類型 | 高中生 | 大學生 |
|---------|--------|--------|
| 典型問法 | 「演算法在學什麼？」「AI 能學到哪些東西？」 | 「演算法外系可以修嗎？」 |
| 查詢目標 | 知識地圖、學科概念、跨系連結 | 選課資格、學分、時間 |
| 最佳工具 | knowledge map + PPR 探索 | graph 結構查詢 + eligibility |

本輪新增三個**探索模式工具**，並在圖中建立 **Concept Synonymy 邊（SIMILAR_TO）**，讓語意擴散更自然。

---

## 二、Concept Synonymy 邊（SIMILAR_TO）

### 演算法

**Phase 2-f** 新增步驟，在所有 Concept + Technology 節點之間以字串相似度建立雙向 `SIMILAR_TO` 邊。

**blocking 策略**（避免 O(n²) 全比對）：
1. 建立字元反向索引：`{非ASCII字元 → [含此字的節點 id]}`
2. 候選對：共享中文字元 ≥ 2 個
3. 計算 `difflib.SequenceMatcher.ratio()`
4. 條件：ratio ≥ 0.70 且長度比 ≤ 2.5

**效果**（2026-04-21 統計）：

| 指標 | 數值 |
|------|------|
| 候選配對檢查數 | 291,492 |
| 建立 SIMILAR_TO 邊（單向） | 2,532 對 |
| 建立後總邊數 | 34,631（原 29,567） |

**範例配對**（ratio ≥ 0.70）：
- `機器學習` ↔ `機械學習`（0.75）
- `深度學習` ↔ `深層學習`（0.75）
- `Python` ↔ `Python3`（0.92）
- `演算法` ↔ `演算法設計`（0.73）

### 對 PPR 的影響

SIMILAR_TO 邊讓「機器學習」的 PPR 遊走能自然地傳播到「機械學習」「機率學習」等語意相近概念，再從那些概念繼續擴散到相關課程。

---

## 三、新增工具

### 3-A `get_course_knowledge_map(course_name)`

**目的**：回傳一門課的知識地圖

**查詢路徑**：
```
Course --[COVERS]--> Concept 節點（涵蓋概念列表）
       --[TEACHES]--> Technology 節點（使用技術）
       --[concept cluster]--> 相似課程（共享最多 COVERS 概念的課程）
```

**範例輸出**（演算法）：
```
課程: 演算法（資訊管理學系，3學分）
使用技術：C++
涵蓋概念（共 50 個）：AVL樹, K平均算法, NP-完備性, 動態規劃...
概念重疊最高的相關課程：
  - 資料結構（6 個共同概念）
  - 資料與檔案結構（4 個）
  - 計算機概論（3 個）
```

**適合問法**：
- 「演算法在學什麼？」
- 「機器學習這門課教哪些東西？」
- 「有哪些課和深度學習概念重疊最多？」

---

### 3-B `get_depts_by_tech(tech_name)`

**目的**：多跳圖查詢「哪些系所的課程有教某技術」

**查詢路徑（Multi-hop）**：
```
tech::Python
  → 反向 TEACHES → Course 節點
  → 反向 REQUIRES ← CurriculumPlan
  → 反向 HAS_CURRICULUM ← Department
```

區分**必修**（該系正式要求）與**選修**（有開但非必要）。

**範例輸出**（Python）：
```
教「Python」的系所分布（共 30 門相關課程）：

必修課含此技術的系所（5 個）：化學學系、化學工程、土木工程學系...
選修課含此技術的系所：企業管理學系、光電科學與工程學系...
```

**適合問法**：
- 「什麼科系需要學 Python？」
- 「哪些系有教機器學習的課？」
- 「SQL 在哪些系是必修？」

---

### 3-C `ppr_explore(seed, focus, top_k)`

**目的**：從種子概念出發，以 Personalized PageRank 在整個知識圖譜做廣泛探索

**演算法**：
```
初始：seed 節點分配均等初始分數
迭代（n=25次）：
  s_new[v] += alpha × s[u] / degree(u)  ← 對所有 u 的鄰居 v（無向）
  s[seed]  += (1-alpha) / n_seeds        ← Restart 保持集中
正規化 → 排序 → 過濾指定節點類型
```

- alpha = 0.85，restart prob = 0.15
- 種子限制：只從 Concept / Technology / Field / Course 節點中找（避免結構節點成為種子）

**focus 參數**：

| focus | 回傳類型 | 使用場景 |
|-------|---------|---------|
| `"all"` | 所有類型 | 廣泛探索 |
| `"course"` | 只有 Course | 「和 AI 有關的課有哪些？」 |
| `"instructor"` | 只有 Instructor | 「做機器學習研究的老師？」 |
| `"dept"` | 系所節點 | 「哪些系和 AI 最相關？」 |
| `"concept"` | Concept/Technology/Field | 「機器學習延伸到哪些概念？」 |

**範例輸出**（機器學習, course+instructor）：
```
[Instructor] 張家凱（人工智慧國際碩士學位學程）score=19.47
[Course] 深度學習程式設計（通訊工程學系）score=4.25
[Course] 人工智慧（資訊工程學系）score=4.00
[Course] 資料科學（通訊工程學系）score=3.49
[Course] 自然語言處理（AI學程聯盟）score=2.93
```

**和 `find_similar_courses` 的差異**：

| 工具 | 跳數 | 節點類型 | 適合 |
|------|------|---------|------|
| `find_similar_courses` | 2-hop（課→概念→課） | 只有 Course | 「和 X 最像的課」 |
| `ppr_explore` | 無限（帶衰減） | 全類型 | 「和 X 相關的一切」 |

---

## 四、快速重建圖指令

```bash
# 只加 SIMILAR_TO 邊（最快，不重跑其他步驟）
python scripts/graph/build_graph.py --synonymy-only

# 完整豐富化（含 synonymy）
python scripts/graph/build_graph.py --enrich-only

# 完整重建
python scripts/graph/build_graph.py
```

---

## 五、圖統計（2026-04-21）

| 指標 | 數值 |
|------|------|
| 總節點 | 14,602 |
| 總邊 | **34,631**（新增 5,064 條 SIMILAR_TO） |
| Concept 節點 | 6,938 |
| Technology 節點 | 390 |
| SIMILAR_TO 邊 | **5,064**（2,532 對） |
| COVERS 邊 | 9,049 |
| TEACHES 邊 | 633 |

---

## 六、暫緩項目

- **Embedding 相似度 Synonymy**：cosine ≥ 0.85 做語意同義邊（深度學習 ≈ 神經網路），費用 < $0.01，待字串版本驗證後實作
- **PPR 結果快取**：常用 seed 可預先計算並快取，降低每次 PPR 的計算時間
- **Community Detection**（Microsoft GraphRAG 路線）：Concept 節點分群摘要，適合「資工系的知識體系是什麼」整體性問題
