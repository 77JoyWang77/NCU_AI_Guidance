# 測試結果分析與優化方向

> 分析時間：2026-05-03  
> 依據：`data/test_results/20260502_141607.md`（36 題）+ `docs/05-prompt-design/test-questions.md`  
> 工具版本：14 工具（docs/04-agent-tool-design/03-tools.md）

---

## 一、整體概況

| 項目 | 數值 |
|------|------|
| 測試題數 | 36 |
| 全部標記 ✅ | 36 |
| 工具選用完全符合預期 | ~22 題 |
| 存在偏差或值得討論 | ~14 題 |
| 嚴重錯誤（空結果 / 完全錯工具） | 4 題 |

> **注意**：測試報告所有題目皆標記 ✅，但本分析從工具行為、Fallback 路徑、資料缺漏等角度深入檢視，部分題目在「結果看起來 OK」的表象下仍有優化空間。

---

## 二、逐題問題清單

### 2.1 工具選用偏差（LLM 選錯 / 多呼叫）

| 題號 | 問題 | 實際工具行為 | 預期行為 | 偏差類型 |
|------|------|------------|---------|---------|
| Q1 | Python 課程 | `search_courses` + `get_depts_by_tech` | 僅 `search_courses(tech="Python")` | 多呼叫（over-tooling） |
| Q17 | 客家文化 PPR | `ppr_explore` + `search_courses` + `search_teachers` | 僅 `ppr_explore(focus="all")` | 多呼叫（3 個工具） |
| Q23 | 機器學習先修+替代 | 僅 `get_course_detail`（消歧義） | `get_course_detail` + `find_similar_courses` 並行 | 少呼叫（缺並行） |
| Q29 | 客語教學修課資格 | `search_programs` + `search_courses` | `get_course_detail(name_zh="客語教學")` | 完全錯誤工具 |
| Q34 | 社會組資料分析 | `search_courses` ×2 + `search_programs` | `ppr_explore(seed="統計,資料分析")` + `search_programs` | 漏用 PPR |

**分析**：

- **Q1**：Tech 查詢時 LLM 額外觸發 `get_depts_by_tech`，顯示兩工具的使用場景在 system prompt 中邊界不夠清晰。雖然結果更豐富，但造成不必要的工具呼叫。
- **Q17**：PPR `focus="all"` 理論上已涵蓋課程、教師、系所，LLM 卻再補呼叫 `search_courses` 和 `search_teachers`，代表它不信任 PPR 的廣度。可能原因：PPR 回傳格式讓 LLM 不確定是否已包含教師資訊。
- **Q23**：當 `get_course_detail` 回傳 ambiguous 結果後，LLM 沒有繼續並行呼叫 `find_similar_courses`，直接轉向消歧義引導。
- **Q29**：「外系學生可以修客語教學相關的課嗎？」應直接用 `get_course_detail` 查修課資格，但 LLM 把它解讀為「找課」而非「查課程資格」，選了錯誤工具路徑。
- **Q34**：社會組廣泛探索問題，`ppr_explore` 是最適合的起點，但 LLM 直接用 `search_courses` 代替，失去圖探索的優勢。

---

### 2.2 資料覆蓋缺漏（工具呼叫正確但回傳空）

| 題號 | 問題 | 工具 | 問題描述 |
|------|------|------|---------|
| Q8 | 人工智慧技術應用學程 | `get_program_info` | 比對到「地球科學資訊」學程，名稱匹配錯誤（0 筆課程卡片） |
| Q14 | GIS 系所分布 | `get_depts_by_tech` + `search_courses` | 知識圖譜中無 GIS 技術節點，兩工具均回傳 0 |
| Q21 | 微積分延伸（PPR） | `ppr_explore` | `seed="微積分"` 在圖中無概念節點，PPR 回傳 0 筆 |
| Q24 | 地球科學系課程 | `get_dept_courses` | 傳入 `"地球科學系"`（缺「學」字）→ 0 筆，正確名稱應為「地球科學學系」 |

**分析**：

- **Q8**（學程名稱比對錯誤）：`get_program_info` 的模糊比對策略在「人工智慧技術應用」命中了「地球科學資訊」，比對邏輯有問題。應優先以「人工智慧」作為核心詞比對，或在 `available_programs` 中提示使用者。
- **Q14**（GIS 節點缺漏）：資料中使用「地理資訊系統」而非「GIS」作為技術標籤，造成技術名稱別名問題。需在資料建構層補充技術別名對應表。
- **Q21**（微積分概念節點）：「微積分」在知識圖譜中是課程節點，不是概念節點，PPR 的 seed 解析無法定位。需確認圖中基礎課程是否有對應的 Concept 節點。
- **Q24**（系所名稱正規化）：LLM 在口語化問題中截短了系所名稱（「地球科學系」→「地球科學學系」），系所名稱正規化機制不夠健全。

---

### 2.3 Fallback 行為觀察

| 題號 | 問題 | Fallback 行為 | 評估 |
|------|------|--------------|------|
| Q14 | GIS Fallback | `get_depts_by_tech` → `search_courses`（仍 0 結果）→ LLM 提示換詞 | ✅ 正確放棄+提示，但應更早給出替代詞 |
| Q21 | 微積分延伸 Fallback | `ppr_explore(0筆)` → `search_courses` + `get_depts_by_tech` | ⚠️ Fallback 路徑合理但工具選法偏離預期（應是 concept→search_courses） |
| Q31 | 全球環境變遷 | 使用 `explore_concept_neighborhood` 而非 `find_similar_courses` | ⚠️ 工具選法偏差，但結果品質良好 |
| Q33 | 跨文化溝通 | 直接 `search_courses`（未先嘗試 `ppr_explore`） | ⚠️ 符合 W-03 預期的 Fallback 路徑（若 PPR 先試過才算完整） |

---

### 2.4 其他品質觀察

| 題號 | 問題 | 觀察 |
|------|------|------|
| Q3 | 大氣系必修 | 回傳 21 筆中有重複課程（微積分×2、普通物理A×2），Pool=16 但說明是 21 筆，顯示去重邏輯在 DebugPanel 顯示層與實際不一致 |
| Q7 | 永續學程 | `search_programs` 先找到「永續企業」學程（非「永續發展」），名稱不精準；若使用者指定的學程名稱改一個字就可能找錯 |
| Q20 | 地科教授 | 直接用 `search_teachers` 成功（跳過 PPR 步驟），M-03 的 2 步串行場景未被觸發。顯示「地球科學 板塊構造」這類直接問法不會觸發 PPR 前置步驟 |

---

## 三、問題分類與優先級

### P0 — 嚴重（已全部修正 ✅）

| # | 問題 | 位置 | 影響題目 | 狀態 |
|---|------|------|---------|------|
| 1 | `get_program_info` 模糊比對錯誤（命中不相關學程） | `tools.py` 比對邏輯 | Q8 | ✅ 已修正（向量搜尋 fallback + resolved_name） |
| 2 | GIS 等技術別名缺漏（技術節點名稱不一致） | 資料建構層 | Q14 | ✅ 已修正（`_search_concept_nodes` 加入 tech/dept 查詢） |
| 3 | 系所名稱正規化不足（「地球科學系」vs「地球科學學系」） | tools.py + graph | Q24 | ✅ 已修正（`dept_aliases.json` + `_find_dept_like` 4-level） |

### P1 — 重要（工具選用偏差）

| # | 問題 | 位置 | 影響題目 | 狀態 |
|---|------|------|---------|------|
| 4 | 修課資格問題用錯工具（`search_courses` 代替 `get_course_detail`） | system prompt | Q29 | ✅ 已修正（新增修課資格查詢觸發詞）|
| 5 | `find_similar_courses` vs `explore_concept_neighborhood` 邊界模糊（Q31） | system prompt | Q31 | ⏳ 待觀察 |
| 6 | PPR `focus="all"` 後 LLM 仍補呼叫其他工具（Q17） | system prompt | Q17 | ✅ 已修正（強調 focus="all" 涵蓋所有節點類型） |
| 7 | 技術查詢時不必要地補呼叫 `get_depts_by_tech`（Q1） | system prompt | Q1 | ✅ 已修正（明確化 get_depts_by_tech 觸發條件） |

### P2 — 改善（結果可接受，但流程或覆蓋度待提升）

| # | 問題 | 位置 | 影響題目 | 狀態 |
|---|------|------|---------|------|
| 8 | PPR seed 對基礎課程（微積分等）向量覆蓋不足 | 知識圖譜資料 | Q21 | ✅ 已部分修正（`top_k` 3→8，擴大向量種子範圍） |
| 9 | 廣泛探索問題漏用 `ppr_explore`（社會組 Q34） | system prompt | Q34 | ✅ 已修正（新增廣泛探索觸發條件說明） |
| 10 | `get_course_detail` 消歧義後未繼續並行呼叫 `find_similar_courses` | Agent 推論策略 | Q23 | ⏳ 待觀察 |
| 11 | `get_dept_courses` 重複課程顯示問題 | tools.py 去重邏輯 | Q3 | ⏳ 待修正（B4） |
| 12 | M-03 兩步串行（PPR→teacher_info）未被觸發 | system prompt 觸發語意 | Q20 | ⏳ 待觀察 |

---

## 四、優化方向建議

### 方向 A：System Prompt 精煉 ✅ 已完成

| 項目 | 說明 | 狀態 |
|------|------|------|
| A1 | 修課資格查詢觸發詞（「外系可以修嗎」→ `get_course_detail`） | ✅ 已加入 system prompt |
| A2 | PPR `focus="all"` 結果完整性說明（無需補呼叫其他工具） | ✅ 已加入 system prompt |
| A3 | 廣泛探索問題觸發 `ppr_explore` 的條件與範例 11 | ✅ 已加入 system prompt |
| A4 | `tech` 查詢後不必補呼叫 `get_depts_by_tech` 的明確說明 | ✅ 已加入 system prompt |

---

### 方向 B：工具層修改

**B1. `get_program_info` 比對邏輯加強 ✅ 已完成**

`"人工智慧技術應用"` 錯誤命中 `"地球科學資訊"` 的問題已修正：
- 改為 Qdrant 向量搜尋 fallback，不再使用單字元模糊比對
- 找到候選名稱後改用 `get_program_courses(resolved_name)` 查課程

**B2. 技術節點向量語意擴展 ✅ 已完成**

`"GIS"` 等英文縮寫找不到對應圖節點的問題已修正：
- 在 `search_courses_by_tech` 和 `get_depts_by_tech` 中加入 `_search_concept_nodes(tech_name, top_k=3)` 向量語意擴展
- PPR seed 向量擴展從 `top_k=3` 提升至 `top_k=8`

**B3. 系所名稱正規化 ✅ 已完成**

「地球科學系」等縮寫查不到的問題已修正：
- 建立 `data/processed/dept_aliases.json`（約 60 組縮寫→正式全名）
- `_find_dept_like()` 改為 4-level 解析：exact → alias → substring → vector

**B4. `get_dept_courses` 去重邏輯 ⏳ 待修正**

問題：大氣系必修出現重複課程（微積分×2），可能來自不同年度或不同課號。  
建議：以 `(course_code, name)` 為 key 去重，相同課程只保留一筆。

---

### 方向 C：知識圖譜資料補強

**C1. 基礎學科概念節點建立 ⏳ 待修正**

問題：PPR seed `"微積分"` 在圖中只有課程節點，無 Concept 節點可展開。  
即便 `top_k=8` 向量擴展仍可能找不到合適種子。  
根本解法：在知識圖譜中為基礎學科課程補建 Concept 節點：
- `微積分` → `微分`, `積分`, `極限`
- `線性代數` → `矩陣運算`, `特徵值`, `向量空間`

**C2. 技術標籤標準化 ⏳ 待確認**

盤點目前技術節點（`Technology` 類型），確認英文縮寫是否有中文別名節點。

---

### 方向 D：新功能評估

**D1. 學習路徑生成（Learning Path Generator）⏳ 評估中**

多題使用者詢問「如何從 A 延伸到 B」，目前靠 PPR + search_courses 拼湊，品質參差。  
建議工具 `generate_learning_path(goal, background, dept?)`，開發成本較高，建議穩定 A/B 方向後再評估。

**D2. 跨系比較工具（compare_depts）⏳ 評估中**

建議工具 `compare_depts(dept_a, dept_b)`，一次整合系所介紹、代表必修、研究方向。

**D3. 個人化選課建議 ⏳ 評估中**

建議工具 `personalized_recommendation(interests, background, constraints?)`。

---

### 方向 E：修課資格篩選功能（新增）

**E1. Eligibility Filter 整合至 `search_courses`**

Qdrant 中每門課已有完整 payload 欄位，目前尚未作為搜尋 filter 使用：

| 欄位 | 說明 | 可查詢場景 |
|------|------|----------|
| `is_unrestricted` | 完全無修課限制 | 「哪些課外系生都可以修？」 |
| `open_to_all_undergrad` | 開放全校大學部 | 「有哪些全校開放選修的課？」 |
| `open_to_minor` | 開放輔系生 | 「輔系可以修哪些課？」 |
| `open_to_double_major` | 開放雙主修生 | 「雙主修可以修哪些課？」 |
| `eligible_years` | 可修的年級清單（如 [2,3,4]） | 「大一可以修嗎？」 |
| `dept_include` | 限定開放系所清單 | 「外系能不能修？」 |
| `has_prereq` | 是否有先修要求 | 「有沒有沒有先修要求的進階課？」 |

**實作方向**：

1. 在 `search_courses` 工具加入 filter 參數（`open_to_outsider`, `eligible_year`）
2. System prompt 中加入觸發規則：
   - 「外系可以修嗎」 → `open_to_outsider=True`
   - 「大一/二/三/四年級」 → `eligible_year=1/2/3/4`
3. 工具層在 Qdrant query 時加入 `must` filter 條件

> ⚠️ 注意：目前 `raw_conditions` 文字欄位已可提供部分修課限制資訊（透過 `get_course_detail`）。Eligibility filter 的優勢在於**批次搜尋時的精準過濾**（如「哪些機器學習課外系可以修」），而非單一課程查詢。

---

## 五、優先執行建議

| 優先 | 項目 | 狀態 | 效益 |
|------|------|------|------|
| ★★★ | A1-A4 System prompt 精煉（工具選用偏差） | ✅ 已完成 | 消除 Q1/Q17/Q29/Q34 工具選錯 |
| ★★★ | B1 `get_program_info` 比對邏輯（Q8） | ✅ 已完成 | 消除學程找錯問題 |
| ★★★ | B2 技術向量語意擴展（Q14 GIS） | ✅ 已完成 | 補全技術查詢覆蓋率 |
| ★★★ | B3 系所名稱正規化（Q24） | ✅ 已完成 | 消除 dept 名稱查無結果 |
| ★★☆ | PPR top_k 3→8 seed 擴展（Q21） | ✅ 已完成 | 提升 PPR 向量種子覆蓋率 |
| ★★☆ | E1 Eligibility filter 整合至 search_courses | ⏳ 待實作 | 精準回答「外系可以修嗎」類問題 |
| ★★☆ | B4 `get_dept_courses` 去重 | ⏳ 待修正 | 改善顯示品質 |
| ★☆☆ | C1 基礎學科概念節點（Q21 根本解） | ⏳ 待修正 | 提升 PPR 覆蓋率（需圖資料重建） |
| ★☆☆ | D1-D3 進階工具開發 | ⏳ 評估中 | 進階功能 |

---

## 六、測試題目（v2，2026-05-03 更新）

`scripts/test_rag.py` 已更新為以下測試集（40 題）：

### 6.1 新增類別

| 類別 | 說明 | 題目 |
|------|------|------|
| `regression` | P0 修正回歸測試 | 人工智慧技術應用學程、GIS 系所分布、地科系課程、資工系必修 |
| `alias` | 系所別名正規化 | 大氣系畢業規定、化材系課程、資管系介紹 |
| `eligibility` | 修課資格查詢 | 客語教學外系限制、資料結構年級限制、機率與統計先修 |
| `ppr_seed` | PPR seed 擴展驗證 | 微積分延伸、客家文化 focus="all"、機器學習圖探索 |

### 6.2 測試執行建議

```bash
# 只跑回歸測試（P0 修正驗證）
python scripts/test_rag.py --cats regression

# 只跑修課資格類（A1 prompt fix 驗證）
python scripts/test_rag.py --cats eligibility

# 只跑 PPR 擴展類（top_k=8 驗證）
python scripts/test_rag.py --cats ppr_seed

# 跑完整測試集
python scripts/test_rag.py
```

### 6.3 後續 Eligibility Filter 測試題目（E1 實作後新增）

> 以下題目待 E1（search_courses 加入 filter 參數）實作後加入 `eligibility` 類別：

| 題目 | 期望行為 |
|------|---------|
| 「哪些機器學習課外系生也可以選修？」 | `search_courses(query="機器學習", open_to_outsider=True)` |
| 「有哪些課大一就可以修？不限系所。」 | `search_courses(eligible_year=1)` |
| 「輔系生可以選資訊工程的哪些課？」 | `search_courses(dept="資訊工程學系", open_to_minor=True)` |

---

*上次更新：2026-05-03。P0+P1 全部修正完成，待執行新測試集驗證改善效果。*
