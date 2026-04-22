# 已知問題與下一步規劃

> 文件版本：2026-04-21

---

## 問題 A：Markdown 未渲染

### 現象

LLM 回答使用 `###`、`**粗體**`、`- 條列` 等 Markdown 語法，但前端 `HighlightedAnswer.tsx` 以純文字渲染，使用者看到的是原始符號。

### 根本原因

`HighlightedAnswer.tsx` 的 `buildSegments()` 函式將文字分割為「普通文字」和「高亮課程名稱」兩種 segment，渲染時直接輸出 `<span>`，沒有 Markdown 解析。

### 計畫解法

1. 安裝 `react-markdown` + `remark-gfm`
2. 在每個普通文字 segment 內套用 `<ReactMarkdown>` 渲染
3. 保留課程名稱高亮邏輯（在 Markdown 渲染後的文字節點中做高亮）

```tsx
// 概念示意
<ReactMarkdown remarkPlugins={[remarkGfm]}>
  {plainTextSegment}
</ReactMarkdown>
```

**注意**：`<course_list>` tag 已在渲染前過濾，不影響 Markdown 顯示。

---

## 問題 B：Debug 面板缺少分數

### 現象

前端 `DebugTracePanel` 顯示每個工具找到的課程名稱，但沒有顯示相似度分數（`distance`/`shared_concepts`/`score`）。

### 根本原因

後端 `tool_done` SSE 事件只傳遞 `courses_found`（課程名稱列表），沒有附帶對應的分數陣列。

### 計畫解法

#### 後端修改（`llm_service.py`）

在 `_collect_course_pool()` 中新增 `scores` 記錄，並在 `stream_with_tools()` 的 `tool_done` 事件傳遞：

```python
# tool_done 事件新增 scores 欄位
yield json.dumps({
    "type": "tool_done",
    "tool": tool_name,
    "count": len(courses_found),
    "courses_found": courses_found[:8],
    "scores": scores[:8],         # 新增：與 courses_found 一一對應
    "score_type": "distance"      # 新增：分數類型（distance/shared_concepts/ppr）
})
```

#### 前端修改

- `StreamEvent` 型別新增 `scores?: number[]`, `score_type?: string`
- `ToolTraceItem` 型別新增 `scores: number[]`, `scoreType: string`
- `DebugTracePanel` 在課程 badge 後顯示分數

```tsx
// 顯示示意
<span className="badge bg-blue-50 text-blue-700">
  {name}
  <span className="text-xs text-blue-400 ml-1">
    {scoreType === 'distance' ? `d=${score.toFixed(2)}` : 
     scoreType === 'shared_concepts' ? `c=${score}` : 
     `ppr=${score.toFixed(1)}`}
  </span>
</span>
```

---

## 問題 C：工具組合不完整（最重要）

### 現象

詢問「有沒有和深度學習概念重疊最高的課程？」時：
- LLM 只呼叫 `get_course_knowledge_map(course_name="深度學習")`
- 回傳 8 門概念相似課程（pool 中無「深度學習程式設計」等課程）
- LLM 在回答文字中提到「深度學習程式設計（通訊工程學系）」→ **幻覺**（不在 pool 中）
- `_verify_course_list` 正確地將其排除出 `course_cards`

### 問題根源

**LLM 應同時呼叫** `search_courses(query="深度學習")` 才能找到名稱中直接含「深度學習」的課程，但 SYSTEM_PROMPT 沒有明確指示。

### 計畫解法

在 SYSTEM_PROMPT 的「Tool 選用指引」中加入概念查詢組合策略：

```
**概念查詢組合策略**：
使用者問「有沒有和 X 概念重疊的課程」或「有哪些 X 相關課程」時，
請同時呼叫：
1. `get_course_knowledge_map(course_name="X")` — 找概念圖譜相似課程
2. `search_courses(query="X")` — 找名稱直接含 X 的課程
兩者結果取聯集，確保不遺漏名稱直接含關鍵字的課程。
```

### 驗證方式

問「有沒有和深度學習概念重疊最高的課程？」後，Debug panel 應同時看到：
- `get_course_knowledge_map`（8 門概念相似課程）
- `search_courses`（名稱含「深度學習」的課程，如「深度學習程式設計」）

---

## 問題 D：Session 儲存不完整

### 現象

1. `course_cards` 常有 `code`、`teacher`、`summary` 欄位為空字串
2. 無 `debug_trace`：重新載入對話後，DebugTracePanel 為空
3. 無完整 `course_pool`：「查看全部 N 門課程」的 drawer 無法從歷史記錄恢復

### 計畫解法

詳見 `05-session-storage.md` 的「問題與待補強欄位」章節。

核心修改：
1. `_verify_course_list()` 後對空欄位的 cards 呼叫 `retriever.get_courses_by_name()` 補全
2. `session_store.save()` 新增 `debug_trace` 和 `course_pool` 參數
3. `GET /chat/session/{id}` 回傳時包含 `debug_trace`

---

## 問題 E：PPR score 未顯示在工具結果字串中

### 現象

`ppr_explore` 的回傳字串格式：
```
以「深度學習」為起點的 PPR 探索結果（all 模式）：
  [課程] 機器學習（資訊工程學系）
  [教師] 王教授（資訊工程學系）
```

**看不到 score 數值**，使用者無法判斷各節點的相關程度。

### 計畫解法

在 `tool_ppr_explore()` 的格式化輸出中加入 score：

```python
lines.append(f"  [{label}] {name}{extra}  score={r['score']}")
```

或在 DebugTracePanel 中透過問題 B 的 `scores` 欄位顯示。

---

## 後續開發優先順序建議

| 優先 | 問題 | 預估工作量 | 影響 |
|------|------|----------|------|
| P1 | 問題 A：Markdown 渲染 | 小（安裝套件 + 修改 1 個 component） | 顯示品質大幅提升 |
| P1 | 問題 C：工具組合 | 小（修改 SYSTEM_PROMPT 一段） | 搜尋結果完整性 |
| P2 | 問題 B：Debug 分數 | 中（後端 SSE + 前端 UI） | 開發除錯體驗 |
| P2 | 問題 D：Session 儲存 | 中（後端補全邏輯） | 歷史記錄完整性 |
| P3 | 問題 E：PPR score 顯示 | 小（修改格式化字串） | Debug 可讀性 |
