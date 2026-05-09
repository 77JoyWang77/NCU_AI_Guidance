# 測試 v3 結果分析

> 測試時間：2026-05-05 13:56  
> 測試檔案：`data/test_results/20260505_135637.md`  
> 題目數：59（新增 21 題：人文/生醫生科/自然科學/通識進階/特殊班制/PPR Overview/語意豐富化/課程名稱 Fallback/分班去重）  
> 上次修正：N1 PPR 幻覺禁止、N2 matched_via、N3 縮寫別名、N4 fallback_candidates、B4 去重、F5 語意豐富化、overview 模式重設計

---

## 一、整體概況

| 項目 | 數值 |
|------|------|
| 題目總數 | 59 |
| 工具呼叫失敗（error） | 0 |
| 回答顯示 ✅ | 59 / 59 |
| 平均耗時 | 8.4s |
| 中位數耗時 | 7.5s |
| 最短耗時 | 5.4s |
| 最長耗時 | 28.1s（Q1，冷啟動） |
| 總 input tokens | 1,033,310 |
| 總 output tokens | 30,185 |

**工具呼叫統計（全場次）：**

| 工具 | 呼叫次數 |
|------|---------|
| `search_courses` | 21 |
| `get_dept_courses` | 15 |
| `ppr_explore` | 9 |
| `get_dept_info` | 8 |
| `get_course_detail` | 8 |
| `search_programs` | 8 |

---

## 二、耗時分析：為什麼平均 8.4s 而非 LangSmith 上看到的 2s？

### 兩個數字的意義不同

| 指標 | 數值 | 含義 |
|------|------|------|
| LangSmith 單次 LLM trace | ~2s | **單次 API 呼叫**（送 prompt → 收 response）的純 LLM 延遲 |
| test_rag.py 平均耗時 | 8.4s | **完整端對端 wall clock**（使用者問 → 最終答案） |

### 端對端耗時組成（典型雙輪題目）

```
[ LLM 第一輪 ] ≈ 2s → tool execution ≈ 0.1–0.5s → [ LLM 第二輪 ] ≈ 2s
              ↑                                                        ↑
        SSE first token                                    SSE stream 完畢
```

- **多輪 LLM 呼叫**：多數題目需要 2 輪（第一輪決定工具 → 第二輪生成答案），部分題目需要 3 輪
- **SSE 串流延遲**：每輪從第一個 token 到串流結束都需等待；LangSmith 只記錄到第一個 token 時間
- **工具執行時間**：圖遍歷 < 2ms，但 Qdrant 向量查詢 ~10–50ms/次，部分工具（如 `get_dept_courses all`）可能取出大量資料需序列化
- **Python 腳本開銷**：SSE 客戶端逐行解析、token 計數、結果渲染

**實際拆解（Q13 為例，3 工具 3 輪，耗時 10.24s）：**

```
系統 prompt 載入 + 第一輪 LLM ≈ 2.5s
ppr_explore 執行 ≈ 50ms
search_courses 執行 ≈ 30ms（graph_exact）
search_teachers 執行 ≈ 200ms（向量搜尋）
第二輪 LLM（含工具結果，22234 input tokens）≈ 3.5s
SSE 串流 798 output tokens ≈ 3.5s
合計 ≈ 10s  ✓
```

### Q1 冷啟動異常（28.1s）

Q1（人工智慧技術應用學程）耗時 28.1s，input_tokens = 12,139，是所有題目最高。主要原因：

1. **冷啟動**：首次請求需初始化所有服務（Qdrant index 載入、igraph 圖遍歷快取建立等），額外增加 10–15s
2. **大型工具回傳**：`get_program_info` 回傳 13 筆課程 + 詳細欄位，序列化後 input tokens 增加
3. 後續題目均已熱機，耗時大幅降低（第 2 題起約 7–9s）

### Qdrant 換 Cloud 能快多少？

| 來源 | 每次查詢延遲 | 典型場景額外影響 |
|------|------------|----------------|
| Qdrant local（本機檔案） | 10–50ms | 多工具題目合計增加 ~100ms |
| Qdrant Cloud（遠端 API） | 30–200ms（視網路） | 可能反而更慢 |

**結論：換 Qdrant Cloud 不是瓶頸所在，不建議為了降低延遲而遷移。** 真正的延遲主要來自多輪 LLM 呼叫（不可避免）與輸出 token 串流速度（受 Claude API 速率限制）。要減少端對端時間，最有效的方法是減少工具輪次（一次 overview 取代多次分別呼叫）。

---

## 三、新功能驗證

### N1 修正（PPR 幻覺禁止）✅ — Q11

```
ppr_explore(seed="微積分", focus="course", top_k=10) → 7 筆（ppr）
```

修正前：`focus="concept"` 回傳 0 筆 → LLM 用幻覺填充 `<course>積分</course>` 等非工具課程。  
修正後：`focus="course"` 正確回傳 7 門數學系相關課程（高等微積分Ⅰ、分析導論I、最佳化方法與應用等）。

### N3 修正（縮寫別名）✅ — Q6

```
get_dept_courses(dept_name="化學與材料工程學系", course_type="all") → 44 筆
```

修正前：LLM 選 `get_dept_info` 而非 `get_dept_courses`。  
修正後：直接呼叫 `get_dept_courses`，系統自動正規化「化材系 → 化學與材料工程學系」。

### N4 修正（fallback_candidates）✅ — Q57、Q58

- Q57「深度學習概論」→ fallback 回傳 5 筆相近課程（深度學習介紹×2、深度學習、深度學習程式設計等），LLM 正確呈現候選清單
- Q58「機率統計」→ fallback 回傳 5 筆（機率與統計×3、機率×2），LLM 正確要求使用者確認課名

### B4 修正（分班去重）✅ — Q16

```
get_dept_courses(dept_name="大氣科學學系", course_type="required") → 16 筆（已去重）
```

LLM 回答中正確顯示「微積分（2 班）、普通物理A（2 班）、應用數學（2 班）」，不再重複列出。

### overview 模式✅ — Q12、Q13、Q53、Q54

- Q12（客家文化）：單次 `ppr_explore(focus="overview")` → 9 門課 + 6 位教師，分組清晰
- Q53（AI 全貌）：單次 `ppr_explore(seed="人工智慧", focus="overview")` → 課程/教授/系所三區塊，單工具呼叫完成
- Q54（影像處理+電腦視覺）：多 seed 格式 `seed="影像處理,電腦視覺"` 正確解析

### 語意豐富化欄位（F5）✅ — Q55、Q56

- Q55：`get_dept_courses("資訊工程學系","all")` 回傳每門課含 `competencies` 等級（level_num 1-5、level_label），LLM 正確整理成「演算法（資訊工程學系）→ 數理邏輯能力 5 級、分析問題 5 級」等
- Q56：`search_courses(tech="Docker")` 回傳 `technologies`、`concepts`、`field_tags`，LLM 正確說明 Docker 在課程中的用途

### 新增題目類別覆蓋率

| 類別 | 題號 | 結果 |
|------|------|------|
| 人文學科（中文/英文/法語/哲學） | Q39–Q42 | 全部正確 ✅ |
| 生醫生科 | Q43–Q45 | 全部正確 ✅ |
| 自然科學（物理/統計） | Q46–Q47 | 全部正確 ✅ |
| 通識進階（藝術/法律/科技倫理） | Q48–Q50 | Q48、Q49 ✅；Q50 有 N5 問題 |
| 特殊班制（管理學院學士班/跨領域） | Q51–Q52 | ✅（資料不足但行為合理） |
| PPR Overview 模式 | Q53–Q54 | 全部正確 ✅ |
| 語意豐富化欄位 | Q55–Q56 | 全部正確 ✅ |
| 課程名稱 Fallback | Q57–Q58 | 全部正確 ✅ |
| 分班去重 | Q59 | D1 問題（0 筆回傳）|

---

## 四、新發現問題

### D1 ⚠️⚠️ 數學系 dept name 不一致 — Q59（高嚴重度）

**問題：**
```
get_dept_courses(dept_name="數學學系", course_type="required") → 0 筆
```

LLM 使用「數學學系」，但圖資料中實際名稱是「**數學系**」（不帶「學」字）。系統別名正規化目前只處理常見縮寫（資工系 → 資訊工程學系），未涵蓋同一系所的正式名稱變體。

**影響：** 使用者查詢「數學學系課程」完全無法回傳結果，且系統未給 fallback 提示。

**修正方向：**
- 在 `dept_alias_map` 加入「數學學系」→「數學系」的映射
- 或在 `list_all_departments()` 輸出後，讓 LLM 更容易確認正確名稱

---

### N5 ⚠️ 通識主題查詢觸發 get_dept_courses all — Q50（中嚴重度）

**問題：**
```
# 第 1 輪（正確）
search_courses(query="科技倫理 數位社會 AI 影響", dept="通識教育中心", n=8) → 8 筆

# 第 2 輪（多餘）
get_dept_courses(dept_name="通識教育中心", course_type="all") → 42 筆
```

LLM 拿到 8 筆語意搜尋結果後，認為不夠完整，補呼叫了 `get_dept_courses("通識教育中心","all")`，拉入 42 筆課程進 context，但最終回答只用到 7 筆。

**根本原因：** 通識課程依主題分散（人文/社會/自然/核心），LLM 對「是否已查完」缺乏信心，傾向用全量 `course_type="all"` 確認。

**影響：** input_tokens 暴增至 45,027（全場次最高），對應耗時 8.84s 且語意命中的 8 筆反而被稀釋在大量無關課程中。

**修正方向：**
- System prompt 加入指引：通識課依「主題」查詢應優先用 `search_courses(query=..., dept="通識教育中心")`；`get_dept_courses` 只在使用者明確要「通識所有課程清單」時才用
- 或在 tool description 加注：`通識教育中心` 課程超過 50 筆，`course_type="all"` 會回傳大量資料，不建議做主題搜尋

---

### A2' ⚠️ overview 後補呼叫 search_teachers — Q13（中嚴重度）

**問題：**
```
ppr_explore(seed="機器學習", focus="overview", top_k=12) → 10 筆（含教師節點）
search_courses(query="機器學習", tech="機器學習", n=8)   → 16 筆（補充）
search_teachers(query="機器學習", n=8)                   → 補呼叫
```

Q12（客家文化）已修正：overview 回傳教師後 LLM 停止補呼叫。  
Q13（機器學習）仍觸發 `search_teachers`：overview 結果中教師節點較少（機器學習圖邊稀疏），LLM 判斷不完整而補查。

**分析：** 問題不在 LLM 違規，而在「overview 教師節點數量不足」時 LLM 合理補充。但這會帶來 10.24s 耗時 + 22,234 input tokens 的代價。

**修正方向：**
- System prompt 強化：overview 模式不保證完整，若教師資料不足，主動告知使用者「教師資料目前在圖中較稀疏，如需精確請另查 `search_teachers`」，不得直接補呼叫
- 或提高 overview 模式下教師節點 top_k 上限（目前 `_CAP["Instructor"] = 6`，可試提高至 10）

---

### T1 ⚠️ 多輪重複工具呼叫 — Q38（低嚴重度）

**問題：**
```
search_courses(query="土木工程 環境工程...", n=8) → 8 筆
search_programs(query="土木 環境工程", n=5)       → 5 筆
search_courses(query="環境工程 土木工程 交叉...", n=8) → 8 筆（高度重複）
search_programs(query="環境 土木 永續...", n=5)    → 5 筆（高度重複）
```

4 次工具呼叫，其中 2+2 次查詢語意高度相似，課程回傳結果有大量重疊。總耗時 13.99s，input_tokens = 50,572（全場次第二高）。

**修正方向：** System prompt 加入「工具呼叫去重」指引：同一工具、語意相近查詢不得在同一輪連續呼叫兩次；若第一輪結果不夠，應先整合現有資料，確認具體缺口後再補查。

---

### T2 ⚠️ enrich 查詢觸發 get_dept_courses all — Q55（中嚴重度）

**問題：**
```
get_dept_courses(dept_name="資訊工程學系", course_type="all") → 97 筆
```

使用者只問「哪些課在培養程式設計能力」，LLM 選擇 `course_type="all"` 拉取整系 97 筆課程，然後在 context 中過濾，input_tokens = 24,106。

**根本原因：** 語意豐富化欄位（F5）讓 `get_dept_courses` 回傳包含 `competencies` 等級資訊，LLM 學會利用這個欄位，但代價是先拉全量再過濾。

**修正方向（兩選一）：**
1. 新增 `search_courses(query=..., dept=..., competency=...)` 欄位，支援依核心能力主題搜尋
2. System prompt 加入指引：「依能力查詢時，優先用 `search_courses(query=能力描述, dept=系所)` + `tech/field` 篩選；`get_dept_courses course_type=all` 只在使用者明確要全系課程清單時使用」

---

## 五、Session 人工檢查發現的新問題

> 來源：`data/sessions/8b6403acb8b349c1aad04ad9a35140b1.json`（使用者手動測試，2026-05-05 18:19）

### S1 ⚠️⚠️ ppr_explore 不回傳 seed 課程本身 — 「總體經濟學」（高嚴重度）

**問題：**
```
ppr_explore(seed="總體經濟學", focus="course", top_k=8) → 回傳 [經濟學、國際財經新聞、公共經濟學...]
```

EC2005「總體經濟學」（經濟學系，學士班）**確實存在於原始資料與圖中**，但 PPR 明確在程式碼中排除種子節點（`graph_service.py:795-796`）：

```python
if idx in seed_idx_set:
    continue  # ← PPR 結果永不包含種子節點本身
```

**根本原因（雙重問題）：**
1. **工具選擇錯誤（Prompt）**：使用者輸入課程名稱，LLM 選了 `ppr_explore` 而非 `get_course_detail`/`search_courses`。正確流程：先用 `get_course_detail("總體經濟學")` 直接命中；PPR 僅用於探索相鄰課程，不適合直接課程查詢。
2. **Tool description 未說明**：`ppr_explore` 的 schema 和 system prompt 均未告知 LLM「此工具永遠不會回傳 seed 課程本身」，導致 LLM 誤以為能用它「找到」某門課。

**驗證**：`get_course_detail("總體經濟學")` 或 `search_courses(query="總體經濟學")` 可直接找到 EC2005。

---

### S2 ⚠️⚠️ 自然語言處理課程被全數過濾 — 工具 + 資料雙問題（高嚴重度）

**問題：**
```
ppr_explore(seed="自然語言處理", focus="course", top_k=10) → 回傳 [資料科學與機器學習、AI代理系統...]
```

LLM 回答「目前資料中沒有直接回傳一門課名就叫『自然語言處理』的課」——這在技術上**部分正確但資訊不完整**。

**原始資料中「自然語言處理」課程清查：**

| 課號 | 系所 | 學制 | 狀態 | 是否被過濾 |
|------|------|------|------|-----------|
| CE7024 | 資訊工程學系 | 碩博同修 | 開課中 | ✗ `is_grad_only=True`，`exclude_grad_only=True` 過濾 |
| GS4518 | 通識教育中心 | 學士班 | **[已停開]** | ✗ 課名含 [已停開] |
| TC5004 | 臺灣大專院校人工智慧學程聯盟 | 碩士班 | 開課中 | ✗ `is_grad_only=True`，`exclude_grad_only=True` 過濾 |

**結論**：本科生版課程（GS4518）已停開；活躍版本均為研究所課程，被預設過濾器擋掉。`search_courses` 也找不到（因為預設 `exclude_grad_only=True`）。

**根本原因（雙重問題）：**
1. **工具選擇錯誤（Prompt）**：LLM 應先嘗試 `search_courses(query="自然語言處理", is_grad=True)` 以顯示研究所版本，讓使用者知道課程存在但屬研究所層級。目前 PPR 不會回傳這個訊息。
2. **回答品質問題**：LLM 應告知「此課程現有開課版本均為研究所課程（CE7024、TC5004），若您是大學部學生請注意；通識版 GS4518 已停開」，而非靜默地轉移到相似課程。

---

### S3 ⚠️⚠️ 張家凱開課資料遺失 — 圖結構缺陷（高嚴重度）

**問題：**
```
get_teacher_info(teacher_name="張家凱") → 任職系所=人工智慧國際碩士學位學程，開課=空
```

**原始資料查核（114_1 通識教育中心）：**

| 課號 | 課程名稱 | 學制 | 系所 |
|------|---------|------|------|
| GS4524-A/B | 人工智慧跨域應用專題 | 學士班 | 通識教育中心 |
| GS4719-A | 程式設計-Python | 學士班 | 通識教育中心 |
| GS4542-00 | 生成式人工智慧與Python程式設計跨域應用 | 學士班 | 通識教育中心 |

**根本原因（圖建構缺陷）：**

`build_graph.py:522-530` 建 TAUGHT_BY 邊時有一個關鍵前置條件：

```python
for code, r in raw.items():
    if not G.has_node(code):   # ← 只有圖中已有 Course 節點才建 TAUGHT_BY 邊
        continue
    for name in r.get("instructors", []):
        ensure_edge(G, code, iid, relation="TAUGHT_BY")
```

通識選修課（GS-coded）**不在任何系所課程結構（curriculum）中**，因此 Course 節點從未被建立 → `G.has_node(code)` 為 False → TAUGHT_BY 邊被跳過 → `get_teacher_courses` 找不到張家凱的課。

**任職系所顯示錯誤**（人工智慧國際碩士學位學程）：此為他的**學術歸屬**（教育部申報資料），但他實際**授課**的系所是通識教育中心。兩個系統的「系所」欄位語意不同，目前混淆呈現。

**影響範圍**：所有只在通識教育中心教課、不在任何系所課程地圖中出現的教師，其開課資料皆遺失。

**修正方向（兩選一）：**
1. **圖層修正（根本解）**：`build_graph.py` 加入「從 raw 中建立所有課程節點」的步驟，不限於已在課程結構中出現者。此修正會讓更多 GS/TC 課程節點進入圖，TAUGHT_BY 邊隨之建立。
2. **工具層修正（快速解）**：`get_teacher_courses` 在 TAUGHT_BY 路徑回傳空時，加入 Qdrant fallback：`retriever.search_courses(query=teacher_name, teacher=teacher_name)` 做二次補充。

---

## 六、問題彙整與優先級

### 新發現問題（session 人工測試）

| # | 問題 | 影響場景 | 嚴重度 | 根因分類 | 建議方案 |
|---|------|---------|--------|---------|---------|
| S1 | ppr_explore 不回傳 seed 課程本身 → 總體經濟學遺失 | 任何以課程名作 seed 的查詢 | ⚠️⚠️ 高 | Prompt + Tool doc | system prompt + tool schema 說明 PPR 不返回 seed |
| S2 | 自然語言處理全版本被過濾，回答無說明 | 研究所課程查詢 | ⚠️⚠️ 高 | Prompt + 資料 | system prompt 加入「研究所課程建議」；工具嘗試 `is_grad=True` |
| S3 | 通識課不在圖中 → 張家凱開課遺失 | 僅教通識的教師查詢 | ⚠️⚠️ 高 | 圖建構缺陷 | 修 build_graph.py 或 get_teacher_courses fallback |

### 新發現問題（v3 測試結果分析）

| # | 問題 | 影響題目 | 嚴重度 | 建議方案 |
|---|------|---------|--------|---------|
| D1 | 數學系 / 數學學系 名稱不一致 → 0 筆 | Q59 | ⚠️⚠️ 高 | dept_alias_map 新增變體映射 |
| N5 | 通識主題查詢觸發 `get_dept_courses all` | Q50 | ⚠️ 中 | System prompt 通識查詢指引 |
| T2 | 能力查詢觸發 `get_dept_courses all` → 97 筆 | Q55 | ⚠️ 中 | System prompt 能力查詢指引 |
| A2' | overview 後仍補呼叫 `search_teachers` | Q13 | ⚠️ 中 | System prompt 強化 / 提高 overview 教師 cap |
| T1 | 多輪重複工具呼叫（語意相近） | Q38 | ◻️ 低 | System prompt 工具去重指引 |

### 仍存在的舊問題

| # | 問題 | 影響題目 | 狀態 |
|---|------|---------|------|
| C1 | 微積分等基礎學科無 Concept 節點，PPR focus="concept" 恆回傳 0 | 基礎學科類 | ⏳ 待規劃（根本解） |
| P1-5 | `explore_concept_neighborhood` vs `find_similar_courses` 邊界 | 少數題目 | ⏳ 待觀察 |

---

## 七、優化建議

### G0. S1+S2 修正：ppr_explore tool description + system prompt（Prompt 層）

**ppr_explore tool description 加入：**
```
⚠️ 此工具回傳的是與 seed 相關的「周邊節點」，不包含 seed 本身。
若要查詢某門具體課程（如「總體經濟學」），應改用 get_course_detail 或 search_courses。
ppr_explore 用於「給我和 X 相關的課程/教師/系所」，而非「找到課程 X」。
```

**system prompt 加入：**
```
**課程名稱直接查詢原則**：
- 使用者輸入的是課程名稱（而非概念探索），優先使用 get_course_detail(name_zh=課程名)
- get_course_detail 找不到時，嘗試 search_courses(query=課程名, exclude_grad_only=False)
  - 若只有研究所版本（is_grad_only=True），應明確告知使用者，而非靜默轉移到相似課程
- ppr_explore 不適合直接課程查詢：它永遠不會返回 seed 節點本身
```

### G0b. S3 修正：圖中加入所有 raw 課程節點（根本解）

在 `build_graph.py` 步驟 `[2/4]` 之前，加入：

```python
# [1.5/4] 確保所有 raw 課程節點存在（含通識選修、聯盟課程等未在課程結構中的課）
print("  [1.5/4] raw 課程節點補建...")
for code, r in raw.items():
    if not G.has_node(code):
        G.add_node(code, node_type="Course",
                   name=r["name"], credits=r["credits"],
                   dept=r["dept"], college=r["college"],
                   level=r["level"], semester=r["semester"],
                   domains=r["domains"], source="raw")
```

此修正後，GS4524/GS4719/GS4542 等通識課就會有 Course 節點 → TAUGHT_BY 邊正常建立 → `get_teacher_courses` 回傳正確結果。

**注意**：需重建 igraph 和 Qdrant 圖索引（`build_graph.py` → `build_qdrant_index.py --reset`）。

### G0c. S3 快速解：get_teacher_courses Qdrant fallback

在 `graph_service.py:get_teacher_courses` 的空值判斷後加入：

```python
# TAUGHT_BY + COURSE_EXPERT 均無結果時，fallback 至向量搜尋
if not results:
    from app.services import retriever
    qdrant_courses = retriever.get_courses_by_teacher(teacher_name)  # 需新增此方法
    for c in qdrant_courses:
        results.append({
            "id":       c.get("course_code", ""),
            "name":     c.get("name_zh", ""),
            "credits":  c.get("credits"),
            "relation": "授課（Qdrant）",
        })
```

### G1. D1 修正：dept_alias_map 補充正式名稱變體

```python
# backend/app/services/graph_service.py  dept_alias_map 中加入：
"數學學系":   "數學系",
"物理學系":   "物理學系",          # 確認圖中正式名稱
"化學學系":   "化學學系",          # 同上
```

同時考慮對 `list_all_departments()` 輸出做一次性比對，找出所有「帶/不帶學字」的變體對，統一加入 map。

### G2. N5 + T2 修正：system prompt 通識/能力查詢指引

在「Filter 使用原則」區段加入兩條規則：

```
**通識課主題搜尋**：優先用 search_courses(query="主題關鍵字", dept="通識教育中心")；
  get_dept_courses("通識教育中心","all") 回傳超過 50 筆，僅在使用者明確要完整課程清單時使用。

**依能力查詢**：優先用 search_courses(query="能力描述", dept="系所", field="能力關鍵字")；
  get_dept_courses course_type="all" 回傳整系全量課程，不適合作為能力篩選的起點。
```

### G3. A2' 修正：overview 模式 system prompt 強化

在「ppr_explore 工具指引」加入：

```
overview 模式回傳的教師節點數量取決於圖中連結密度，可能少於實際相關教師。
若教師資訊不足，應主動告知「目前圖中教師連結較稀疏，如需完整師資請另用 search_teachers 查詢」，
不得直接補呼叫 search_teachers（除非使用者明確要求）。
```

### G4. T1 修正：工具去重指引

```
同一輪工具規劃中，若兩次查詢的 query 語意高度相似（主詞相同、只換幾個修飾詞），
合併為一次查詢；若第一次結果不夠，先整合現有資料確認具體缺口後再補查。
```

### G5. F7（future）：系所知識側寫

`get_dept_info` 補充「此系主要課程領域分布」— 對必修課 `course_domain`/`field_tags` 做頻率聚合。可在回答「系所有哪些課」的同時直接給出「本系課程以 xxx 領域為主」的總結，減少後續追問。

---

## 八、執行建議

| 優先 | 項目 | 工作量 | 效益 |
|------|------|--------|------|
| ★★★ | G0b S3 build_graph 補建所有 raw 課程節點（重建圖） | 中 | 修復所有通識教師開課遺失；讓 ppr_explore 能走到通識課 |
| ★★★ | G0 S1+S2 ppr_explore tool doc + system prompt 課程直查原則 | 小 | 根除直接課程查詢走 PPR 的誤用 |
| ★★★ | G1 D1 數學系名稱映射（+ 全面掃描名稱變體） | 小 | 根除 0 筆問題 |
| ★★☆ | G2 N5+T2 通識/能力查詢 system prompt | 小 | 降 50% 通識相關 input tokens |
| ★★☆ | G3 A2' overview 教師補呼叫禁止 | 小 | 消除 Q13 類多餘輪次 |
| ★☆☆ | G0c S3 快速解 Qdrant fallback（圖重建前的臨時方案） | 小 | 部分修復教師開課查詢 |
| ★☆☆ | G4 T1 工具去重指引 | 小 | 降低重複查詢耗時 |
| ★☆☆ | C1 基礎學科 Concept 節點建立 | 大 | 微積分 PPR 精準度（長期） |
| ◻️ | G5 F7 系所知識側寫 aggregation | 中 | 系所查詢回答更豐富 |

---

*分析日期：2026-05-05。基於 test_results/20260505_135637.md（59 題 v3）+ session 人工測試。所有 v2 修正項目（F1-F6、B4、N1-N4）均已驗證有效；新問題 S1-S3/D1/N5/T2/A2'/T1 待下輪修正。*
