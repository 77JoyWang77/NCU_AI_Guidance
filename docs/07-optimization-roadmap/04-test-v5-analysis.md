# 測試 v5 分析報告

> 測試時間：2026-05-09  
> 題目版本：v5（71 題）  
> 基線：全部 71 題成功回答，0 工具錯誤  
> 平均耗時：~7s（最快 4.9s，最慢 13.9s）

---

## 一、已修正的 Bug

### B1 ✅ `get_course_detail` 精確查詢時同名課程互蓋（已修正 2026-05-09）

**問題根源（`llm_service.py _collect_course_pool`）：**

```python
# 舊：以 name 為 key → 同名不同系的課只有第一筆進 pool
if name and name not in course_pool:
    course_pool[name] = { ... }
```

當 LLM 做課程比較（例如總體經濟學，連續呼叫 `get_course_detail(course_code="EC2005")` / `EC2006` / `FM2004`），三筆 `name_zh` 都是「總體經濟學」，第一筆進 pool 後其餘兩筆被 `name not in course_pool` 擋掉，最終 course_cards 只剩 1 個 (EC2005)，但回答裡卻正確描述了三門課（LLM 仍能讀到 tool result，只是卡片無法顯示）。

**修正：** 以 `course_code or name` 作為 pool key，每個課號獨立存入。

```python
key = code or name   # EC2005 / EC2006 / FM2004 各自獨立
if key and key not in course_pool:
    course_pool[key] = { ... }
```

---

## 二、待修正問題

### B2 ✅ 客家語文學系必修課查詢回傳 0 筆（Q21）（已修正 2026-05-11）

**現象：** `get_dept_courses("客家語文學系", "required")` → 0 筆，LLM 無法回答。

**根因：** 圖中節點名稱為「客家語文暨社會科學學系」，alias 沒有涵蓋「客家語文學系」這個短名。

**修正：** 在 `dept_aliases.json` 加入 `"客家語文學系" → "客家語文暨社會科學學系"`（已完成）。

---

### B3 ⚠️ 中文學系畢業規定顯示錯誤學程要求（Q48）

**現象：** Q48 回答裡出現「地球科學資訊學分學程 15 學分」「氣候與環境變遷學分學程 18 學分」等規定，明顯是地科/大氣系的規定，不是中文學系的。

**根因：** `get_graduation_requirements` 取得的原文畢業規定資料中，中文學系那份混入了其他系的文字。需查 raw data 確認。

**修正方向：** 檢查並修正 `graduation_requirements` 資料中「中國文學學系」那一筆，確認無其他系所資料混入。

---

### B4 ⚠️ 系所比較只查一個系（Q56 財金 vs 經濟）

**現象：** Q56「財務金融學系和經濟學系有什麼不同？」LLM 只呼叫 `get_dept_info("財務金融學系")` 一次，沒有查詢經濟學系。比較內容部分是憑知識補充。

**根因：** G5 的 `domain_profile` 已補充財金系 top-5 領域，但 LLM 未觸發查第二個系。

**修正方向：** system prompt 的比較場景補充提示：
```
**兩系比較**：若使用者詢問「A系和B系有什麼不同」，必須分別呼叫 get_dept_info 查詢兩個系。
```

---

## 三、效能問題

### P1 ⚠️ 系所比較觸發 get_dept_courses(all) → token 暴增（Q54）

**現象：** Q54「大氣科學系和地球科學系有什麼不同？」→ 4 次工具呼叫（get_dept_info ×2 + get_dept_courses all ×2），回傳 85+37=122 筆課程，68,030 input_tokens，耗時 9.45s。

**根因：** LLM 拿到 get_dept_info 後判斷「課程差異」需要全量課程佐證，主動追加了兩次 get_dept_courses。但 G5 domain_profile 現在已有 top-5 領域，理論上不需要再拉全量。

**修正方向：** system prompt 加：
```
比較兩系時，get_dept_info 的 domain_profile 欄位已提供 top-5 課程領域摘要，
通常不需要再呼叫 get_dept_courses(course_type="all")；
除非使用者明確要求列出完整課程清單。
```

---

## 四、觀察與建議（不需修正）

| # | 觀察 | 影響 | 建議 |
|---|------|------|------|
| O1 | Q42 地球科學學系課程側寫 → get_dept_info 回傳無 domain_profile（只有 Collego 文字） | G5 未生效 | 檢查 get_dept_domain_profile 是否有回傳結果（可能該系圖中課程節點的 domains 欄位為空） |
| O2 | Q46 通識教育中心選修 → 回傳 37 筆含普通物理/電路學等跨開課 | 使用者期待的「通識課」和系統定義不同 | 已升級為 B6，見下方 |
| O3 | Q15 歷史研究所 → Qdrant 無匹配，LLM 憑知識回答 | 非關鍵功能 | Collego 資料若有歷史研究所則補建；否則接受 |
| O4 | Q29 數學系課程「以哪些領域為主」→ 呼叫 get_dept_courses(all) 而非 get_dept_info | G5 domain_profile 對問「課程領域」的題更有用 | system prompt 加：「哪些領域為主」類問題優先 get_dept_info 看 domain_profile |
| O5 | Q59 社會組資料分析 → pool 只有 2 筆但回答了很多課 | 卡片少；PPR 路徑回傳無法進 pool | 可接受；PPR 結果以文字呈現不是問題 |
| O6 | PPR overview 範例問句（「高中學了 XX，大學往哪延伸」）怪異，overview 輸出也令人困惑 | LLM 較少正確使用 overview 模式 | 重寫 system prompt PPR 說明：強調多種子（逗號分隔），overview 僅在明確要看全貌時使用 |
| O7 | Q32 `search_courses` 對 domain_tags 類問題效果差 | 現在 concept expansion top_k=3，未利用 Qdrant payload 的 domain_tags 欄位 | 考慮 Dynamic top_k 或 Graph Concept Direct Path；詳見設計文件 |
| O8 | G5 `domain_profile` 在回答中沒有明顯改善 | `get_dept_info` 已回傳 domain_profile，但 LLM 未被引導引用 | system prompt 補充：介紹系所時應主動引用 domain_profile 欄位 |
| O9 | 前端分班課程詳情共用顯示，不同班的 course_objective/course_content/textbook 不可見 | 分班課程信息展示不完整 | ✅ 已修正（2026-05-11）：build_course_index 加 per-section syllabus；前端加 hasDifferentSyllabus 判斷 + accordion 顯示 |

---

## 五、新增待修正問題（2026-05-11）

### B5 ⚠️ Q23 幻覺：LLM 捏造不存在的系所名稱

**現象：** Q23「法律與政府研究所課程」→ 圖中無此系所，LLM 自行補全為「法律與政府學系」並捏造課程內容。

**根因：** `get_dept_courses` 或 `get_dept_info` 回傳 `found=False` 時，LLM 在「好意補全」的情況下推斷出不存在的近似系所名。

**修正方向：** system prompt 「回答規則」補充：工具回傳 `found=False` 時，**只能根據 fallback_candidates 列出候選**，嚴禁自行推斷或補全系所名稱。

---

### B6 ⚠️ Q46 通識教育中心 elective 回傳跨開工程課

**現象：** `get_dept_courses("通識教育中心", "elective")` → 37 筆包含普通物理、電路學等工程課，不是人文社會類通識。

**根因：** 部分工程課以「通識教育中心」為開課單位代碼掛名，但並非 GS/TC/CC 開頭的正統通識課。

**修正方向（二選一）：**
1. system prompt 補充：通識主題查詢改用 `search_courses(query="主題", dept="通識教育中心")`，不用 `get_dept_courses(通識教育中心, elective)`
2. 工具層：自動偵測 `dept="通識教育中心"` 時只回傳 GS/TC/CC 開頭課號

---

### P2 ⚠️ Q3/Q6/Q25：工具回傳 37 筆但回答只提 17 筆，截斷不透明

**現象：** `get_dept_courses` 回傳 37 筆選修課，LLM 只列舉 17 筆，使用者不知道截斷發生。

**根因：** tool 回傳無 `total_found` 欄位，LLM 自行截斷但未告知總數。

**修正方向：** `tool_search_courses` 和 `tool_get_dept_courses` 回傳加 `total_found` 欄位；system prompt 要求：若 `total_found > len(courses)`，回答需說明「共找到 X 筆，以下列出最相關的前 N 筆」。

---

### P3 ⚠️ Q13：回答提及 7 門課但課程卡只有 6 張

**現象：** 第 7 門課的 `<course>` 標籤存在於回答中，但 pool 只收到 6 筆。

**根因：** 可能是某筆課的 code 與 name 配對在 `_extract_courses_from_tags` 時未能正確命中。B1 修正後應有所改善，若仍發生需逐 session 追蹤。

---

## 六、摘要（更新至 2026-05-11）

| 項目 | 狀態 |
|------|------|
| B1 `get_course_detail` 同名課程 pool key 覆蓋 | ✅ 已修正（2026-05-09） |
| B2 客家語文學系別名缺失 | ✅ 已修正（2026-05-11） |
| B3 `get_graduation_requirements` alias 未正規化 + 過鬆 fallback | ✅ 已修正（2026-05-11） |
| B4 系所比較只查一個系 system prompt | ✅ 已修正（2026-05-11） |
| B5 Q23 LLM 幻覺補全不存在系所 | ✅ 已修正（2026-05-11，system prompt） |
| B6 通識教育中心 elective 回傳工程課 | ✅ 已修正（2026-05-11，system prompt 強化通識查詢說明） |
| P1 比較問題觸發 get_dept_courses(all) | ✅ 已修正（2026-05-11，system prompt） |
| P2 截斷不透明（37 筆但只說 17 筆） | ✅ 已修正（2026-05-11，get_dept_courses 加 total_found） |
| P3 Q13 課程卡少一張 | ⚠️ 待觀察（B1 修正後） |
| G5 domain_profile 對部分系未生效 | ✅ 已修正（2026-05-11，graph_service 加 REQUIRES 邊識別） |

---

## 附：版本命名說明

v4 跳號原因：`v4_regression` 標籤的測試主要用於修正後的 regression 驗證，題目組合未更新（沿用 v3 題庫）。v5 是第一個有實質題目更新（新增 `econ_fin`/`social_sci`/`dept_compare` 類別，共 71 題）的正式版本，故命名為 v5。

---

*建立日期：2026-05-09。最後更新：2026-05-11。測試版本 v5（71 題）。*
