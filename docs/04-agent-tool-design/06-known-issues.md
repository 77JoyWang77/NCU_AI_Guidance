# 06 — Known Issues & 優化建議

> 根據 Session `9cf94447`（社會組學生查詢資料分析課程）的測試結果，結合 `llm_service.py` / `tools.py` / `HighlightedAnswer.tsx` / `DebugTracePanel.tsx` 程式碼分析整理。

---

## Issue 1：前端課程高亮出現子字串誤匹配

**現象**

回答文字中出現「偏資料科學：「巨量資料分析」學分學程」，其中「資料分析」四個字被渲染成可點選的課程連結，即使使用者看的是學程敘述而非課程名稱。

**根因**

`HighlightedAnswer.tsx` 的 `injectCourseMarkers`（第 13–24 行）對**整段回答文字**做全域 regex 替換：

```ts
// HighlightedAnswer.tsx:18
result = result.replace(
  new RegExp(escaped, 'g'),
  `<mark data-cid="${i}">${name}</mark>`,
);
```

只要 `courseCards` 裡有「資料分析」，**任何位置**出現這四個字都會被高亮，包含作為子字串的「巨量**資料分析**學分學程」。中文沒有空格作為詞界，無法直接用 word boundary。

**附帶問題：`filtered_out` key 型別不匹配**

```python
# llm_service.py:987
filtered_out = [n for n in course_pool if n not in card_names]
```

`course_pool` 的 key 在 `search_courses` 路徑下是 `course_code`（如 `MA2011`），但 `card_names` 是用 `c["name"]`（如「統計學」）建立的 set，兩邊型別不同，導致 Debug 面板的 filtered_out 數字不準確。

**建議修復**

**前端**：不要掃描全文，改為直接解析 `<course>課名</course>` 標籤。後端已在 LLM 輸出中帶入這些標籤，前端只需：
1. 在渲染前找到所有 `<course>...</course>` 的位置
2. 只替換這些精確位置為可點選元件
3. 剩餘文字照常渲染

這樣「巨量資料分析」裡的「資料分析」不會被誤匹配，因為它不在任何 `<course>` 標籤內。

**後端**：修正 `filtered_out` 改用 value 的 name 欄位：
```python
filtered_out = [
    card["name"] for card in course_pool.values()
    if card["name"] not in card_names
]
```

---

## Issue 2：同名課程在 name_index 中被後者覆蓋

**現象**

「統計學」同時出現在數學系、大氣科學系、管院等多個系所。`_extract_courses_from_tags` 建立的 `name_index` 是 `dict[str, dict]`，同名時後者覆蓋前者，匹配結果取決於 pool 中的排列順序。LLM 明確指定「數學系統計學」時，前端卻可能出現管院版本的課程卡。

**根因**

```python
# llm_service.py:~464
for card in course_pool.values():
    cname = card.get("name", "")
    if cname:
        name_index[cname] = card   # ← 同名直接覆蓋，全部只剩最後一筆
```

**建議修復（根本解法）**

分兩步驟同步實作：

**Step 1 — SYSTEM_PROMPT 要求 LLM 在 tag 中帶入系所**

```
提到課程時，請使用 <course>課名（系所）</course> 格式，例如：
<course>統計學（數學系）</course>
課名必須與工具回傳的名稱完全一致，系所同理。若不確定系所，只寫課名即可。
```

**Step 2 — 後端以 `(name, dept)` 二元組消歧義，同時保留所有版本**

```python
# name_index 改為 dict[str, list[dict]] 保留所有同名版本
name_index: dict[str, list[dict]] = {}
for card in course_pool.values():
    cname = card.get("name", "")
    if cname:
        name_index.setdefault(cname, []).append(card)

# 解析 <course>統計學（數學系）</course>
import re
TAG_RE = re.compile(r'<course>(.*?)(?:（(.*?)）)?</course>', re.DOTALL)

for raw in TAG_RE.finditer(answer):
    name = raw.group(1).strip()
    dept_hint = (raw.group(2) or "").strip()

    candidates = name_index.get(name, [])
    if not candidates:
        # fuzzy match ...
        continue

    if len(candidates) == 1:
        matched = candidates[0]
    elif dept_hint:
        # 優先選系所相符的版本
        matched = next(
            (c for c in candidates if dept_hint in c.get("dept", "")),
            candidates[0]
        )
    else:
        matched = candidates[0]  # 沒有系所提示，取第一筆
```

這樣即使 LLM 沒有帶系所，也能正確回傳（取第一筆）；帶了系所就能精確消歧義。

---

## Issue 3：course_pool 大量空字串欄位

**現象**

`get_dept_courses` / `get_program_courses` 放入 pool 的 entry，`summary=""`、`type=""`，甚至 `credits=0`。前端課程卡顯示不完整，LLM 也無法從 pool 判斷課程性質。

**根因**

知識圖譜（Neo4j）的課程節點只儲存 `{id, name, credits, relation, teacher}`，沒有摘要、概念、技術工具等文字內容：

```python
# llm_service.py:~555
course_pool[name] = {
    "type":    c.get("relation", ""),   # 圖的 relation 是 REQUIRED/ELECTIVE，不是中文
    "summary": "",                       # 圖沒有此欄位
}
```

**架構選項分析**

| 選項 | 說明 | 優點 | 缺點 |
|------|------|------|------|
| **A. 直接在 Neo4j 擴充 node properties** | 把 summary/concepts/technologies 也存進圖的課程節點 | 查詢時一次取得所有資料 | 需重跑 NLP pipeline 並重新匯入；圖擅長關係，不擅長大文字；ChromaDB 和 Neo4j 維護兩套相同資料 |
| **B. ChromaDB cross-lookup（推薦）** | 從圖取得 course_id 後，呼叫 `retriever.get_courses_by_code(id)` 補充 ChromaDB metadata | 圖管關係、ChromaDB 管內容，職責分明；`retriever.py` 已有 `get_courses_by_code()` 可直接用 | 多一次 ChromaDB IO，每門課一次查詢，大量課程時有效能影響（需批次處理） |
| **C. Agent 呼叫額外工具** | Agent 在 `get_dept_courses` 後再呼叫 `get_course_syllabus` / `search_courses` 取得詳細資料 | 不需修改後端架構 | 大量增加 tool call 次數與 latency；超出 max_rounds 時根本無法執行 |
| **D. 換套件** | 使用同時支援向量搜尋與圖關係的套件（如 Weaviate、Qdrant graph） | 統一一套資料存取 | 重建成本極高，現階段過度設計 |

**建議：採用 B（ChromaDB cross-lookup）**

在 `_collect_course_pool` 收集圖工具結果後，對 summary 為空的 entry 以 course_id 批次查詢 ChromaDB。ChromaDB metadata 的 `type` 欄位本來就存「必修」/「選修」中文字串（建立索引時已轉換），因此 `type`、`summary`、`concepts` 全部從 ChromaDB 一次取得，不需要再對圖的 `relation` 欄位做 `REQUIRED → 必修` 的額外轉換：

```python
def _enrich_from_chroma(course_pool: dict) -> None:
    from .retriever import get_courses_by_code
    for key, card in course_pool.items():
        if card.get("summary"):
            continue  # 已有內容跳過
        code = card.get("code", "")
        if not code:
            continue
        results = get_courses_by_code(code)
        if results:
            m = results[0].get("metadata", {})
            card["summary"]  = results[0].get("document", "")[:150]
            card["concepts"] = m.get("concepts", "")
            card["type"]     = m.get("type", card["type"])  # "必修"/"選修"直接從 ChromaDB 取
```

注意：若課程存在於圖但不在 ChromaDB（邊緣情況），`type` 保留圖的原始值（可能是英文），這個問題留待 Issue 5 的 ChromaDB 重建時一併處理。

---

## Issue 4：summary 來源錯誤導致前端顯示一行長串

**現象**

前端課程卡的摘要顯示如：

```
課程目標："一、教學目標： 瞭解資料蒐集及統合法..." 授課內容："1.課程介紹及教學平台使用 2.個人...
```

所有欄位標籤與內容擠成一行，即使加 `whitespace-pre-line` CSS 也沒用，因為資料本身就沒有換行。

**根因**

`tools.py:_fmt_courses` 的 `summary` 欄位取的是 ChromaDB 的 `document` 欄位截斷前 200 字：

```python
# tools.py:57
"summary": r.get("document", "")[:200],
```

ChromaDB 的 `document` 是索引時把課程所有文字欄位（課程目標、授課內容、教師資訊…）**串接成一行**的原始字串，供向量搜尋用。這個字串不是給人讀的，截斷後語意也不完整。

同時，通識課的 `concepts`/`technologies` 欄位通常為空（NLP 提取對通識課效果差），無法作為替代。

**根本問題：summary 不應從 `document` 讀取，應從 ChromaDB metadata 的結構化欄位取得**

`_fmt_courses` 已從 `metadata` 讀取 `concepts`、`technologies`、`domain_tags` 等欄位，但 `summary` 還是從 `document` 取。兩者分離：

| 來源 | 內容 | 適合用途 |
|------|------|---------|
| `document` | 所有欄位串接一行 | 向量搜尋的索引文字，不適合顯示 |
| `metadata.concepts` | NLP 提取的核心概念 | 課程卡摘要、LLM 判斷課程性質 |
| `metadata.tools` | NLP 提取的技術工具 | 課程卡摘要、技術篩選 |
| `metadata.domain_tags` | 領域標籤 | 分類顯示 |

**建議修復**

依課程類型分兩路：

**技術/理工課程**：`summary` 改由 metadata 的 `concepts` + `tools` 組合，這兩個欄位建立索引時已從 NLP 結果寫入：
```python
# tools.py:_fmt_courses — 直接從 metadata 讀，不從 document 截斷
"summary": ", ".join(filter(None, [m.get("concepts", ""), m.get("tools", "")])),
```

**通識課（GS / CC 課號）**：`concepts`/`tools` 通常為空，但 `topic_tags` 已在 metadata（`build_vector_index.py:448`），可直接讀取。`core_questions` 目前只寫入 `document` 文字（line 421），**未存入 metadata**，需要 patch：

```python
# build_vector_index.py metadata 區段需補充：
"core_questions": " | ".join(core_qs[:3]),   # ← 目前缺少此行
```

Patch 方式：不需要完整重建 index，用 `collection.update()` 只更新 metadata：
```python
# scripts/rag/patch_core_questions.py（需新增）
import chromadb, json
from pathlib import Path

client = chromadb.PersistentClient(path="data/processed/chroma_db")
col = client.get_collection("ncu_courses_ug")
topic_data = json.loads(Path("data/processed/nlp/nlp_topic_tags.json").read_text("utf-8"))

# 取出所有需要更新的 doc
res = col.get(include=["metadatas"])
ids_to_update, metas_to_update = [], []
for doc_id, meta in zip(res["ids"], res["metadatas"]):
    code = meta.get("course_code", "")
    qs = topic_data.get(code, {}).get("core_questions", [])
    if qs:
        meta["core_questions"] = " | ".join(qs[:3])
        ids_to_update.append(doc_id)
        metas_to_update.append(meta)

col.update(ids=ids_to_update, metadatas=metas_to_update)
print(f"Patched {len(ids_to_update)} records")
```

Patch 完成後，`_fmt_courses` 可直接讀 `m.get("topic_tags", "")` 和 `m.get("core_questions", "")`，完全不需要 JSON lookup。

**課程詳細 Modal 不受影響**：`CourseDetailModal` 點開後會呼叫 `/chat/course_detail` API 取得完整的 `course_objective`、`course_content`、`grading` 結構化欄位，這條路不走 `summary`，不需要修改。

**實作位置**：`tools.py:_fmt_courses`，依 `course_code` 前綴（`GS`/`CC`）分支。

---

## Issue 5：通識課 course_code 格式錯誤（serial_no vs course_id）

**現象**

```json
{"code": "1142_09065_GS4539", "name": "資料庫管理與程式操作", ...}
```

`code` 欄位應為純課號 `GS4539`，但實際顯示完整 serial_no（年度_序號_課號）。前端若用 `code` 做連結或查詢會失敗。

**根因**

`_fmt_courses`（tools.py:37）使用 `m.get("course_code", "")`，但 ChromaDB metadata 的 `course_code` 欄位存的是 serial_no（`1142_09065_GS4539`），不是純課號。

**建議修復**

1. **短期**：在 `_fmt_courses` 加後處理，取 `_` 分隔的最後一段：
   ```python
   raw_code = m.get("course_code", "")
   "course_code": raw_code.split("_")[-1] if "_" in raw_code else raw_code,
   ```
2. **長期**：重建 ChromaDB index，`course_code` 欄位只存純課號，`serial_no` 另存一個欄位

---

## Issue 6：search_programs 在 debug_trace 中永遠顯示 count=null

**現象**

debug_trace 的 `search_programs` toolCall 顯示 `count: null, coursesFound: []`，即使工具成功回傳了學程清單。

**根因（雙重 bug）**

1. `llm_service.py` 的 debug_trace 解析區段（lines 892–937）有各工具的 elif 分支，但**沒有 `search_programs`**：
   ```python
   # 有：search_courses, get_dept_courses, find_similar_courses, ppr_explore, get_depts_by_tech
   # 沒有：search_programs ← 導致 count 永遠是 None
   ```
2. `_collect_course_pool` 也沒有 `search_programs` 的 elif 分支（但這是正確的——學程不是課程，不應進入 course_pool）

**建議修復**

在 debug_trace 解析中加入 `search_programs` 的 elif：

```python
elif tc["name"] == "search_programs" and isinstance(result, list):
    count = len(result)
    courses_found = [r.get("program_name", "") for r in result if r.get("program_name")]
    scores = [r.get("distance", 0.0) for r in result]
    score_type = "distance"
```

注意：`_collect_course_pool` 不需要加（學程≠課程，正確做法是不加入 pool）。

**前端補充修復**

後端修好之後，`DebugTracePanel.tsx` 的「找到的課程」標籤（第 117 行）對 `search_programs` 會顯示錯誤標題。需依工具名稱動態切換標籤：

```tsx
// DebugTracePanel.tsx
const resultLabel = t.tool === 'search_programs' ? '找到的學程' : '找到的課程';
// 原本固定寫死 "找到的課程（共 N 門）"，改為：
`${resultLabel}（共 ${t.coursesFound.length} 筆）`
```

分數標示 `d=X.XX`（distance）對學程是正確的，不需要修改。

---

## Issue 7：前端 DebugTracePanel 工具名稱未完整中文化，缺少搜尋方式標示

**現象**

- `search_programs`、`get_graduation_requirements`、`get_course_syllabus` 等新工具顯示英文原名（不在 TOOL_LABELS 中）
- 使用者無法從 UI 判斷工具使用的是向量搜尋、知識圖譜查詢還是精確關鍵字比對

**根因**

`DebugTracePanel.tsx` 與 `CourseSearchPage.tsx` 的 `TOOL_LABELS` 最後更新時間早於新工具加入，缺少：
- `search_programs`（搜尋學分學程）
- `get_graduation_requirements`（查詢畢業規定，取代舊的兩個工具）
- `get_course_syllabus`（查詢課程大綱）

另外目前 `tool_done` SSE 事件沒有搜尋方式欄位，前端無法顯示。

**建議修復**

1. `DebugTracePanel.tsx` 和 `CourseSearchPage.tsx` 的 TOOL_LABELS 補充：
   ```typescript
   search_programs:              '搜尋學分學程',
   get_graduation_requirements:  '查詢畢業規定',
   get_course_syllabus:          '查詢課程大綱',
   ```

2. backend `tool_done` SSE 事件新增 `search_method` 欄位：
   | 工具 | search_method |
   |------|--------------|
   | `search_courses`（向量路徑） | `"vector"` |
   | `search_courses`（tech graph 路徑） | `"graph"` |
   | `search_programs` | `"vector"` |
   | `get_dept_courses`, `ppr_explore`, `find_similar_courses` | `"graph"` |
   | `get_course_eligibility`, `get_graduation_requirements` | `"keyword"` |

3. 前端在工具名稱後顯示搜尋方式小標籤：
   ```tsx
   const METHOD_LABELS = { vector: '向量', graph: '圖譜', keyword: '精確' };
   // 在工具名稱後顯示：搜尋學分學程 [向量]
   ```

---

## 優先順序總覽

| 優先 | Issue | 影響 |
|------|-------|------|
| 🔴 高 | #1 前端子字串誤匹配 | 學程名稱中出現假課程連結，視覺錯亂 |
| 🔴 高 | #6 search_programs count=null | debug 資訊完全缺失，功能性 bug |
| 🟡 中 | #1 filtered_out key 不匹配 | Debug 面板顯示數字錯誤（附帶問題） |
| 🟡 中 | #2 同名課程覆蓋 | 推薦可能指到錯誤系所的同名課程 |
| 🟡 中 | #5 course_code 格式 | 前端課程連結失效 |
| 🟡 中 | #7 前端中文化 + 搜尋方式 | UX 可讀性 |
| 🟢 低 | #3 空字串補充（ChromaDB cross-lookup） | 需批次 IO，有效能影響，但顯著改善課程卡完整度 |
| 🟢 低 | #4 summary 改結構化欄位 | 需較大重構，但對 LLM 判斷品質有顯著提升 |
