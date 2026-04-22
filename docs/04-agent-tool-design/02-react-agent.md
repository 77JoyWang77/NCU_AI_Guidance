# ReAct Agent 流程設計

> 文件版本：2026-04-21

---

## ReAct 迴圈概述

系統採用 **ReAct（Reason → Act → Observe）** 框架，LLM 在每輪自主決定要呼叫哪些工具，觀察結果後再決定是否繼續。

```
輪次 1：LLM 思考 → 決定呼叫 [tool_A, tool_B] → 並行執行 → 取得結果
輪次 2：LLM 觀察結果 → 決定再呼叫 [tool_C] 或直接回答
輪次 3：...（最多 4 輪）
```

### 關鍵參數

| 參數 | 值 | 說明 |
|------|-----|------|
| `max_rounds` | 4 | 最多迭代輪次 |
| `tool_choice` | `"auto"` | LLM 自主決定是否呼叫工具 |
| `MAX_TOKENS` | 2048 | 每次 LLM 呼叫的最大輸出 token |
| `model` | `AZURE_OPENAI_CHAT_DEPLOYMENT`（gpt-4o） | 對話模型 |

---

## 並行工具執行

同一輪中 LLM 若決定呼叫多個工具，系統使用 `ThreadPoolExecutor` 並行執行，不需等待前一個工具完成：

```python
with ThreadPoolExecutor() as pool:
    futures = {pool.submit(execute_tool, tc.name, args): tc for tc in tool_calls}
    for future in futures:
        result = future.result()
```

**效益**：詢問「資工系有哪些必修課？老師有誰？」時，`get_dept_courses` 和 `search_teachers` 同時執行，減少等待時間。

---

## 停止條件

1. LLM 本輪不再呼叫任何工具（`finish_reason == "stop"` 或 tool_calls 為空）
2. 達到 `max_rounds=4` 上限

---

## course_pool 累積機制

每個工具執行後，`_collect_course_pool()` 解析回傳結果並累積到 `course_pool`（dict，key = 課程名稱）：

```python
course_pool: dict[str, CourseCard]  # {課名: CourseCard dict}
```

### 各工具的解析策略

| 工具名稱 | 回傳格式 | 解析方式 |
|---------|---------|---------|
| `search_courses` | `list[dict]` | 直接遍歷，取 `name_zh` 為 key |
| `get_dept_courses` | `dict` with `courses` list | 遍歷 `courses` 列表 |
| `get_program_courses` | `dict` with `courses` list | 同上 |
| `get_course_eligibility` | `dict` with `courses` list | 遍歷 `courses` 列表 |
| `ppr_explore` | `str` | regex 解析 `[課程] 課名（系所）` 格式 |
| `find_similar_courses` | `str` | regex 解析 `- 課名（系所，N學分）` 格式 |
| `get_course_knowledge_map` | `str` | 同上 |
| `get_depts_by_tech` | `str` | regex 解析「相關課程」段落 |

其餘工具（`get_teacher_info`, `get_dept_info`, `get_graduation_rules` 等）不產出課程到 pool。

---

## `_verify_course_list()` — 零幻覺驗證

### 目的

ReAct 迴圈結束、LLM 生成回答後，再進行一次獨立的 LLM 呼叫，從 `course_pool` 中選出真正相關的課程作為 `course_cards`。

### 設計原則

**LLM 只能從 pool 清單中選，不能輸出清單外的課程名稱 → 確保零幻覺**

### 流程

```
course_pool（最多取 60 筆）
    │
    ▼
prompt 包含：
  - 使用者問題
  - 助理回答節錄（前 600 字）
  - pool 課程清單（課名 + 系所 + 學分）
    │
    ▼
LLM 呼叫（temperature=0, max_tokens=300, 同一個 gpt-4o deployment）
    │
    ▼
回傳：每行一個課程名稱
    │
    ▼
逐行與 pool_map 比對（只保留 pool 內存在的課名）
    │
    ▼
course_cards: list[CourseCard]
```

### 關鍵參數

| 參數 | 值 |
|------|-----|
| `temperature` | 0（確定性輸出） |
| `max_tokens` | 300 |
| `pool_items` 最大量 | 60 筆 |

### 為什麼有效

即使 LLM 在回答文字中「幻覺」出不存在的課程名稱（如從訓練知識中捏造），`_verify_course_list` 的輸出結果仍只包含 pool 內真實存在的課程，因此 `course_cards`（前端顯示的推薦卡片）永遠不會出現幻覺課程。

---

## 串流事件設計（SSE）

`stream_with_tools()` 透過 SSE 即時推送每個步驟：

| 事件類型 | 時機 | 主要欄位 |
|---------|------|---------|
| `tool_start` | 每個工具開始執行前 | `tool`, `args` |
| `tool_done` | 每個工具執行完成後 | `tool`, `count`, `courses_found` |
| `token` | LLM 生成文字每個 token | `text` |
| `verify_start` | 驗證開始前 | `pool_size` |
| `verify_done` | 驗證完成後 | `selected`, `filtered_out` |
| `done` | 全部完成 | `session_id`, `course_cards`, `course_pool`, `course_pool_count`, `has_large_result`, `model`, `input_tokens`, `output_tokens` |
| `error` | 任何錯誤 | `message` |

---

## SYSTEM_PROMPT 重要指引

```
- 語言：繁體中文，語氣友善
- 不捏造課程名稱或數字
- context 不足時誠實說明
- 技術查詢：必須傳 tech 參數（觸發 graph-first 精確查詢）
- 平行查詢策略：學程同時呼叫 description + courses
- Fallback：空結果時換關鍵字 / 換工具
```

---

## 對話歷史管理

Session 使用 `messages` 陣列儲存完整對話歷史，每輪都傳入 LLM：

```python
messages = [
    {"role": "system",    "content": SYSTEM_PROMPT},
    {"role": "user",      "content": "第1輪問題"},
    {"role": "assistant", "content": "第1輪回答"},
    {"role": "user",      "content": "第2輪問題"},
    # ...
]
```

每輪 ReAct 完成後，工具呼叫結果也會作為 `tool` role messages 加入歷史，確保下一輪 LLM 能看到完整上下文。
