# 測試 v2 結果分析

> 測試時間：2026-05-04 03:35  
> 測試檔案：`data/test_results/20260504_033517.md`  
> 題目數：38（含 4 個新類別：regression / alias / eligibility / ppr_seed）  
> 上次修正：PPR top_k 3→8、system prompt A1-A4、B1 program fix、B2 tech vector、B3 dept alias

---

## 一、整體概況

| 項目 | 數值 |
|------|------|
| 題目總數 | 38 |
| 工具呼叫失敗（error） | 0 |
| P0 回歸測試（4 題）通過 | 4 / 4 ✅ |
| alias 別名測試（3 題）通過 | 3 / 3 ✅ |
| eligibility 修課資格（3 題）工具選法正確 | 3 / 3 ✅（但有資料缺漏）|
| PPR seed 測試（3 題）改善 | 1 / 3（微積分仍 0 筆）|
| 新發現問題 | 4 個（詳見下方）|

---

## 二、P0 回歸測試（regression）

### Q1 ✅ 人工智慧技術應用學程
`get_program_info` 正確命中，回傳 13 門課程。B1 修正有效。

### Q2 ⚠️ GIS 是哪些系的課程有教到？

**問題：工具結果不透明，LLM 產生誤導性答案**

```
get_depts_by_tech("GIS") → 3 筆：
- 客庄資源調查及知識庫建置 [已停開]（客家語文暨社會科學學系）
- 文化人類學（客家語文暨社會科學學系）
- 地理資訊系統應用（地球科學學系）
```

LLM 回答：
> 「必修課含 GIS 的系所：客家語文暨社會科學學系_客家社會及政策組」

**核心問題**：
1. **「文化人類學」為什麼會出現在 GIS 查詢結果？** 這是透過 `_search_concept_nodes("GIS")` 向量搜尋，找到某個語意相近的 concept 節點（可能是「空間資訊」或「地方調查」），再從該節點沿邊找到了客語系的課程。但這個推論路徑對 LLM 和使用者完全不透明。

2. **`_search_concept_nodes` 找到了什麼節點？** 工具目前只回傳課程列表，沒有回傳「是透過哪個 concept 節點命中的」。LLM 無從判斷這個連結是否合理，導致它直接把「文化人類學」列為「含 GIS 的課程」。

3. **`客家語文暨社會科學學系_客家社會及政策組`** 是 DeptGroup（分組）節點，不是系所，顯示出現在回答中很令人困惑。

**需要優化**：
- `get_depts_by_tech` / `search_courses_by_tech` 應在回傳結果中附上「命中路徑」，至少說明是透過哪個 concept/tech 節點連結到這門課
- 或在 tool result 中附 `matched_via` 欄位，例如 `{"course": "文化人類學", "matched_via": "空間資訊系統", "match_type": "concept_vector"}`
- DeptGroup 節點應與 Department 節點區分，不要混入「系所分布」回答中

### Q3 ✅ 地科系有哪些課程可以選？
`get_dept_courses(dept_name="地球科學學系", course_type="all")` — B3 alias 解析正確，回傳 43 筆。

### Q4 ⚠️ 資工系有哪些必修課？
`get_dept_courses(dept_name="資訊工程學系", course_type="required")` — 別名解析正確 ✅，但回傳 22 筆中**微積分出現兩次**（不同課號或學期）。B4 去重邏輯未修正，答案原文也重複列出兩次微積分。

---

## 三、系所別名測試（alias）

### Q5 ✅ 大氣系畢業規定
`get_graduation_requirements(dept_name="大氣科學學系")` — 別名正確解析。

### Q6 ⚠️ 化材系在教哪些課程？

**問題：問「哪些課程」但工具選了 `get_dept_info` 而非 `get_dept_courses`**

```
get_dept_info(query="化材系") → 回傳系所介紹文字
```

LLM 回答：「目前不足以直接確認完整課程清單」，建議再查。

**分析**：別名解析（化材系 → 化學工程與材料工程學系）可能在 `get_dept_info` 有效，但問題是工具選法錯誤。使用者問的是「在教哪些課程」，應使用 `get_dept_courses`，但 LLM 卻選了 `get_dept_info`（系所介紹工具）。

**原因推測**：system prompt 中「系所課程查詢」區塊強調要用「正式系所名」，LLM 可能對「化材系」沒有把握這個縮寫能被正確解析，因此選了更保守的 `get_dept_info`。

**優化建議**：
- System prompt 的「系所課程查詢」區塊需加入說明：縮寫/別名仍可使用 `get_dept_courses`，系統會自動正規化
- 或者在 `get_dept_info` 的 tool 說明中加：「若使用者問「有哪些課」，應改用 `get_dept_courses`」

### Q7 ✅ 資管系的系所介紹
`get_dept_info(query="資管系")` — 正確回傳資管系介紹。

---

## 四、修課資格查詢（eligibility）

### Q8 ⚠️ 外系學生可以修客語教學這門課嗎？

**問題：工具選法正確（A1 修正有效），但課程在資料庫中找不到**

```
get_course_detail(name_zh="客語教學") → 找不到課程
```

A1 system prompt 修正有效：LLM 正確選擇 `get_course_detail` 而非 `search_courses` ✅

但「客語教學」這個課名在資料庫中不存在（可能正式名稱是「客語教學設計」或「客語教學法」等）。工具返回找不到後，LLM 正確地要求使用者確認課名，這部分行為合理。

**建議**：
- `get_course_detail` 在找不到精確課名時，應自動 fallback 到 `search_courses` 模糊搜尋，回傳前 3-5 個候選課名供使用者選擇
- 目前這個 fallback 需要額外一輪對話，對使用者體驗不佳

### Q9 ✅ 大一新生可以修資料結構嗎？
`get_course_detail(name_zh="資料結構")` → 消歧義，回傳 3 個候選（資工/通訊/生醫）。工具選法正確，消歧義引導合理。

### Q10 ✅ 外系生可以修機率與統計嗎？
`get_course_detail(name_zh="機率與統計")` → 消歧義，回傳 5 個候選。工具選法正確。

---

## 五、PPR Seed 擴展測試（ppr_seed）

### Q11 ⚠️⚠️ 高中學了微積分，大學往哪延伸？

**問題 1：PPR 仍回傳 0 筆（top_k=8 不足以解決根本問題）**

```
ppr_explore(seed="微積分", focus="concept", top_k=10) → 0 筆
```

即使 top_k 提升至 8，`_search_concept_nodes("微積分")` 找到的向量節點仍無法作為有效 PPR 種子。根本原因是圖中「微積分」沒有 Concept 節點，只有 Course 節點，而 Course 節點的 PPR 擴展路徑可能不夠豐富。**C1（基礎學科概念節點建立）是唯一根本解決方案。**

**問題 2：PPR 返回 0 筆後，LLM 發生幻覺，使用 `<course>` 標籤標記非工具回傳的課程**

LLM 回答中出現：
> `<course>積分</course>`、`<course>微分方程</course>`、`<course>不定積分</course>`

這些都**不是工具回傳的課程**，是 LLM 用先驗知識自行生成的。這直接違反 system prompt 規則：
> 「標籤只用於工具實際回傳過的課程，不得自行推測或補充工具未回傳的課程」

**優化建議**：
- 當 PPR 返回 0 筆時，system prompt 或工具說明應要求 LLM 轉用 `search_courses` 做語意搜尋，不要直接用先驗知識填充
- 或在 system prompt 強化：「PPR 無結果時，回傳空結果並提示換詞，不得自行列出未查詢的課程」

### Q12 ✅ 客家文化 PPR focus="all"
`ppr_explore(seed="客家文化", focus="all", top_k=15)` → 6 筆（課程 + 1 位教師）

A2 修正有效：LLM **沒有**補呼叫 `search_teachers` 或 `search_courses` ✅

### Q13 ⚠️ 機器學習 PPR（A2 未完全修正）

```
ppr_explore(seed="機器學習", focus="all", top_k=15) → 5 筆
search_teachers(query="機器學習", n=5)              → 補呼叫
```

A2 修正對 Q12（客家文化）有效，但 Q13（機器學習）仍補呼叫了 `search_teachers`。原因可能是：PPR 結果中教師節點數量少（只找到部分），LLM 認為不夠完整。

---

## 六、其他問題觀察

### Q16 ⚠️ 大氣科學學系必修課重複（B4 未修）

`get_dept_courses` 回傳 21 筆但有重複：微積分×2、普通物理A×2、應用數學×2、大氣動力學×2、天氣學與天氣分析×2。答案直接列出重複課程，使用者混淆。

### Q20 ⚠️ 永續發展學分學程命中「永續企業」

使用者問「永續發展學分學程」，系統命中「永續企業學分學程」。這是 B1 類問題（學程名稱部分相似），但在修正後仍存在，因為向量相似度判斷「永續」兩字比「發展 vs 企業」更重要。

**這個行為其實合理**（找到最接近的），但 LLM 應更清楚地告知使用者「找到的不是完全一樣的學程」，而非直接回答「你問的學程」。本次回答中有做到這一點（「你問的『永續發展學分學程』，對應到的是『永續企業』學分學程」），行為正常 ✅

### Q28 ✅ 機器學習系所分布（多工具）

使用者明確說「從課程到系所分布都想了解」，所以同時呼叫 `search_courses(tech="機器學習")` + `get_depts_by_tech("機器學習")` 是正確行為，A4 修正判斷邊界正確。

### Q35 ⚠️ 全球環境變遷用了 `explore_concept_neighborhood` 而非 `find_similar_courses`

P1-5 問題仍存在。但本次結果品質良好（找到 10 門相關課程），行為可接受。

### Q37 ✅ 社會組資料分析（A3 廣泛探索修正有效）

```
ppr_explore(seed="資料分析,統計", focus="course")
search_programs(query="資料分析 統計")
```

A3 修正有效：正確觸發 `ppr_explore` 作為第一步 ✅

---

## 七、問題彙整與優先級

### 新發現問題

| # | 問題 | 影響題目 | 嚴重度 | 狀態 |
|---|------|---------|--------|------|
| N1 | PPR 0 筆時 LLM 幻覺（使用 `<course>` 標籤標記非工具課程） | Q11 | ⚠️ 高（幻覺） | ✅ system prompt F2 |
| N2 | `get_depts_by_tech` 結果不透明（向量語意命中無解釋） | Q2 | ⚠️ 中（誤導） | ✅ `matched_via` + `matched_nodes` |
| N3 | 別名縮寫問「哪些課程」時 LLM 仍選 `get_dept_info` | Q6 | ⚠️ 中（工具選法） | ✅ system prompt F4 |
| N4 | `get_course_detail` 找不到課名時應 fallback 而非直接報錯 | Q8 | ⚠️ 中（使用者體驗）| ✅ fallback_candidates F3 |

### 仍存在的舊問題

| # | 問題 | 影響題目 | 狀態 |
|---|------|---------|------|
| B4 | `get_dept_courses` 重複課程 | Q4, Q16 | ✅ (名稱+學分) 去重 + sections 欄位 |
| C1 | 微積分等基礎學科無 Concept 節點，PPR 恆回傳 0 | Q11 | ⏳ 待修正（根本解） |
| P1-5 | `explore_concept_neighborhood` vs `find_similar_courses` 邊界 | Q35 | ⏳ 待觀察 |
| A2 | `ppr_explore` focus="all" 後仍補呼叫 search_teachers（部分題目）| Q13 | ⏳ 部分改善 |

---

## 八、優化建議

### F1. ✅ `get_depts_by_tech` / `search_courses_by_tech` 加入命中路徑說明

已實作：
- `graph_tech` 路徑每筆課程加入 `matched_via`（命中的 concept/tech/field 節點名稱）
- `get_depts_by_tech` 回傳結果前加一行「向量搜尋擴展命中節點：xxx」
- PPR seed 過濾：排除無課程連接的孤立 Field 節點（`_has_course_edge`）

### F2. ✅ PPR 無結果時禁止 LLM 自行推測課程名稱

已實作（2026-05-05）：

System prompt 強化：
- `ppr_explore` 工具指引：以課程名稱為 seed 時，用 `focus="course"` 或 `focus="all"`；基礎學科無 Concept 節點，`focus="concept"` 回傳 0 筆
- Fallback 區段：ppr_explore 0 筆時，(a) 先換 `focus="course"` 重試；(b) 仍 0 筆改用 `search_courses`；⚠️ **不得用 `<course>` 標籤標記任何課程**
- 範例 2 更新：微積分範例從 `focus="concept"` 改為 `focus="course"`，並說明原因

### F3. ✅ `get_course_detail` 找不到課名時自動 fallback

已實作（2026-05-05）：

`tool_get_course_detail`：精確名稱查不到時，自動呼叫 `retriever.search_courses(name_zh, n_results=5)` 返回 `fallback_candidates`（含 name_zh/dept/course_code/credits/distance）。System prompt 告知 LLM 呈現候選清單，請使用者確認名稱後重新查詢。

### F4. ✅ System prompt 加入「縮寫/別名也可用於 `get_dept_courses`」說明

已實作（2026-05-05）：

System prompt Filter 使用原則區段改為：
- `get_dept_courses` 支援縮寫自動正規化（「資工系」「化材系」「大氣系」均可直接傳入），不需先呼叫 `get_dept_info` 確認
- 其他工具（`search_courses` 的 `dept` 參數）仍建議使用正式全名

### F5. ✅ Graph 路徑課程語意豐富化

已實作（2026-05-05）：
- 新增 `graph_service.get_course_tags(course_id)` — 純記憶體圖遍歷，無 I/O
- 新增 `tools._enrich_courses_metadata(courses)` — 為 graph 路徑課程補齊語意欄位
- `tool_search_courses` graph_tech path + `tool_get_dept_courses` 均呼叫 enrich
- `_fmt_courses`（向量搜尋路徑）新增 `course_domain` 欄位

每筆課程回傳欄位新增：

| 欄位 | 來源 | 說明 |
|------|------|------|
| `concepts` | 圖邊 COVERS | NLP 抽取的學術概念 |
| `technologies` | 圖邊 TEACHES | 程式語言/框架/工具 |
| `field_tags` | 圖邊 COVERS_FIELD | 研究領域標籤 |
| `course_domain` | 節點屬性 domains | 原始課程綱要「課程領域」 |
| `competencies` | 圖邊 DEVELOPS | 核心能力 list（含 name/level_num/level_label） |
| `topic_tags` | 圖邊 TAGGED_AS | 通識課主題（GS/CC 課程） |
| `core_questions` | 節點屬性 | 通識課核心議題 |

### F6. ✅ Competency 節點等級建圖與 Qdrant 索引

已實作（2026-05-05）：
- `build_graph.py` `_load_raw_courses` 保留完整 `{name, level_num, level_label}` 格式（原本只存名稱）
- `DEVELOPS` 邊加入 `level_num, level_label` 屬性
- igraph 邊權重改為動態：`level_num / 4.0`（高強度課程 PPR 傳播更強）
- `build_qdrant_index.py` `INDEXED_TYPES` 加入 `"Competency"`
- `build_connected_courses` 加入 `DEVELOPS` 邊支援

**執行重建**：
```bash
python scripts/graph/build_graph.py
python scripts/rag/build_qdrant_index.py --reset
```

### F7. 系所知識側寫（future）

`get_dept_info` 補充「此系主要課程領域」— 對必修課 `domain_tags`/`course_domain` 做頻率聚合。需新的 aggregation logic，列為下輪優化。

---

## 九、執行建議

| 優先 | 項目 | 工作量 | 效益 | 狀態 |
|------|------|--------|------|------|
| ✅ | F2 PPR 無結果禁止幻覺（system prompt） | — | — | 完成 |
| ✅ | F3 `get_course_detail` fallback_candidates | — | — | 完成 |
| ✅ | F4 system prompt 縮寫說明 | — | — | 完成 |
| ★★☆ | C1 基礎學科 Concept 節點 | 大 | Q11 PPR 根本解 | ⏳ 待規劃 |
| ✅ | F1 matched_via + PPR 孤立節點過濾 | — | — | 完成 |
| ✅ | F5 graph 路徑語意豐富化 | — | — | 完成 |
| ✅ | F6 Competency 等級建圖 + Qdrant | — | — | 完成（需重建） |
| ✅ | B4 get_dept_courses 去重 | — | — | 完成 |
| ✅ | 工具回傳欄位說明（system prompt 新增章節） | — | — | 完成 |

---

*上次更新：2026-05-05。基於 test_results/20260504_033517.md（38 題）分析；F1~F6/B4/N1~N4 均已完成。C1（基礎學科概念節點）為下輪規劃項目。*
