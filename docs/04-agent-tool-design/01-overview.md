# 系統架構總覽

> 文件版本：2026-04-23

---

## 系統目的

**中央大學選課助理**（NCU Course Advisor）是一個針對中央大學課程資訊的 GraphRAG 對話系統，協助高中生探索科系、大學生規劃選課、了解學程與畢業規定。

---

## 技術棧

| 層次 | 技術 |
|------|------|
| 後端框架 | FastAPI（Python 3.11+） |
| LLM | Azure OpenAI GPT-4o（`AZURE_OPENAI_CHAT_DEPLOYMENT`） |
| 向量資料庫 | ChromaDB（Euclidean distance） |
| 知識圖譜 | NetworkX（載入自 `knowledge_graph.json`） |
| 前端框架 | React 19 + TypeScript + Tailwind CSS |
| 監控 | LangSmith（選填） |
| Session 儲存 | JSON 檔案（`data/sessions/`） |

---

## 資料源

### 1. ChromaDB 向量資料庫

| Collection | 內容 | 用途 |
|-----------|------|------|
| `ncu_courses_ug` | 大學部課程嵌入（含 metadata） | 課程語意搜尋 |
| `ncu_courses_grad` | 研究所課程嵌入 | 研究所課程搜尋 |
| `ncu_teachers` | 教師專長嵌入 | 教師搜尋 |
| `ncu_departments` | 系所介紹嵌入（Collego 資料） | 系所說明搜尋 |
| `ncu_credit_programs` | 學分學程嵌入 | 學程語意搜尋 |

**課程 metadata 欄位（含課綱）**：每筆課程記錄除基本欄位外，另含 `objective`（課程目標）、`content`（授課內容）、`textbook`（教科書/參考書）三個欄位，由 `update_syllabus_metadata.py` 獨立更新（不需重新嵌入向量）。

### 2. 知識圖譜（NetworkX）

載入自 `data/processed/graph/knowledge_graph.json`，節點類型包含：

- `Course`：課程節點
- `Instructor`：教師節點
- `Department / DeptGroup / CollegeBachelorProgram`：系所節點
- `CreditProgram`：學分學程節點
- `Concept / Technology / Field`：知識概念節點
- `CurriculumPlan / ElectiveGroup / Slot`：課程規劃節點

### 3. 靜態 JSON 資料

| 檔案 | 內容 |
|------|------|
| `data/processed/program_descriptions.json` | 學分學程說明文字 |
| `data/processed/requirements_notes.json` | 系所畢業規定原文 |
| `data/processed/schedule_draft/` | 課程規劃草稿（畢業學分） |

---

## 資料流

```
使用者問題
    │
    ▼
Stage 1 — ReAct Agent（最多 4 輪）
    │  ┌─────────────────────────────────────────┐
    │  │  每輪：LLM 決定呼叫哪些工具              │
    │  │  ThreadPoolExecutor 並行執行             │
    │  │  工具回傳結果 → course_pool 累積         │
    │  └─────────────────────────────────────────┘
    │
    ▼
Stage 1 結束：LLM 生成回答（含所有工具結果為 context）
    │
    ▼
_verify_course_list()
    │  從 course_pool（最多 60 門）讓 LLM 選出真正相關的課程
    │  LLM 只能選 pool 內的課程 → 零幻覺
    │
    ▼
回傳 {answer, course_cards, session_id, ...}
```

> **規劃中：兩階段設計（Stage 1 + Stage 2）**  
> 目前 Stage 1 的 ReAct agent 同時負責工具呼叫與最終回覆生成。規劃將回覆生成抽離為獨立的 Stage 2 agent，Stage 1 只管資料收集，Stage 2 以乾淨的 context 生成友善回答，並以 `<course>課名</course>` 標籤標記提到的課程，取代現有的 `_verify_course_list` LLM 呼叫。詳見 `06-known-issues.md` 兩階段設計節。

---

## 前端三欄 Layout

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

- **左側欄**：預設收合，顯示歷史對話列表
- **聊天區域**：SSE 串流輸出，每則訊息下方有 DebugTracePanel 按鈕
- **右側面板**：永久顯示最新一輪回答的推薦課程，手機版隱藏（`lg:flex`）

---

## 工具清單（18 個）

| 類別 | 工具 | 說明 |
|------|------|------|
| 課程搜尋 | `search_courses` | 語意搜尋 + ChromaDB 過濾 |
| 課程搜尋 | `get_course_syllabus` | 官方課綱（目標/內容/教科書） |
| 課程搜尋 | `get_course_eligibility` | 修課資格限制（raw_conditions 原文） |
| 課程搜尋 | `get_prereq_info` | 先修條件展開 |
| 系所 | `get_dept_courses` | 必/選修課程列表 |
| 系所 | `get_dept_info` | 系所特色介紹（Collego） |
| 系所 | `get_graduation_requirements` | 畢業規定（結構化+原文，整合版） |
| 學程 | `get_program_courses` | 學程必/選修清單 |
| 學程 | `get_program_description` | 學程完整說明文字 |
| 學程 | `search_programs` | 語意搜尋學分學程 |
| 教師 | `get_teacher_info` | 教師詳情 + 開課清單 |
| 教師 | `search_teachers` | 語意搜尋教師專長 |
| 圖探索 | `get_course_knowledge_map` | 課程知識地圖（概念+技術） |
| 圖探索 | `find_similar_courses` | 共享概念最多的相似課程 |
| 圖探索 | `get_depts_by_tech` | 技術分布到哪些系所 |
| 圖探索 | `ppr_explore` | PageRank 廣泛探索 |

---

## SSE 串流事件序列

```
tool_start(tool, args) → tool_done(tool, count, courses_found) → 
[重複多輪] → verify_start(pool_size) → verify_done(selected, filtered_out) → 
done(session_id, course_cards, course_pool, ...)
```

---

## API 端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/chat` | 同步聊天（含完整 ReAct + verify） |
| POST | `/api/chat/stream` | SSE 串流聊天 |
| POST | `/api/chat/course_detail` | 依課名查詢完整課程資訊 |
| GET  | `/api/chat/sessions` | 列出所有對話紀錄 |
| GET  | `/api/chat/session/{id}` | 取得特定對話的完整 turns |
| DELETE | `/api/chat/session/{id}` | 刪除對話 |
