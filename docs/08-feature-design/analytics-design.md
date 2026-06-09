# 個人學習傾向分析頁面設計說明

> 路由：`/profile`　需登入（Firebase JWT）

---

## 整體架構

頁面分為三個分頁，右上角以膠囊式 Tab 切換，預設顯示「全部」：

| Tab | 說明 |
|-----|------|
| 全部 | 課程助理 + 研究計畫的跨系統綜合分析 |
| 課程助理 | 課程探索行為分析（對話、工具、系所、領域） |
| 研究計畫 | PDF Chat 探索行為分析（論文、系所、對話深度） |

**懶載入策略：** 切換到某個 Tab 時才發 API，已載入的不重複請求。「全部」Tab 同時並行發兩個請求，等兩者都回來才呈現（避免分波動畫）。

**數字動畫：** 所有統計卡片在資料載入後以 ease-out cubic 從 0 滾動至目標值（900ms）。

---

## 資料來源

### 課程助理（`GET /api/chat/analytics`）

| 資料表 | 欄位 | 用途 |
|--------|------|------|
| `chat_turns.course_pool` | JSONB 陣列 | 系所分佈、課程領域、唯一課程數 |
| `chat_turns.course_cards` | JSONB 陣列 | `domain_tags` 興趣標籤 |
| `chat_turns.tools_used` | JSONB 陣列 | 工具使用頻率（規劃工具比例） |
| `chat_sessions` | `user_id` | session 計數 |
| `user_analytics` | `data`, `computed_at` | 15 分鐘快取 |

額外靜態資料（`lru_cache`，只載入一次）：
- `course_index.json` → 課程官方領域
- `nlp_topic_tags.json` → 通識主題標籤

### 研究計畫（`GET /api/projects/analytics`）

| 資料表 | 欄位 | 用途 |
|--------|------|------|
| `pdf_conversations` | `user_id`, `document_id`, `thread_id`, `created_at` | 對話列表 |
| `pdf_agent_messages` | `thread_id`, `user_id`, `user_question`, `created_at` | 訊息計數、最近提問 |
| `user_pdf_analytics` | `data`, `computed_at` | 15 分鐘快取 |
| `projects.json`（靜態） | `documentId`, `title`, `department`, `year` | 論文詮釋資料（`lru_cache`） |

**查詢優化：** `pdf_agent_messages` 不做全欄 ORM 撈取（`agent_answer` 等大欄位），改用兩條 SQL：
- `GROUP BY thread_id COUNT(*)` 取各 thread 訊息數
- `SELECT thread_id, user_question, created_at ... LIMIT 10` 取最近提問

---

## 後端 API

### `GET /api/chat/analytics`

```jsonc
{
  "overview": {
    "total_sessions": 12,
    "total_turns": 47,
    "total_courses_explored": 183,
    "fav_college": "資訊電機學院"
  },
  "dept_distribution": [{ "name": "資訊工程學系", "count": 42, "pct": 23.1 }],
  "college_distribution": [{ "name": "資訊電機學院", "count": 89, "pct": 48.6 }],
  "tool_usage": [{ "tool": "search_courses", "label": "課程語意搜尋", "count": 31 }],
  "top_domain_tags": [{ "tag": "機器學習", "count": 18 }],
  "top_course_domains": [{ "domain": "基礎學科", "count": 12 }],
  "general_edu": {
    "total": 23,
    "categories": [{ "name": "通識", "count": 10 }],
    "top_topic_tags": [{ "tag": "歷史", "count": 4 }]
  }
}
```

### `GET /api/projects/analytics`

```jsonc
{
  "overview": {
    "total_conversations": 8,
    "total_questions": 34,
    "total_documents_explored": 5,
    "avg_depth": 4.3
  },
  "dept_distribution": [{ "name": "資訊工程學系", "count": 3, "pct": 37.5 }],
  "college_distribution": [{ "name": "資訊電機學院", "count": 5, "pct": 62.5 }],
  "depth_distribution": [
    { "range": "1–2 輪", "count": 2 },
    { "range": "3–5 輪", "count": 4 },
    { "range": "6+ 輪",  "count": 2 }
  ],
  "exploration_type": { "type": "深度鑽研型", "desc": "..." },
  "document_list": [{
    "document_id": 42, "title": "...", "department": "資訊工程學系",
    "college": "資訊電機學院", "year": "112",
    "conversation_count": 3, "question_count": 12, "avg_depth": 4.0,
    "last_viewed_at": "2025-04-20T10:30:00"
  }],
  "recent_questions": [{ "question": "...", "document_title": "...", "created_at": "..." }]
}
```

---

## 快取機制

兩套快取邏輯完全對稱：

```
GET /api/chat/analytics（或 /projects/analytics）
  → 查 user_analytics（或 user_pdf_analytics）
      WHERE computed_at > now() - 900s（15 分鐘）
  → 命中 → 直接回傳（O(1)）
  → 未命中 → 全量計算 → UPSERT 快取 → 回傳
```

強制重算：`UPDATE user_analytics SET computed_at = to_timestamp(0)`

---

## 頁面佈局

### 全部 Tab

```
概覽卡片 × 4（課程對話 / 研究計畫對話 / 課程提問 / 探索論文）

┌─────────────────────────┬─────────────────────────┐
│  綜合學術領域分佈        │  綜合探索型態診斷        │
│  六角雷達圖              │  型態 badge + 文字說明   │
│  ＋ 加權 / 等比 切換     │                         │
└─────────────────────────┴─────────────────────────┘

使用偏好分析（全寬）
  課程助理 vs 研究計畫互動比例 + 各自平均對話深度
```

### 課程助理 Tab

```
概覽卡片 × 4（對話次數 / 提問輪次 / 探索課程 / 最常探索學院）
學術探索領域（雷達）｜ 課程探索型態診斷
課程探索領域 WordCloud ｜ 課程領域分佈 WordCloud
探索系所分佈（Pie）｜ 通識與一般選修（圓形環）
```

### 研究計畫 Tab

```
概覽卡片 × 4（對話次數 / 提問次數 / 探索論文數 / 平均對話深度）
探索學院雷達圖 ｜ 研究探索型態診斷
探索系所分佈（Pie）｜ 對話深度分佈（Bar）
論文探索列表（最多 8 筆）
最近提問（最新 10 筆）
```

---

## 探索型態診斷邏輯

### 課程助理（前端診斷）

前置保護：`total_turns < 3` → 直接回傳均衡探索型。

| 型態 | 條件 |
|------|------|
| 規劃導向型 | 規劃工具呼叫數 / 所有工具呼叫數 **≥ 25%** |
| 跨域探索型 | ≥ 3 個領域實際佔比 ≥ 15% |
| 專注深挖型 | 最集中系所佔比 **> 55%** 且系所數 ≤ 4 |
| 廣泛探索型 | 探索系所 **≥ 6** 個，最集中系所 **< 30%** |
| 均衡探索型 | 預設 |

規劃工具：`get_graduation_requirements`, `get_graduation_rules`, `get_program_info`, `get_program_courses`, `get_requirements_notes`

### 研究計畫（後端診斷）

| 型態 | 條件 |
|------|------|
| 深度鑽研型 | `avg_depth ≥ 4`，或 `avg_depth ≥ 3` 且論文數 ≤ 2 |
| 跨域探索型 | 涉及學院數 **≥ 3** 且總對話數 **≥ 3** |
| 廣泛涉獵型 | 論文數 ≥ 5 且 `avg_depth < 2.5` |
| 專注研究型 | 最集中系所佔比 > 70% |
| 均衡探索型 | 預設 |

### 綜合（前端診斷）

`coursePct` = 課程助理互動量佔總互動量比例。

| 型態 | 條件 |
|------|------|
| 學術研究導向 | `researchPct > 60%` 且研究計畫 `avg_depth ≥ 2` |
| 課程規劃導向 | `coursePct > 60%` 且規劃工具比例 ≥ 25% |
| 課程探索導向 | `coursePct > 60%`（無明顯規劃工具使用） |
| 跨域整合型 | 跨系統合計 ≥ 3 個學院、≥ 3 個主要領域 |
| 廣泛探索型 | 兩系統合計涉足系所 ≥ 8 個 |
| 均衡發展型 | 預設 |

---

## 學術領域對照

六軸雷達圖的學院 → 領域對應：

| 軸 | 涵蓋學院 | 顏色 |
|----|---------|------|
| 理工 | 理學院、工學院、永續與綠能科技研究學院 | `#6366f1` |
| 資訊 | 資訊電機學院 | `#0ea5e9` |
| 地科 | 地球科學學院 | `#a16207` |
| 生醫 | 生醫理工學院 | `#10b981` |
| 人文 | 文學院、客家學院 | `#f59e0b` |
| 商管 | 管理學院 | `#ef4444` |

「中心、處室」不計入雷達圖。

綜合雷達圖提供**加權**（依互動量比例混合）與**等比**（各佔 50%）兩種計算模式供切換。

---

## 通識與一般選修分類

| 類別 | 涵蓋系所 |
|------|---------|
| 通識 | 通識教育中心、核心通識課程、總教學中心、台灣聯大AI學程、環境科技學程、遙測學程 |
| 外語 | 語言中心 |
| 體育 | 體育室、軍訓室 |
| 服務學習 | 學務處-服務學習發展中心、學務處-職涯發展中心 |

僅在 `categories.length > 0` 或 `top_topic_tags.length > 0` 時顯示此卡片。
