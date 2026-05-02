# ReAct Agent 設計

> 主邏輯：`backend/app/services/llm_service.py`  
> 工具實作：`backend/app/services/tools.py`  
> 相關設計文件：`docs/04-agent-tool-design/`

---

## 一、整體架構

```
使用者輸入
    ↓
ReAct Agent（最多 4 輪）
    ├─ 輪次 1：LLM 決策 → [tool_A, tool_B] 並行執行 → 取得結果
    ├─ 輪次 2：LLM 觀察 → [tool_C] → 取得結果
    └─ 輪次 N：LLM 認為資訊足夠 → 直接生成最終回答

LLM 生成回答（SSE 串流）
    └─ 含 <course>課名（系所）</course> 標籤

零幻覺驗證
    └─ regex 擷取標籤 → exact/fuzzy match course_pool → 只保留真實課程

回傳結果
    └─ {answer, course_cards, course_pool, debug_trace, tools_used}
```

---

## 二、ReAct 迴圈機制

### 關鍵參數

| 參數 | 值 | 說明 |
|------|-----|------|
| `max_rounds` | 4 | 最多工具呼叫輪次 |
| `tool_choice` | `"auto"` | LLM 自主決定是否呼叫工具 |
| `MAX_TOKENS` | 2048 | 最終回答最大長度 |
| `model` | GPT-4o | Azure OpenAI |

### 並行工具執行

同一輪中若有多個工具呼叫，使用 `ThreadPoolExecutor` 並行執行，不需等待前一個完成：

```python
with ThreadPoolExecutor(max_workers=len(tool_calls)) as executor:
    futures = {
        executor.submit(execute_tool, tc.function.name, args): tc
        for tc, args in tool_call_args
    }
    for future in as_completed(futures):
        result = future.result()
```

### 對話歷史管理

Session 使用 `messages` 陣列儲存完整對話歷史，每輪都傳入 LLM：

```python
messages = [
    {"role": "system",    "content": SYSTEM_PROMPT},
    {"role": "user",      "content": "第1輪問題"},
    {"role": "assistant", "content": "第1輪回答（+工具呼叫記錄）"},
    {"role": "user",      "content": "第2輪問題"},
    # ...
]
```

---

## 三、14 個工具總表

| 工具 | 分類 | 資料源 | 分數欄位 | 主要用途 |
|------|------|--------|---------|---------|
| `search_courses` | 課程搜尋 | Qdrant + 圖 | `distance` / RRF | 語意搜尋課程；tech 參數走圖精確查詢 |
| `get_course_detail` | 課程搜尋 | Qdrant payload + eligibility | 無 | 完整課綱 + 修課資格 + 先修要求（整合版） |
| `get_dept_courses` | 課程搜尋 | 知識圖譜 | 無 | 系所必修/選修課程清單 |
| `get_dept_info` | 系所 | Qdrant `ncu_departments` | `distance` | 系所介紹（Collego） |
| `get_graduation_requirements` | 系所 | schedule_draft + requirements JSON | 無 | 畢業規定（結構化 + 原文） |
| `search_programs` | 學程 | Qdrant `ncu_credit_programs` | `distance` | 語意搜尋學分學程 |
| `get_program_info` | 學程 | program_descriptions + 圖 | 無 | 學程說明 + 課程清單（整合版） |
| `get_teacher_info` | 教師 | Qdrant + 圖 | 無 | 教師詳情 + 開課清單 |
| `search_teachers` | 教師 | Qdrant `ncu_teachers` | `distance` | 語意搜尋教師 |
| `get_course_knowledge_map` | 圖探索 | 知識圖譜 + RRF | `shared_concepts` | 課程概念地圖 + 相似課程 |
| `find_similar_courses` | 圖探索 | 知識圖譜 + Qdrant | RRF score | 找共享概念最多的相似課程 |
| `get_depts_by_tech` | 圖探索 | 知識圖譜 | 無 | 查哪些系所教授某技術 |
| `ppr_explore` | 圖探索 | 知識圖譜 igraph | PPR `score` | Personalized PageRank 廣泛探索 |
| `explore_concept_neighborhood` | 圖探索 | Qdrant 圖節點 + BFS | 無 | 概念鄰域精確探索（N 跳 BFS） |

---

## 四、Course Pool 累積機制

每個工具執行後，`_collect_course_pool()` 解析結果並累積到 `course_pool`（dict，key = 課程名稱）：

| 工具 | 回傳格式 | 解析方式 |
|------|---------|---------|
| `search_courses` | `list[dict]` | 直接遍歷，取 `name_zh` 為 key |
| `get_dept_courses` | `dict with courses list` | 遍歷 `courses` 列表 |
| `get_program_info` | `dict with courses list` | 遍歷 `courses` 列表 |
| `ppr_explore` | `str` | regex 解析 `[課程] 課名（系所）` 格式 |
| `find_similar_courses` | `str` | regex 解析 `- 課名（系所，N學分）` |

---

## 五、零幻覺機制

傳統 RAG 的課程推薦容易出現幻覺（編造不存在的課程名稱）。本系統用三層防護消除幻覺：

### 5.1 工具層：只回傳真實存在的課程

每個工具只從 Qdrant payload 或知識圖譜節點取得課程資訊，不由 LLM 生成課程名稱。

### 5.2 標籤層：強制 `<course>` 標記

System Prompt 要求 LLM 以標籤標記所有提及的課程：

```
<course>課名（系所）</course>    ← 知道系所時
<course>課名</course>            ← 不知道系所時

規則：
- 必須逐字相同，不縮寫、不改寫
- 只標工具實際回傳課程（不標自己「想到」的課程）
```

### 5.3 驗證層：`_extract_courses_from_tags()`

```
LLM 回答文字（含 <course> 標籤）
    ↓
regex 擷取所有標籤
    ↓
exact match course_pool（按名稱精確比對）
    ↓（若無匹配）
fuzzy match（SequenceMatcher 相似度 ≥ 0.85）
    ↓
dept hint 消歧義（同名課程按系所區分）
    ↓
course_cards：只含 pool 內存在的課程（零幻覺）
```

**效果**：用戶看到的課程卡片永遠是真實存在且工具曾回傳的課程。

---

## 六、SSE 串流事件序列

`/api/chat/stream` 端點使用 Server-Sent Events 即時推送進度：

| 事件類型 | 時機 | 主要欄位 |
|---------|------|---------|
| `tool_start` | 工具開始執行 | `tool`, `args` |
| `tool_done` | 工具執行完畢 | `tool`, `count`, `courses_found`, `scores`, `score_type` |
| `token` | LLM 生成每個 token | `text` |
| `verify_start` | tag 提取開始 | `pool_size` |
| `verify_done` | tag 提取完成 | `method="tag"`, `selected`, `filtered_out` |
| `done` | 全部完成 | `session_id`, `course_cards`, `course_pool`, `tools_used`, `debug_trace` |
| `error` | 任何錯誤 | `message` |

---

## 七、Session 儲存設計

### 7.1 儲存位置

```
data/sessions/{session_id}.json
```

session_id：32 字元 UUID（hex）

### 7.2 雙軌設計

**`messages` — LLM 對話歷史（扁平格式）**：
- 每次對話都傳入 LLM（完整上下文）
- 不含 tool call 詳情，只存 LLM 最終回答
- 不含 course_cards 等 UI 資料

**`turns` — 前端顯示結構（結構化格式）**：

```json
{
  "user": "問題",
  "assistant": "回答",
  "course_cards": [...],
  "course_pool": [...],
  "debug_trace": {"toolCalls": [...]},
  "tools_used": ["search_courses", "ppr_explore"],
  "created_at": "2026-05-01T12:00:00"
}
```

### 7.3 API 操作

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/chat` | 同步聊天 |
| POST | `/api/chat/stream` | SSE 串流聊天 |
| POST | `/api/chat/course_detail` | 依課名查詢完整課程資訊 |
| GET | `/api/chat/sessions` | 列出所有對話（最近 50 個） |
| GET | `/api/chat/session/{id}` | 取得特定對話 |
| DELETE | `/api/chat/session/{id}` | 刪除對話 |

---

## 八、System Prompt 設計重點

### 角色定義

```
你是「中央大學選課助理」，一個專門協助中央大學學生查詢課程資訊、
規劃學習路徑、探索科系的智慧助理。
語氣：友善、簡潔、專業
語言：繁體中文
```

### Filter 使用原則

| Filter | 使用條件 |
|--------|---------|
| `dept` | 使用者明確說「XX系的課」時才加；不要主動猜測 |
| `course_type` | 明確說「選修」「必修」才加 |
| `exclude_grad_only` | 預設 true（隱藏研究所限定課程） |
| `college` | 使用者說「某學院的課」時才加 |

### 系所名稱規範

- 使用正式全名（不可縮寫）
- 通識課：「通識教育中心」（不是「通識」）
- 外語課：「語言中心」（不是「外文系」）
- 研究所：「資訊工程學系碩士班」（不是「資工所」）

### 工具選用範例（10 個）

| 情境 | 工具選擇 |
|------|---------|
| 技術查詢 | `search_courses(tech="Python")` + `get_depts_by_tech(tech="Python")` |
| 系所課程 | `get_dept_courses(dept="資訊工程學系")` |
| 主題搜尋 | `search_courses(query="機器學習相關課程")` |
| 學程發現 | `search_programs(query="AI 相關")` → `get_program_info(name="...")` |
| 先修查詢 | `get_course_detail(course_name="資料結構")` |
| 廣泛探索 | `ppr_explore(seed="深度學習", focus="course")` |
| 教師查詢 | `search_teachers(query="電腦視覺專長")` → `get_teacher_info(name="...")` |
| 概念鄰域 | `explore_concept_neighborhood(concept="強化學習", depth=2)` |
| 相似課程 | `find_similar_courses(course_name="人工智慧")` |
| 畢業規定 | `get_graduation_requirements(dept="資訊工程學系")` |

---

## 九、前端三欄 Layout

```
┌────────────┬──────────────────────────┬──────────────┐
│  左側欄    │      聊天區域            │  右側面板    │
│  (320px)   │    (flex-1)              │   (280px)    │
│            │                          │              │
│  對話紀錄  │  訊息泡泡（Markdown）    │  推薦課程    │
│  列表      │  + DebugTracePanel       │  卡片列表    │
│            │                          │              │
│ 預設收合   │  輸入框                  │  lg:flex     │
└────────────┴──────────────────────────┴──────────────┘
```

- **左側欄**：預設收合，顯示歷史對話列表（可新增/刪除）
- **聊天區域**：SSE 串流輸出（逐字顯示），每則訊息下方有 DebugTracePanel 按鈕
- **右側面板**：永久顯示最新一輪的推薦課程卡片（手機版隱藏）

---

## 十、LangSmith 監控（可選）

若設定 `LANGSMITH_API_KEY` 環境變數，系統自動啟用 LangSmith 追蹤：

```python
if os.getenv("LANGSMITH_API_KEY"):
    from langsmith import wrap_openai
    client = wrap_openai(AzureOpenAI(...))
```

追蹤內容：每次 LLM 呼叫的輸入/輸出、token 用量、延遲時間、工具呼叫序列。
