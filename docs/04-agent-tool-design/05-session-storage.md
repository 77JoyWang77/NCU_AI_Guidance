# Session 儲存設計

> 文件版本：2026-05-02  
> 來源：`backend/app/services/session_store.py`，`backend/app/routes/chat.py`

---

## 儲存位置

```
data/sessions/{session_id}.json
```

- `session_id`：32 字元 UUID（hex，無連字符），如 `aa298156fc684c199bb1af9bc43751be`
- 每個 session 一個 JSON 檔案

---

## JSON 結構

```json
{
  "session_id": "aa298156fc684c199bb1af9bc43751be",
  "title": "有沒有和深度學習概念重疊最高的課程",
  "created_at": "2026-04-21T10:30:00.000Z",
  "updated_at": "2026-04-21T10:35:00.000Z",
  "messages": [
    {"role": "user",      "content": "有沒有和深度學習概念重疊最高的課程？"},
    {"role": "assistant", "content": "根據知識圖譜分析..."}
  ],
  "turns": [
    {
      "user": "有沒有和深度學習概念重疊最高的課程？",
      "assistant": "根據知識圖譜分析...",
      "course_cards": [
        {
          "code": "CS3001",
          "name": "機器學習",
          "dept": "資訊工程學系",
          "credits": 3,
          "type": "選修",
          "teacher": "王教授",
          "summary": "課程摘要..."
        }
      ],
      "course_pool": [
        {
          "code": "CS3001",
          "name": "機器學習",
          "dept": "資訊工程學系",
          "credits": 3
        }
      ],
      "debug_trace": {
        "toolCalls": [
          {
            "tool": "get_course_knowledge_map",
            "args": {"course_name": "深度學習"},
            "coursesFound": ["機器學習", "電腦視覺"],
            "count": 8,
            "scores": [0.91, 0.87],
            "scoreType": "rrf"
          }
        ]
      },
      "tools_used": ["get_course_knowledge_map"],
      "created_at": "2026-04-21T10:30:00.000Z"
    }
  ]
}
```

---

## 雙軌設計說明

### `messages` — LLM 對話歷史（扁平格式）

```python
messages = [
    {"role": "system",    "content": SYSTEM_PROMPT},
    {"role": "user",      "content": "第1輪問題"},
    {"role": "assistant", "content": "第1輪回答"},
    {"role": "user",      "content": "第2輪問題"},
    ...
]
```

- **用途**：每次對話都傳入 LLM，提供完整對話上下文
- **不含** tool call 詳情（只存 LLM 最終回答）
- **不含** course_cards 等 UI 資料

### `turns` — 前端顯示結構（結構化格式）

```python
{
    "user": str,
    "assistant": str,
    "course_cards": list[CourseCard],   # tag 提取後的精選課程
    "course_pool": list[CourseCard],    # 完整 pool（含未被選中的）
    "debug_trace": {                    # 工具呼叫詳情（串流路徑才有）
        "toolCalls": list[ToolCallLog]  # {tool, args, coursesFound, count, scores, scoreType}
    },
    "tools_used": list[str],
    "created_at": str
}
```

- **用途**：前端載入歷史對話時，恢復完整顯示（含課程卡片、debug trace）
- **獨立於** `messages`，不影響 LLM context
- `debug_trace` 由串流路徑（`stream_with_tools`）填充；同步路徑（`generate_with_tools`）目前為 `{}`

---

## title 生成規則

- 取**第一輪**使用者問題的前 40 個字元
- 若第一輪後才修改 session，title 不更新

---

## API 操作

### 建立/更新 session

```python
session_store.save(
    session_id=session_id,
    user_msg=question,
    assistant_msg=answer,
    course_cards=course_cards,
    course_pool=list(course_pool.values()),
    debug_trace=debug_trace,
    tools_used=tools_used,
)
```

### 讀取 session 列表

```
GET /api/chat/sessions
```

回傳：最近 50 個 sessions，依 `updated_at` 降序排列

```json
[
  {"session_id": "...", "title": "...", "updated_at": "...", "turn_count": 3}
]
```

### 讀取特定 session

```
GET /api/chat/session/{session_id}
```

回傳完整 `turns` 陣列（含 course_cards）

---

## 前端恢復邏輯

載入歷史對話時（`handleSelectConversation`）：

1. 呼叫 `GET /api/chat/session/{id}` 取得 turns
2. 將每個 turn 轉換為 `Conversation.messages` 格式
3. 從最後一個 turn 的 `course_cards` 恢復右側推薦面板
