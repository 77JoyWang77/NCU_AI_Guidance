# 實作分析：v5 測試後修正方案

> 最後更新：2026-05-11

---

## 🔴 現在需要決定的事（共 3 項）

### 決定 1：要不要做 D1（動態 concept 擴展 threshold）？

**背景：** `search_courses` 目前固定取 top 3 個 concept 節點擴展查詢，不管命中信心高低都擴展，可能稀釋低相關查詢（如「資料科學」被擴展到不相關概念）。

**要做的話：**
- `graph_service.py` 新增 `_search_concept_nodes_with_scores()`（~25行），回傳 `(node_id, score)` 而不只是 id
- `tools.py` 改用新函式，score < 0.65 的 concept 不納入擴展（~15行）
- **需要先跑 `scripts/test_search_comparison.py` 看 score 分布，確認 0.65 是合理 threshold**

**不做的話：** 現狀不變，Q32（「資料科學相關課程」）類問題維持現有效果。

> D1 和 D2 可以同時做，兩者獨立——D1 讓 Signal A 更聰明，D2 新增 Signal C，互不干涉。

---

### 決定 2：要不要做 D2（圖概念直達）？採哪種方式？

**背景：** `search_courses` 目前只用 Qdrant 向量搜尋（兩路 RRF）。  
圖的 BFS 路徑（concept 節點 → Course）已在 `explore_by_concept_neighborhood` 實作，只差整合進 `tool_search_courses`。

**有兩種整合方式可選：**

#### 方式 D2-RRF（原計畫）
圖 BFS 結果作為 Signal C 加入 RRF，競爭排名後一起回傳最終 n=8 筆。
- LLM 看到的結果和現在一樣，只是排名有改變
- 圖結果可能排擠掉 Qdrant 的好結果

#### 方式 D2-Append（你的想法）
圖 BFS 結果**另外附加**在 Qdrant 結果後面，標記 `matched_via: "graph_concept"`，由 LLM 自己判斷要不要引用。

```python
return {
    "qdrant_results":        _fmt_courses(qdrant_top_n),   # 現有 8 筆
    "graph_concept_matches": graph_top_k,                  # 圖命中的課，帶 matched_via
}
```

- LLM 看到更多資訊，可自行取捨
- 圖結果不會排擠 Qdrant 結果
- 但會增加 token 消耗（多幾筆資料），且 `_collect_course_pool` 需同時解析兩個 key

**兩者比較：**

| | D2-RRF | D2-Append |
|---|---|---|
| 回傳格式 | 不變（list，8筆） | 改為 dict（兩個 key） |
| LLM 看到的資訊量 | 相同 | 更多 |
| 圖結果能不能影響輸出 | 透過排名 | 由 LLM 直接判斷 |
| `_collect_course_pool` 改動 | 無需改 | 需加解析 `graph_concept_matches` key |
| 雜訊風險 | 低（RRF 過濾） | 中（LLM 需自己過濾） |
| system prompt 需補充 | 輕微（說明 matched_via） | 需說明兩個 key 各自用途 |

**建議：** 如果你信任 LLM 的判斷力，選 D2-Append；如果想保持輸出穩定，選 D2-RRF。兩者工作量相近。

---

### 決定 3：要不要做 P2-b（search_courses 加 total_found）？

**背景：** `search_courses` 固定回傳 8 筆，無法告知 LLM「實際候選有幾筆」。P2-a（get_dept_courses total_found）已完成，這是 search_courses 的對應版本。

**要做的話：** tools.py 改回傳 `dict`（~15行）+ llm_service.py 改 3 處 `isinstance(result, list)` 檢查（~10行）。

**建議不做**：search_courses 固定回 8 筆，LLM 說「以下是相關課程」語意上夠用；Q3/Q6/Q25 的截斷問題根因是 `get_dept_courses` 37 筆（P2-a 已解決）。但如果你覺得值得做也可以。

---

### 決定 4：要不要做 E2-b（PPR 回傳加 seed_resolved 欄位）？

**背景：** E2-a 已做——種子全部找不到時回傳可操作的提示，部分找不到時末尾加 ⚠️ 警告。  
E2-b 是在**正常回傳的開頭**加一行「已解析種子：XXX、XXX」，讓 LLM 明確知道哪些種子有效（不只是哪些無效）。

**要做的話：** `tools.py tool_ppr_explore` 在回傳字串開頭插入一行（~5行）：
```python
resolved = [g["nodes"].get(nid, {}).get("name", nid) for nid in found_seed_ids]
lines.insert(0, f"已解析種子節點：{'、'.join(set(resolved))}")
```

**不做也可以：** E2-a 的 ⚠️ 警告已能處理「部分種子無效」的情境；E2-b 是錦上添花。

---

## ✅ 已完成（不需要你做任何事）

| 項目 | 說明 |
|------|------|
| B2 客家語文學系別名 | dept_aliases.json 一行 |
| B3 畢業規定 alias + 移除過鬆 fallback | tool_get_graduation_requirements |
| B4/P1 兩系比較 system prompt | 必查兩個系；domain_profile 夠用不拉全量 |
| B5 幻覺防範 system prompt | found=False 禁止補全系所名稱 |
| B6/G1 通識課警告 system prompt | 主題查詢改用 search_courses |
| G5 REQUIRES 邊名修正 | domain_profile 大氣/資工系恢復正常 |
| P2-a get_dept_courses total_found | 加了 total_found 欄位 |
| E1 PPR system prompt 改寫 | 多種子推薦，overview 限縮 |
| C1-C4 Tool 回傳豐富化 + 去重 | get_course_tags + enrich + dedup |
| F 分班 per-section syllabus | build_course_index + 前端 accordion（62% 有差異） |
| **E2-a PPR seed confidence hint** | tool_ppr_explore 加種子覆蓋提示 |

---

## 🟡 建議先做再決定 D1/D2

跑測試腳本，看數據再決定：

```bash
cd backend
python -m scripts.test_search_comparison              # 全部 query
python -m scripts.test_search_comparison "資料科學"   # D1 關鍵案例
python -m scripts.test_search_comparison "語言學"     # D2 非 STEM 覆蓋驗證
python -m scripts.test_search_comparison --ppr        # PPR E2-a 驗證
```

腳本輸出：每個 query 顯示「concept 節點擴展結果」＋「Qdrant 策略 vs 圖策略的重疊分析」。

---

*建立日期：2026-05-11。最後更新：2026-05-11。*
