# 檢索分層測試：方法論總覽

本目錄記錄「純向量搜尋 vs 知識圖譜/多信號 RRF 融合」的實際查詢案例測試，用來量化多信號 RRF
各信號的邊際貢獻——課程助理的核心檢索邏輯是手寫的多信號 RRF，光看程式碼很難直觀感受「拿掉
某個信號會讓結果變成什麼樣子」，這份測試把每個信號的實際作用拆出來看。

**誠實定位**：本測試是**小規模、質化的案例消融**，不是有 relevance-label 的統計顯著量化 benchmark
（系統本身沒有 ground-truth 標記集）。價值在於用具體查詢說明「圖譜/RRF 各信號實際做了什麼」。

---

## 系統實際架構（測試設計依據）

課程推薦 RAG（`/api/chat`，非 PDF 論文問答那套）的檢索管線遠比「向量 vs 向量+圖譜」兩路複雜。
`backend/app/services/tools.py::tool_search_courses()` 內部是**手寫多信號 RRF**：

| Signal | 來源 | 機制 |
|---|---|---|
| A | Query Expansion 向量搜尋 | 用 Layer1 從 `ncu_graph_nodes` 語意搜尋到的 Concept/Technology/Field/Competency 節點名稱，附加到原問句組成 `expanded_query`，再查 Qdrant |
| B | 原始問句向量搜尋 | 只在 `expanded_query != query` 時才查，避免原始語意被擴展詞稀釋 |
| A_excl/B_excl | 系限排除補回 | 補回「全校開放但排除特定系所」的課程（正向 filter 抓不到） |
| N | 課名完全比對 | boost = 0.15（遠高於單一 RRF 貢獻上限 ≈1/61≈0.016），命中直接置頂 |
| N2 | 課名部分包含 | boost = 0.05 |
| C | 圖語意直達課程 | Layer1 中 Qdrant `ncu_graph_nodes` 語意搜尋直接命中的 **Course 節點**（score≥0.65），boost = score/(RRF_K+1) |

六路用 `RRF_K=60`、公式 `1/(RRF_K+rank)` 融合（`tools.py:425`，函式內寫死的區域變數）。
另有兩套獨立圖檢索入口：**PPR**（`graph_service.ppr_explore`，種子需 `_search_concept_nodes_with_scores`
分數 ≥0.65 或字串比對才收錄）與 **BFS**（`explore_by_concept_neighborhood`，hops=2，入口同樣靠語意搜尋）——
這兩者**不是**上面六路 Signal 的一部分，是獨立的圖探索工具（`find_similar_courses` 等其他 LLM tool 才會用到）。

Leiden 社群偵測（`scripts/graph/compute_communities.py`）**已算好但完全沒接上執行期**，是斷鏈死代碼
（`docs/04-agent-tool-design/06-known-issues.md` 已記錄），本次測試不涵蓋。

## 四層拆解定義

| 層 | 呼叫 | 對應生產邏輯 |
|---|---|---|
| 純向量 | `retriever.search_courses(query)` | 沒有任何圖擴展/boost 的最陽春向量搜尋，作為 baseline |
| 純圖譜 PPR | `graph_service.ppr_explore(seed_names=[query], node_type_filter=["Course"])` | 獨立圖工具，種子直接餵整句問句 |
| 純圖譜 BFS | `graph_service.explore_by_concept_neighborhood(query, hops=2)` | 對照組，另一種圖探索方式 |
| RRF 融合後 | `_fusion_shadow.fused_search_with_breakdown()` | `tool_search_courses()` 的「影子複製」，等同生產邏輯，且拆出六路 Signal 個別貢獻 |

「影子複製」而非直接呼叫生產函式的原因：`RRF_K` 等常數是 `tool_search_courses()` 函式內寫死的
區域變數，無法用 monkey-patch 修改，要做消融實驗只能複製一份邏輯出來參數化。複製版本以
**canary check** 保證正確性——每次執行都先比對「全開參數下影子複製 top5」是否與
「真正呼叫 `tool_search_courses()`」完全一致，不一致就拒絕繼續（代表 `tools.py` 已改動，需要
重新同步 `scripts/test_course_agent/_fusion_shadow.py`）。

## 消融組合

| 消融 | 參數 | 觀察 |
|---|---|---|
| `no_signal_c` | `use_signal_c=False` | 拿掉圖語意直達課程 |
| `no_expansion` | `use_expansion=False` | 拿掉 query expansion（近似「無圖擴展的純向量 RRF」） |
| `no_name_boost` | `use_name_boost=False` | 拿掉課名 boost（Signal N/N2） |
| `no_excl` | `use_excl=False` | 拿掉系限排除補回 |
| `rrf_k_10/30/100/200` | `rrf_k=...` | RRF_K 掃描，觀察排名穩定度 |

## 測試題目

三組主案例，各測「生活化問法」與「專業改寫問法」：**手語辨識工具**、**收據記帳工具**、
**假新聞查核工具**（挑選依據見 `case-studies.md`，均以 `data/processed/graph/knowledge_graph.json`
實際確認過圖節點命中情況，查無字面節點但有語意相關節點）。

## 執行方式

```bash
# 前提：本地 Qdrant Docker 已啟動且 .env 的 QDRANT_URL=http://localhost:6333
docker-compose up -d
python scripts/qdrant/test_connection.py

# 跑全部 3 案例（含 canary check + 消融，約 50 秒）
python scripts/test_course_agent/test_retrieval_layers.py

# 只跑單一案例、跳過消融（單題除錯用）
python scripts/test_course_agent/test_retrieval_layers.py --case sign_language --no-ablation

# 只驗證影子複製與生產邏輯是否同步
python scripts/test_course_agent/_fusion_shadow.py
```

輸出：`data/test_results/retrieval_eval/<timestamp>_<case_id>.json`（結構化資料，含待人工填寫的
`human_eval` 欄位骨架）與 `<timestamp>_report.md`（人類可讀對照表）。

## 檔案

- `README.md`（本檔）：方法論總覽
- `case-studies.md`：三主案例完整對照表與觀察（人工判斷欄位待補）
- `ablation-results.md`：RRF_K 掃描、各 Signal 消融結果的完整數據
