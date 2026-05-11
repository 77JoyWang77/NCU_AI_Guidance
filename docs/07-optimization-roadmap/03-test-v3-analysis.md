# 測試 v3 → v4 優化追蹤

> 初版測試時間：2026-05-05（59 題）  
> 最後更新：2026-05-09  
> v3 基線：平均耗時 8.4s、工具錯誤 0、59/59 回答成功

---

## 一、已完成優化

| # | 項目 | 說明 |
|---|------|------|
| G0 | PPR tool doc + 課程直查 system prompt | ppr_explore 加警告；system prompt 加「課程名稱直接查詢原則」 |
| G0b | build_graph [1.5/4] 補建通識課節點 | GS/TC 課程 Course 節點補建 → TAUGHT_BY 邊正常建立，張家凱等通識教師開課資料修復 |
| G1 | 數學系 alias + HAS_GROUP fix | dept_aliases.json 新增「數學學系」→「數學系」；`_iter_dept_plans()` 修復 HAS_GROUP 系所（數學、機械、客家、生醫） |
| F5 | graph 路徑課程語意豐富化 | search_courses / get_dept_courses 回傳加入 concepts / technologies / field_tags / course_domain / competencies |
| B4 | get_dept_courses 去重 | 同名同學分課程合併為一筆，加 sections 欄位 |
| N1-N4 | PPR 幻覺禁止 / matched_via / 縮寫別名 / fallback_candidates | 見 v2 分析 |
| Qdrant Docker | 並行工具呼叫修復 | lru_cache 並發初始化 → QdrantClient 多執行緒競爭 → 改用 Docker server（QDRANT_URL）解決 |
| Frontend correction | 串流答案修正穿透前端 | done 事件加 final_answer；前端 onDone 用修正後文字更新 content；session 儲存也改用 final_answer |
| G2 | 通識/能力查詢 system prompt | 加「通識課主題查詢優先 search_courses」和「依能力查詢不走 get_dept_courses all」指引 |
| G3 | overview 後補呼叫 search_teachers 限制 | system prompt 加：圖中教師節點稀疏時主動告知，不得直接補呼叫 search_teachers |
| G4 | 多輪語意重複工具去重指引 | system prompt 加：同主題查詢合併為一次，先整合現有結果確認缺口再補查 |
| G5 | 系所知識側寫 domain_profile | graph_service.get_dept_domain_profile；tool_get_dept_info 回傳加 domain_profile（top-5 領域頻率） |

---

## 二、待處理問題

> G2/G3/G4/G5 均已完成（2026-05-09）。以下保留問題描述供參考。

### G2 ✅ 通識/能力查詢觸發全量 get_dept_courses（已修正）

**問題：**
- N5：search_courses 拿到 8 筆後，LLM 再補 `get_dept_courses("通識教育中心","all")` → 42 筆、input_tokens 暴增至 45,027
- T2：「哪些課培養程式設計能力」→ `get_dept_courses("資訊工程學系","all")` → 97 筆

**修正方式：** 在 system prompt「Filter 使用原則」加：

```
**通識課主題搜尋**：優先 search_courses(query="主題", dept="通識教育中心")；
  get_dept_courses("通識教育中心","all") 超過 50 筆，僅在使用者明確要完整清單時使用。

**依能力查詢**：優先 search_courses(query="能力描述", dept="系所")；
  get_dept_courses course_type="all" 不適合作為能力篩選起點。
```

---

### G3 ✅ overview 後仍補呼叫 search_teachers（已修正）

**問題：** Q13（機器學習）ppr_explore overview 後仍觸發 search_teachers，因圖中機器學習教師邊稀疏，LLM 判斷不完整而補查。耗時 10.24s、22,234 input_tokens。

**修正方式：** system prompt 加：

```
overview 模式教師節點數取決於圖連結密度，可能少於實際相關教師。
若教師資訊不足，應告知「目前圖中教師連結較稀疏，如需完整師資請另用 search_teachers」，
不得直接補呼叫 search_teachers（除非使用者明確要求）。
```

---

### G4 ✅ 多輪語意重複工具呼叫（已修正）

**問題：** Q38（土木+環境工程）4 次工具呼叫中 2+2 次查詢語意高度相似，課程大量重疊，耗時 13.99s、50,572 input_tokens。

**修正方式：** system prompt 加：

```
同一輪若兩次 query 主詞相同、只換修飾詞，合併為一次；
若第一次結果不夠，先整合現有資料確認缺口再補查。
```

---

### G5 ✅ 系所知識側寫（已完成）

**目標：** `get_dept_info` 或新工具回答「X 系適合什麼人」時，補充「本系課程以 xxx 領域為主」的統計摘要，減少使用者追問。

**實作方式：**

1. **資料來源**：圖中每門必修課已有 `course_domain`（來自 `node["domains"]`）和 `field_tags`（COVERS_FIELD 邊）。
2. **聚合邏輯**：在 `graph_service.py` 新增 `get_dept_domain_profile(dept_id)` — 走 `HAS_CURRICULUM → CurriculumPlan → REQUIRED → Course`，對所有必修課的 `domains` 和 `field_tags` 做頻率統計，回傳 top-5 領域。
3. **整合點**：`tool_get_dept_info` 呼叫此函式，在回傳 dict 加 `"domain_profile": [...]`。
4. **工作量**：中（純圖遍歷，無需重建資料）。

---

### happy-painting-swing plan ◻️（見計畫檔）

**項目：**
- F5 已完成（graph 路徑語意豐富化）
- B4 已完成（分班去重）
- 計畫檔中 Step 6（`_fmt_courses` 加 `course_domain`）待確認是否已隨 F5 一起做

---

## 三、仍存在的結構性限制

| # | 問題 | 影響 | 狀態 |
|---|------|------|------|
| C1 | 微積分等基礎學科無 Concept 節點，PPR focus="concept" 恆回傳 0 | 基礎學科類 PPR 精準度 | ⏳ 待規劃（需重跑 NLP enrichment） |
| P1-5 | `ppr_explore` vs `find_similar_courses` 使用邊界不清晰 | 少數多工具題目 | ⏳ 待觀察 |

---

## 四、下一步建議

| 優先 | 項目 | 工作量 | 狀態 |
|------|------|--------|------|
| ✅ | G2/G3/G4 system prompt | 小 | 已完成 |
| ✅ | G5 系所知識側寫（get_dept_domain_profile） | 中 | 已完成 |
| ◻️ | C1 基礎學科 Concept 節點（重跑 NLP） | 大 | 暫緩 |
| ◻️ | P1-5 ppr_explore vs find_similar_courses 邊界 | 中 | 待觀察 |

---

*更新日期：2026-05-09。v5 題庫重整：縮減資工題比重，擴充人文/語言、經濟金融、社科/客家、通識（共 63 題）。*
