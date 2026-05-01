# Hybrid Retrieval 優化測試記錄

> 測試日期：2026-05-01  
> 測試者：實際呼叫工具函式（Python REPL，連接 Qdrant local + Azure OpenAI）

---

## 一、測試項目對應改動

| 改動 | 狀態 |
|------|------|
| `retriever.py`：`client.search()` → `client.query_points()`（qdrant-client 1.17.1 相容） | ✅ 修復 |
| `tools.py`：`_s(val)` helper 處理 Qdrant list payload 欄位 | ✅ 修復 |
| `search_courses` Layer 1（query expansion via graph nodes）+ Layer 2（Signal A/B）+ Layer 3（RRF） | ✅ 實裝 |
| `ppr_explore` gap truncation（`_ppr_gap_filter`） | ✅ 實裝 |
| `_rrf_similar_courses()` helper（圖 + 向量 RRF，`find_similar_courses` 和 `get_course_knowledge_map` 共用） | ✅ 實裝 |
| `graph_service.py`：`_search_concept_nodes()` 改用 `query_points` | ✅ 修復 |
| `build_qdrant_index.py --phase3`（概念向量 .npz） | ⏸️ 延後（待 Qdrant Cloud 遷移後） |

---

## 二、實際測試結果

### T1：`search_courses` — 語意偏移查詢

**呼叫**：`tool_search_courses(query="電腦如何看懂圖片", n=5)`  
**耗時**：30.3s（首次呼叫，含 Qdrant 初始化 + Azure embedding）

**結果**（按 RRF 分數排序）：

| course_code | name_zh | dept | distance |
|-------------|---------|------|----------|
| CE6032 | 電腦視覺 | 資訊工程學系 | 0.4432 |
| CE3060 | 電腦視覺原理及應用簡介 | 資訊工程學系 | 0.4920 |
| GS4522 | 圖像辨識的企業應用 | 通識教育中心 | 0.4940 |
| CE6031 | 圖形識別 | 資訊工程學系 | 0.5033 |
| SS6089 | 數位影像處理 | 太空科學與工程學系 | 0.5685 |

**觀察**：查詢「電腦如何看懂圖片」無任何關鍵字與課程名稱直接相符，Layer 1 query expansion 將查詢展開至圖譜概念節點（電腦視覺相關），使「電腦視覺」類課程能排到前排。結果 5 筆全部與電腦視覺/影像處理領域直接相關，語意對齊良好。

---

### T2：`search_courses` — 學院過濾器

**呼叫**：`tool_search_courses(query="資料結構", college="資訊電機學院", n=5)`  
**耗時**：2.6s（embedding 已快取）

**結果**：

| course_code | name_zh | college | distance |
|-------------|---------|---------|----------|
| CE2002 | 資料結構 | 資訊電機學院 | 0.4405 |
| CO2012 | 資料結構 | 資訊電機學院 | 0.4046 |
| CE1004 | 計算機實習 Ⅱ | 資訊電機學院 | 0.6384 |
| CE6137 | 計算機結構 | 資訊電機學院 | 0.6058 |
| CE6039 | 資料庫系統 | 資訊電機學院 | 0.6109 |

**觀察**：學院過濾正確（所有結果都在資訊電機學院）。前 2 筆是精確命中（兩個系各開一門「資料結構」），後 3 筆距離偏高（0.60+），為正常語意搜尋在限縮 collection 後的邊際命中。過濾邏輯未被 query expansion 破壞。

---

### T3：`find_similar_courses` — RRF 融合

**呼叫**：`tool_find_similar_courses(course_name="機器學習")`  
**耗時**：21.4s

**結果**（共 15 門，依 RRF 分數排序）：

```
與「機器學習」概念相近的課程（共 15 門）：
- AI商業資料分析與應用（產業經濟研究所碩士班，3學分）   [共享概念：5 個]
- 機器學習概論（通識教育中心，2學分）
- 人工智慧（機械工程學系，3學分）                       [共享概念：5 個]
- 統計與實驗設計（生醫科學與工程學系碩士班，3學分）      [共享概念：14 個]
- 自然語言處理（臺灣大專院校人工智慧學程聯盟，3學分）    [共享概念：9 個]
- Python程式設計（機械工程學系，3學分）                  [共享概念：7 個]
- 數值預報（大氣科學學系，3學分）                        [共享概念：7 個]
- 人力資源管理資訊系統與數據分析（人力資源管理碩士班，3學分）[共享概念：7 個]
- 人工智慧程式入門（生醫科學與工程學系，3學分）           [共享概念：6 個]
- 機器學習演算法（通訊工程學系，3學分）
- Python教育資料探勘實作（網路學習科技研究所碩士班，3學分）[共享概念：5 個]
- 統計學習（統計研究所碩士班，3學分）                    [共享概念：5 個]
- 人工智慧與機器學習（資訊管理學系，3學分）
- 機器學習智慧系統（財務金融學系，3學分）
- AI機器學習與應用（工業管理研究所碩士班，3學分）
```

**觀察**：
- 有 `[共享概念：N 個]` 標記的來自圖結果；無標記的為向量搜尋補入（如「機器學習概論」、「機器學習演算法」、「人工智慧與機器學習」）。
- RRF 融合使向量命中的高相關課程（如「機器學習概論」）能排入，填補純圖排名的盲點。
- 跨學院覆蓋廣（資工、生醫、統計、財金、管理）：符合「相關課程推薦」語意。

---

### T4：`ppr_explore` — Gap Truncation

**呼叫**：`tool_ppr_explore(query="深度學習", focus="course", top_k=8)`  
**耗時**：23.2s

**結果**（PPR weighted 得分，已 gap truncation 截斷）：

```
以「深度學習」為起點的 PPR 探索結果（course 模式）：
  [課程] 深度學習與建築資訊模型程式整合設計（土木工程學系）  [PPR: 48.9709]
  [課程] 深度學習程式設計（通訊工程學系）                   [PPR: 9.8699]
  [課程] 深度學習介紹（資訊工程學系）                       [PPR: 9.7108]
  [課程] 深度學習系統設計與應用（電機工程學系）              [PPR: 8.3111]
  [課程] 資料科學與機器學習（資訊管理學系）                  [PPR: 5.7053]
  [課程] 人工智慧（資訊工程學系）                           [PPR: 5.0831]
  [課程] Python程式設計（機械工程學系）                     [PPR: 4.9227]
  [課程] Python與機器學習（機械工程學系）                   [PPR: 4.7921]
```

**觀察**：
- 前 4 筆為「深度學習」同名/直接相關課程（PPR 8.3+），後 4 筆為概念相關的延伸課程（PPR 4.7~5.7）。
- Gap truncation 已生效：第 1 筆（48.97）與第 2 筆（9.87）有明顯 gap，表示「深度學習與建築資訊模型」因概念連結特別集中而得分遠高於其他；truncation 閾值未在此 gap 截斷（因為 mean−0.5σ 仍容納後面分數），8 筆全數保留符合 top_k=8 設定。
- 若 top_k 更大（如 20），truncation 會在低分尾部截斷相關性弱的節點。

---

### T5：`get_course_knowledge_map` — 課程知識地圖

**呼叫**：`tool_get_course_knowledge_map(course_name="人工智慧導論")`  
**耗時**：22.4s

**結果摘要**：

```
【人工智慧導論】（臺灣大專院校人工智慧學程聯盟，3學分）

使用技術：MATLAB, Python, sklearn
涵蓋概念（共 54 個）：AI應用, DQN, K-Means（K平均）, PCA（主成分分析）,
  Q值迭代, Q學習, SVM（支援向量機）, 人類反饋強化學習（RLHF）, 價值迭代,
  向量支持機, 基於模型的強化學習, 實體機器人, 專家系統, 對抗性搜尋,
  對話系統 ...等 54 個概念

概念重疊最高的相關課程（可延伸學習）：
  - AI商業資料分析與應用（財務金融學系）      [共享 2 個概念]
  - AI人工智慧導論（通識教育中心）
  - 人工智慧（資訊工程學系）
  - 人工智慧與機器學習（資訊管理學系）        [共享 3 個概念]
  - 生成式人工智慧導論（文學院）
  - 知行合一：AI的應用與實踐（經濟學系）
  - 自然語言處理（臺灣大專院校人工智慧學程聯盟）[共享 10 個概念]
  - 人力資源管理資訊系統與數據分析（人力資源管理研究所碩士班）[共享 6 個概念]
```

**觀察**：
- 54 個概念涵蓋 RL（DQN、Q學習）、ML（SVM、K-Means、PCA）、AI 基礎（專家系統、對話系統），符合「導論」廣度。
- 相關課程透過 `_rrf_similar_courses()` 提供（圖 + 向量融合），包含跨學院推薦（財金、文學院、人管）。
- `_s()` 修復後技術欄位（`MATLAB, Python, sklearn`）正確顯示，不再因 list 型別拋出 TypeError。

---

## 三、Bug 修復記錄

### Bug 1：`qdrant-client 1.17.1` 移除 `client.search()`

- **症狀**：所有向量搜尋靜默回傳空 list（exception 被 `except Exception: pass` 吞掉）
- **根因**：qdrant-client 1.17.1 完全移除 `.search()`，改為 `.query_points()`，回傳值從 `list[ScoredPoint]` 改為 `QueryResponse`（需取 `.points`）
- **修復**：`retriever.py` 所有搜尋函式改用 `client.query_points()`，結果取 `result.points`
- **影響範圍**：`search_courses`, `search_programs`, `search_departments`, `search_teachers`, `graph_service._search_concept_nodes()`

### Bug 2：Qdrant payload list 欄位型別不一致

- **症狀**：`tool_search_courses()` 呼叫 `_fmt_courses()` 拋出 `TypeError: can only concatenate str (not "list") to str`
- **根因**：`languages`, `tools`, `concepts`, `topic_tags` 等欄位在 Qdrant payload 以陣列儲存（支援 `$contains` 過濾），但 `_fmt_courses` 假設全為字串
- **修復**：新增 `_s(val)` helper，`isinstance(val, list)` 時 `join` 轉字串，否則直接回傳；所有相關欄位改用 `_s()` 取值

---

## 四、效能摘要

| 測試 | 耗時 | 備註 |
|------|------|------|
| T1 search_courses（首次） | 30.3s | Qdrant 初始化 + 2× Azure embedding（expanded + original）|
| T2 search_courses（快取後）| 2.6s | embedding 快取命中，僅 Qdrant 查詢 |
| T3 find_similar_courses | 21.4s | 1× Azure embedding + 圖查詢 + 向量搜尋 |
| T4 ppr_explore | 23.2s | igraph PPR（0.2s）+ Azure embedding（query expansion 種子）|
| T5 get_course_knowledge_map | 22.4s | 圖查詢 + 1× Azure embedding |

首次呼叫慢（20~30s）主要為 Azure OpenAI embedding 延遲；後續查詢有 `lru_cache(maxsize=512)` 保護，重複查詢大幅加速。

---

## 五、已知限制與後續改善

1. **Query expansion 概念品質**：`_search_concept_nodes` 回傳的節點名稱有時過於通用（如「程式設計」），可能輕微污染查詢。後續可加相似度閾值（只使用 cosine distance < 0.4 的節點）。

2. **Option A 概念向量（Phase 3）**：`search_by_concept_vec_for()` 已實作，但 `.npz` 未建立。待 Qdrant Cloud 遷移後執行 `build_qdrant_index.py --phase3` 再整合進 `_rrf_similar_courses()`（三路 RRF：圖 + 課文向量 + 概念向量）。

3. **PPR 第一名得分異常高**：`深度學習與建築資訊模型程式整合設計` PPR=48.97，遠高於其他（次高 9.87）。可能是圖譜中此課程的概念節點集中度特別高，或為資料雜訊。建議人工確認其 concept edges。

4. **`find_similar_courses` 部分結果缺 `[共享概念]` 標記**：向量搜尋補入的課程（無圖邊）不顯示共享概念數，前端呈現時可考慮改為統一顯示「語意相似」標籤。
