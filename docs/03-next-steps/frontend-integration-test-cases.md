# 前端整合測試案例

> 設計日期：2026-04-21  
> 對應功能：`course_pool` 收集 + `_extract_mentioned_courses()` 幻覺過濾 + `CourseMentionPanel` 課程卡片

測試重點：
1. **`course_cards`**：LLM 答案中提到的課程是否正確出現在卡片欄
2. **`has_large_result`**：工具回傳 > 20 門課時是否顯示提示條
3. **`course_pool_count`**：跨工具累積計數是否正確
4. **幻覺過濾**：LLM 若捏造課程名稱，不應出現在卡片
5. **多工具並行**：同一問題觸發多個工具時，course_pool 是否正確合併
6. **ReAct 多輪**：需要 2+ 輪才能回答的問題，course_pool 是否跨輪累積

---

## 一、`course_cards` 基本驗證（應出現卡片）

這類問題應觸發 `search_courses` 或 `get_dept_courses`，LLM 回答中會點名課程 → 卡片出現。

### T-01 技術導向查詢（graph-first 路徑）
```
中央大學哪些課程有教 PyTorch？
```
**預期**：
- 工具呼叫：`search_courses(query="PyTorch", tech="PyTorch")`
- LLM 答案應點名 2–5 門課
- `course_cards` 出現這幾門課（`source: graph_tech`）
- `course_pool_count ≥ 5`

---

### T-02 系所必修查詢（`get_dept_courses`）
```
資訊工程學系大學部有哪些必修課？
```
**預期**：
- 工具呼叫：`get_dept_courses(dept_name="資訊工程學系", course_type="required")`
- LLM 答案中會提到「程式設計」「資料結構」「演算法」等核心必修
- `course_cards` 出現 LLM 提到的那幾門
- `has_large_result=false`（必修通常 < 20 門）

---

### T-03 探索式查詢（`ppr_explore` → course focus）
```
我對機器學習有興趣，中央大學有哪些相關課程可以選？
```
**預期**：
- 工具呼叫：`ppr_explore(seed="機器學習", focus="course")` 或 `search_courses`
- LLM 推薦 4–6 門課 → `course_cards` 出現且已驗證
- 若額外呼叫 `get_course_knowledge_map` → `course_pool_count` 應增加

---

### T-04 知識地圖 + 相似課程（`get_course_knowledge_map`）
```
演算法這門課在教什麼？有沒有和它類似的課？
```
**預期**：
- 工具呼叫：`get_course_knowledge_map("演算法")` + `find_similar_courses("演算法")`（可能並行）
- LLM 回答會列出概念 + 推薦相似課程
- `course_cards` 出現 LLM 點名的相似課程（如「資料結構」「計算機概論」）
- `course_pool_count` 應反映 similar_courses 數量

---

## 二、`has_large_result` 驗證（應顯示提示條）

這類問題應觸發系所選修查詢，課程數 > 20 門。

### T-05 選修全列（大量課程）
```
資訊工程學系有哪些選修課？
```
**預期**：
- 工具呼叫：`get_dept_courses(dept_name="資訊工程學系", course_type="elective")`
- 資工選修通常 50–80 門 → `has_large_result=true`
- 前端提示條顯示：「共搜尋到 N 門課程，以下僅顯示回答中提到的相關課程」
- `course_cards` 只有 LLM 答案中精選的 5–8 門

---

### T-06 必修 + 選修全查（`course_type="all"`）
```
管理學院電機工程學系的課程架構是什麼？必修選修都想了解
```
**預期**：
- 工具呼叫：`get_dept_courses(dept_name="電機工程學系", course_type="all")`（或分兩次呼叫）
- 必修 + 選修合計 > 20 → `has_large_result=true`
- `course_pool_count` 應是必修 + 選修總數

---

### T-07 學分學程課程（`get_program_courses`）
```
「人工智慧技術應用學分學程」有哪些課程？
```
**預期**：
- 工具呼叫：`get_program_description("人工智慧技術應用")` + `get_program_courses("人工智慧技術應用")`
- 若課程 > 20 門 → `has_large_result=true`
- `course_cards` 出現 LLM 點名的必選修課

---

## 三、多工具並行（course_pool 跨工具合併）

### T-08 技術分布 + 課程推薦（雙工具）
```
哪些科系有教 Python？我應該選哪個系？
```
**預期**：
- 工具呼叫（並行）：`get_depts_by_tech("Python")` + `search_courses(query="Python", tech="Python")`
- `course_pool` 同時收到兩個工具的課程
- `course_pool_count` 應大於單一工具的結果數
- LLM 整合兩個結果 → `course_cards` 來自兩個工具的交集

---

### T-09 教師 + 課程並行查詢
```
電機工程學系有哪些機器學習相關的必修課，以及哪些老師在做這方面的研究？
```
**預期**：
- 工具呼叫（並行）：`get_dept_courses("電機工程學系")` + `search_teachers("機器學習")`
- `course_pool` 收到 `get_dept_courses` 的課程
- `course_cards` 只顯示 LLM 答案中提到的課程（非教師節點）
- `tools_used` 應同時包含兩個工具名

---

### T-10 系所介紹 + 課程推薦（三工具）
```
我想讀資料科學相關的科系，中央大學有哪些系所適合？它們各有什麼代表課程？
```
**預期**：
- 工具呼叫：`ppr_explore(seed="資料科學", focus="dept")` + `get_dept_info` + `search_courses`
- LLM 提到多個系所和各系代表課程 → `course_cards` 出現跨系課程
- `course_pool_count ≥ 15`

---

## 四、多輪 ReAct（course_pool 跨輪累積）

### T-11 先查系所、再查畢業規定、最後查課程（三輪）
```
我想讀資訊管理學系，他們的畢業規定是什麼？哪幾門必修課是最重要的？
```
**預期流程**：
1. 第一輪：LLM 呼叫 `get_requirements_notes("資訊管理學系")`
2. 第二輪：LLM 呼叫 `get_dept_courses("資訊管理學系", "required")`
3. 最終回答：整合畢業規定 + 必修課說明

**驗證**：
- `tools_used` 長度 ≥ 2
- `course_pool` 應累積第二輪的必修課
- `course_cards` 出現 LLM 特別強調的必修課

---

### T-12 先探索概念、再找課程（兩輪）
```
高中學過微積分，大學可以往什麼方向延伸？中央大學有沒有相關的進階課程？
```
**預期流程**：
1. 第一輪：`ppr_explore(seed="微積分", focus="concept")` 找延伸概念
2. 第二輪：`search_courses(query="數值分析 微分方程 最佳化")` 找課程

**驗證**：
- LLM 先分析延伸方向，再推薦課程
- `course_cards` 來自第二輪的搜尋結果
- `course_pool_count` 跨兩輪累積

---

## 五、幻覺過濾驗證

這類測試需要確認 `course_cards` 不包含 LLM 捏造的課程。

### T-13 邊界測試：LLM 捏造課程名稱
```
中央大學有沒有「區塊鏈與 Web3 應用」這門課？
```
**預期**：
- 工具找不到此課程 → `course_pool` 為空或無此課名
- 若 LLM 錯誤聲稱「有這門課」 → `course_cards` 應為空（幻覺過濾成功）
- 若 LLM 正確說「查無此課」 → `course_cards` 為空（正常）

---

### T-14 跨系相似課推薦（驗證只顯示已驗證課程）
```
有沒有和深度學習概念重疊最高的課程，不限系所？
```
**預期**：
- 工具呼叫：`find_similar_courses("深度學習")` 或 `get_course_knowledge_map("深度學習")`
- `course_pool` 收到 15 門相似課程
- LLM 從中挑選 4–5 門推薦 → `course_cards` 只有這 4–5 門
- 其他 10 門（LLM 未提及）不出現在 `course_cards`

---

## 六、跨領域複雜問題（高信心壓力測試）

### T-15 文理跨域：高中生探索
```
我高中讀社會組，但對資料分析和統計有興趣，中央大學有沒有不需要很強程式基礎的相關課程或學程？
```
**預期**：
- 工具呼叫：`ppr_explore(seed="統計,資料分析", focus="course")` + `get_dept_info("管理學院")` + 可能呼叫 `get_program_description`
- LLM 推薦管理學院或統計相關課程 → `course_cards` 出現

---

### T-16 生醫工程跨域查詢
```
我想學習生醫影像分析，中央大學的生醫工程或電機系有哪些課可以學到相關技術？
```
**預期**：
- 工具呼叫：`search_courses(query="生醫影像 醫學影像分析", tech="MATLAB")` + `get_depts_by_tech("影像處理")`
- 跨系結果合併 → `course_cards` 出現電機、資工、生醫相關課程

---

### T-17 客家學院通識類探索
```
中央大學有沒有關於客家文化、地方創生或永續發展的課程，適合工程系學生選修？
```
**預期**：
- 工具呼叫：`search_courses(query="客家文化 地方創生 永續發展")`
- 這類課程 Concept 節點較少，PPR 效果有限 → 主要靠向量搜尋
- `course_cards` 若有出現 → 驗證通識類課程也能被收入 course_pool

---

### T-18 選課規劃（先修鏈 + 學分計算）
```
大一資工生想提前學機器學習，哪些課是前置條件？建議的修課順序是什麼？
```
**預期**：
- 工具呼叫：`get_prereq_info("機器學習")` + `get_course_eligibility("機器學習")` + `get_dept_courses("資訊工程學系", "required")`
- 多工具回傳 → `course_pool` 收到先修課 + 必修課
- LLM 列出修課路徑中提到的所有課程 → `course_cards` 出現整個先修鏈

---

## 七、API 直接驗證指令

```bash
# T-02 基本驗證
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "資訊工程學系有哪些必修課？"}' | python -m json.tool

# 驗證重點：
# - .course_cards 列表非空
# - .course_cards[*].name 每個都出現在 .answer 文字中
# - .course_pool_count >= len(.course_cards)

# T-05 大量課程驗證
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "資訊工程學系有哪些選修課？"}' | python -m json.tool

# 驗證重點：
# - .has_large_result == true
# - .course_pool_count > 20
# - len(.course_cards) < .course_pool_count  ← 幻覺過濾有效

# T-13 幻覺過濾驗證
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "中央大學有沒有區塊鏈與Web3應用這門課？"}' | python -m json.tool

# 驗證重點：
# - 若 .answer 中沒提到具體課名 → .course_cards 為空
# - .course_cards 不應包含任何 course_pool 外的課程名稱
```

---

## 八、測試結果記錄表

| 題號 | 問題摘要 | 預期工具 | course_cards 數 | has_large_result | 幻覺過濾 | 備註 |
|------|---------|---------|----------------|-----------------|---------|------|
| T-01 | PyTorch 課程 | search_courses(tech) | 2–5 | false | — | |
| T-02 | 資工必修 | get_dept_courses | 3–6 | false | — | |
| T-03 | 機器學習探索 | ppr_explore | 3–6 | false | — | |
| T-04 | 演算法知識地圖 | knowledge_map + similar | 3–5 | false | — | |
| T-05 | 資工選修全列 | get_dept_courses | 5–8 | **true** | — | |
| T-06 | 電機必修+選修 | get_dept_courses(all) | 5–10 | **true** | — | |
| T-07 | AI 學程課程 | get_program_* | 視規模 | 視規模 | — | |
| T-08 | Python 哪些系 | get_depts_by_tech | 3–6 | false | — | 跨工具 |
| T-09 | 電機 ML 老師 | dept_courses + teachers | 3–5 | false | — | 教師節點不入卡片 |
| T-10 | 資料科學系所 | ppr + dept_info + search | 5–8 | false | — | 三工具 |
| T-11 | 資管畢業規定 | req_notes + dept_courses | 3–5 | false | — | 多輪 |
| T-12 | 微積分延伸 | ppr + search | 3–5 | false | — | 多輪 |
| T-13 | 區塊鏈課程？ | search_courses | **0** | false | ✓ | 幻覺測試 |
| T-14 | 深度學習相似課 | find_similar / knowledge_map | 4–5 | false | ✓ | 部分過濾 |
| T-15 | 社會組轉資料 | ppr + get_dept_info | 3–5 | false | — | 高中生情境 |
| T-16 | 生醫影像分析 | search + get_depts_by_tech | 3–6 | false | — | 跨域 |
| T-17 | 客家文化通識 | search_courses | 1–3 | false | — | 弱領域測試 |
| T-18 | 大一先修 ML | prereq + eligibility + dept | 4–7 | false | — | 先修鏈 |
