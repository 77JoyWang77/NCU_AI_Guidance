# 測試結果與已知問題

> 測試時間：2026-04-30 ~ 2026-05-01  
> 測試腳本：`scripts/debug_agent.py`, `scripts/test_rag.py`

---

## 一、測試工具

### 1.1 debug_agent.py

互動式 Agent 測試工具，追蹤所有工具呼叫：

```bash
# 單次測試
python scripts/debug_agent.py "我想找人工智慧相關課程"

# 批次測試（從檔案讀取問題）
python scripts/debug_agent.py --batch questions.txt --save

# 指定 session 繼續對話
python scripts/debug_agent.py --session <session_id>
```

**輸出內容**：
- 工具呼叫紀錄（工具名稱、參數、回傳筆數）
- Course Pool 累積狀態
- Course Cards（最終推薦）
- 被過濾的課程（幻覺檢測）
- Token 統計

### 1.2 test_rag.py

自動化 API 端對端測試（`/api/chat/stream`）：

```bash
python scripts/test_rag.py --url http://localhost:8000
```

**特性**：
- 41 個內置測試用例（14 類別）
- 輸出 JSON + Markdown 報告
- 追蹤每個工具呼叫的 `coursesFound`、`scores`、`scoreType`

---

## 二、功能測試結果（2026-05-01）

### T1：語意偏移查詢（search_courses）

- **查詢**：「電腦如何看懂圖片」（不使用「電腦視覺」等正式術語）
- **耗時**：30.3s（首次，含 Qdrant 初始化 + embedding）
- **結果**：「電腦視覺」、「影像處理」、「深度學習」類課程排前列
- **評估**：Query Expansion 有效（概念節點「電腦視覺」被展開）

### T2：學院過濾（search_courses + filter）

- **查詢**：「資料結構」，`college=資訊電機學院`
- **耗時**：2.6s（embedding 快取命中）
- **結果**：正確過濾至資電學院，跨學院課程不出現
- **評估**：過濾邏輯正確，不受 query expansion 影響

### T3：跨學院 RRF 融合（find_similar_courses）

- **查詢**：「機器學習」
- **耗時**：21.4s
- **結果**：跨學院覆蓋廣（資工、生醫、統計、財金皆有），RRF 融合有效
- **評估**：多信號融合確實提升覆蓋廣度，非單一系所偏向

### T4：PPR Gap Truncation（ppr_explore）

- **查詢**：`seed=深度學習`，`focus=course`
- **耗時**：23.2s
- **PPR 分數分布**：前 4 筆 PPR score ≥ 8.3（強相關），後 4 筆 < 2.0（弱相關，自動截斷）
- **評估**：Gap Truncation 有效去除不相關尾部

### T5：課程知識地圖（get_course_knowledge_map）

- **查詢**：「人工智慧導論」
- **耗時**：22.4s
- **結果**：54 個涵蓋概念節點，跨學院相似課程推薦有效
- **評估**：知識地圖豐富，概念覆蓋廣

---

## 三、效能摘要

| 測試 | 耗時 | 主要瓶頸 |
|------|------|---------|
| T1（首次，冷啟動） | 30.3s | Qdrant 初始化 + Azure Embedding API |
| T2（快取命中） | 2.6s | 無 API 呼叫，純向量搜尋 |
| T3 | 21.4s | embedding 快取 + 圖查詢 |
| T4 | 23.2s | igraph PPR（約 0.2s）+ embedding |
| T5 | 22.4s | 圖查詢 + embedding |

**優化說明**：
- 首次呼叫慢（20~30s）主要為 Azure OpenAI embedding
- `@lru_cache(maxsize=512)` 快取相同查詢的 embedding
- igraph Weighted PPR 每次計算 ~0.2s（已優化）

---

## 四、Bug 修復記錄

### Bug 1：qdrant-client 1.17.1 API 移除

| 項目 | 說明 |
|------|------|
| **症狀** | 所有向量搜尋靜默回傳空 list，無錯誤訊息 |
| **根因** | qdrant-client 1.17.1 移除了 `client.search()`，改為 `client.query_points()` |
| **修復** | `retriever.py` 所有搜尋改用新 API，結果從 `.points` 取 |
| **影響** | `search_courses`, `search_teachers`, `get_dept_info`, `search_programs` 全部受影響 |

```python
# 舊版（已移除）
results = client.search(collection_name=..., query_vector=..., limit=...)

# 新版
response = client.query_points(collection_name=..., query=..., limit=...)
results = response.points
```

### Bug 2：Qdrant payload list 欄位 TypeError

| 項目 | 說明 |
|------|------|
| **症狀** | `_fmt_courses()` 拋出 `TypeError: can only concatenate str (not "list") to str` |
| **根因** | `languages`, `tools`, `concepts` 等欄位以 list 格式儲存，但顯示時直接字串拼接 |
| **修復** | 新增 `_s(val)` helper：list 時 join 轉字串，str 時直接使用 |

```python
def _s(val) -> str:
    if isinstance(val, list):
        return ", ".join(str(v) for v in val if v)
    return str(val) if val else ""
```

---

## 五、已知問題與技術債

### 5.1 工具選擇歧義

| 問題 | 說明 |
|------|------|
| `find_similar_courses` vs `get_course_knowledge_map` | 兩者都用 `_rrf_similar_courses()`，差別只在多了概念/技術清單；LLM 可能傾向選 knowledge_map |
| `explore_concept_neighborhood` vs `ppr_explore` | 精確（BFS）vs 廣泛（PPR），邊界在 System Prompt 中不夠清晰 |

**建議**：中期考慮移除 `find_similar_courses`，功能整入 `get_course_knowledge_map`。

### 5.2 Dead Code

| 位置 | 描述 |
|------|------|
| `llm_service.py` | `_build_context()`, `generate_answer()`, `generate_simple_answer()`：已被 Tool-Use flow 取代 |
| `llm_service.py` | `_verify_course_list()`：被 `_extract_courses_from_tags()` 取代 |
| `tools.py` | `tool_get_prereq_info`, `tool_get_course_eligibility`：已整合進 `get_course_detail` |
| `tools.py` | `can_student_take()` 及相關函式：路由層無呼叫 |

### 5.3 串流 `done` 事件缺 `sources`

`generate_with_tools` 回傳 dict 包含 `sources`，但 `stream_with_tools` 的 done 事件沒有 `sources`。前端目前不使用此欄位，但若日後需要引用來源則需補充。

### 5.4 Phase 3 概念向量（.npz 未建立）

`build_qdrant_index.py --phase3` 可建立「每課程概念平均向量」的 `.npz` 檔，供 `search_by_concept_vec_for()` 使用。目前尚未執行，已實作的函式 `_build_course_concept_vecs()` 待啟用。

### 5.5 Query Expansion 概念品質

部分查詢的概念節點展開結果過於通用（如「學習」、「方法」），建議加入相似度閾值（cosine distance < 0.4）過濾。

---

## 六、未來規劃

### 短期（1-2 個月）

| 項目 | 說明 |
|------|------|
| 清理 dead code | 移除已廢棄函式，降低維護成本 |
| 工具邊界釐清 | 更新 System Prompt 範例，避免工具選擇歧義 |
| Phase 3 .npz | 執行 `build_qdrant_index.py --phase3` 建立概念平均向量 |

### 中期（2-4 個月）

| 項目 | 說明 |
|------|------|
| 使用者測試 | 高中生 / 大學生真實場景測試，收集回饋 |
| Qdrant Cloud 遷移 | 評估從 file-mode 遷移至 Qdrant Cloud，解決冷啟動問題 |
| 回應速度優化 | 減少首次呼叫延遲（探索嵌入批次快取） |

### 長期（4 個月+）

| 項目 | 說明 |
|------|------|
| 資料更新機制 | 115 學年度課程資料更新流程自動化 |
| 個人化功能 | 使用者帳號 + 儲存探索歷程 |
| 多輪推薦精化 | 根據對話歷史調整推薦策略 |
