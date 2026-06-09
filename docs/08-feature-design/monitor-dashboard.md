# 開發人員監控儀表板設計文件

## 概覽

`/monitor` 是僅供開發人員存取的系統監控頁面，採用深色主題（Grafana 風格），整合 PostgreSQL、Qdrant、Cloudinary、Azure OpenAI 等服務的即時狀態與統計資料，**同時監控課程推薦與大專生計畫兩個 AI 功能**，無需登入外部平台即可掌握系統健康。

---

## 存取控制

| 機制 | 說明 |
|------|------|
| 後端 | `DEVELOPER_EMAILS` 環境變數（逗號分隔），`GET /api/monitor/*` 驗證 Firebase token 後比對 email，非開發人員回傳 403 |
| 前端 | `isDeveloper(email)` 比對 `VITE_DEVELOPER_EMAILS`，非開發人員自動導向首頁，Navbar 也不顯示入口 |

---

## 頁面結構

### 固定頂欄
```
系統監控  ● 正常    ● Render  ·  ● PostgreSQL  ·  ● Qdrant  ·  ● /api/chat 142ms
[30s][1m][5m]  [↺]
```
- 系統狀態燈（全部正常 / 異常）
- 各服務健康點（Render、PostgreSQL、Qdrant、API 延遲）
- 自動刷新間隔選擇（30s / 1m / 5m）+ 手動刷新

### Tab 分頁（5 個）

| Tab | 說明 | 主要內容 |
|-----|------|---------|
| **總覽** | 兩功能合計概覽 | 合計用戶 / 費用 / Turns、課程 vs PDF 時段對比卡、時段選擇器、課程 Token 趨勢 |
| **課程推薦** | gpt-5.4-mini 監控 | Model 資訊 + 定價、Latency 統計、Latency 趨勢、Token / 費用趨勢、工具使用統計 |
| **大專生計畫** | gpt-4o + gpt-4o-mini 監控 | Agent 路由分佈（圓餅）、Latency by Agent（橫條）、費用拆分卡、4 系列 Token 趨勢、端到端 Latency |
| **資料庫** | 基礎設施統計 | 基礎設施概覽卡片、PostgreSQL 詳細統計、Qdrant Collections、Cloudinary PDF 儲存 |
| **對話活動** | 使用行為分析 | Feature 切換器（合計 / 課程推薦 / 大專生計畫）、活動趨勢、工具使用、活躍時段 |

---

## 資料來源與 API

### `GET /api/monitor/stats`

依開發人員認證 + 時段參數回傳完整統計。

**Query Parameters：**

| 參數 | 說明 |
|------|------|
| `preset=1d\|7d\|30d` | 快捷預設，有快取（TTL：60s / 300s / 600s） |
| `start=YYYY-MM-DD&end=YYYY-MM-DD` | 自訂日期（不快取） |
| `feature=all\|course\|pdf` | 只取特定功能統計，預設 `all` |

- 單日（`start == end`）：自動改用**小時分組**（0–23）
- 多日：按**日期分組**

**回傳結構：**

```jsonc
{
  // ── 頁頭資訊 ──────────────────────────────────────────────
  "date_range":            { "start": "2026-05-24", "end": "2026-05-30" },
  "model_name":            "gpt-5.4-mini",
  "pdf_model_name":        "gpt-4o",
  "pdf_router_model_name": "gpt-4o-mini",
  "server_uptime_seconds": 9240,
  "system_health":         { "postgres": "ok", "qdrant": "ok" },
  "latency_stats": [
    { "endpoint": "/api/chat", "count": 30, "avg_ms": 8500, "p95_ms": 14200, "error_count": 0, "error_rate_pct": 0 }
  ],

  // ── 合計（兩功能去重） ────────────────────────────────────
  "combined": {
    "total_users":    142,
    "online_now":     3,
    "total_turns":    2500,
    "total_cost_usd": 0.0072
  },

  // ── 課程推薦（backward-compat：頂層 key 同時保留）─────────
  "course": {
    "all_time": {
      "total_users": 138, "total_sessions": 500, "total_turns": 2000,
      "total_input": 1000000, "total_output": 400000,
      "online_now": 2, "estimated_cost_usd": 0.0042
    },
    "period": {
      "active_users": 23, "new_users": 5, "sessions": 30, "turns": 120,
      "avg_turns_per_session": 4.2,
      "input_tokens": 50000, "output_tokens": 25000,
      "estimated_cost_usd": 0.0002,
      "llm_latency": { "count": 30, "avg_ms": 8500, "p95_ms": 14200, "p99_ms": 18000, "min_ms": 3200, "max_ms": 22000 },
      "llm_latency_trend": [{ "date": "2026-05-24", "avg_ms": 8200 }]
    },
    "trends": {
      "turns":        { "current": 120, "previous": 95, "change_pct": 26.3 },
      "tokens":       { "current": 75000, "previous": 60000, "change_pct": 25.0 },
      "active_users": { "current": 23, "previous": 18, "change_pct": 27.8 }
    },
    "peak_hours":     [{ "hour": 0, "turns": 5 }],
    "daily_trend":    [{ "date": "2026-05-24", "input": 45000, "output": 22000, "turns": 95, "sessions": 25 }],
    "tools_usage":    [{ "tool": "search_courses", "label": "課程語意搜尋", "count": 300 }],
    "activity_trend": [{ "date": "2026-05-24", "sessions": 25, "turns": 95 }]
  },

  // ── 大專生計畫 ────────────────────────────────────────────
  "pdf": {
    "all_time": {
      "total_users": 45, "total_sessions": 120, "total_turns": 500,
      "total_input": 300000, "total_output": 120000,
      "total_router_input": 8000, "total_router_output": 3000,
      "online_now": 1, "estimated_cost_usd": 0.003
    },
    "period": {
      "active_users": 8, "new_users": 2, "sessions": 10, "turns": 40,
      "avg_turns_per_session": 4.0,
      "input_tokens": 12000, "output_tokens": 5000,
      "router_input_tokens": 400, "router_output_tokens": 150,
      "estimated_cost_usd": 0.00005,
      "estimated_cost_breakdown": {
        "agent_usd":  0.000047,
        "router_usd": 0.0000003
      },
      "llm_latency": { "count": 40, "avg_ms": 12000, "p95_ms": 20000, "p99_ms": 25000, "min_ms": 5000, "max_ms": 30000 },
      "llm_latency_trend": [{ "date": "2026-05-24", "avg_ms": 11500 }],
      "agent_distribution": [
        { "agent_name": "retrieval", "cnt": 22 },
        { "agent_name": "chat",      "cnt": 12 },
        { "agent_name": "research",  "cnt": 6  }
      ],
      "latency_by_agent": [
        { "agent_name": "research",  "cnt": 6,  "avg_ms": 22000, "p95_ms": 28000 },
        { "agent_name": "retrieval", "cnt": 22, "avg_ms": 11000, "p95_ms": 18000 },
        { "agent_name": "chat",      "cnt": 12, "avg_ms": 8000,  "p95_ms": 14000 }
      ]
    },
    "trends": {
      "turns":        { "current": 40, "previous": 32, "change_pct": 25.0 },
      "tokens":       { "current": 17000, "previous": 13000, "change_pct": 30.8 },
      "active_users": { "current": 8, "previous": 6, "change_pct": 33.3 }
    },
    "daily_trend": [
      { "date": "2026-05-24", "input": 10000, "output": 4200,
        "router_input": 320, "router_output": 120, "turns": 32, "sessions": 8 }
    ],
    "activity_trend": [{ "date": "2026-05-24", "sessions": 8, "turns": 32 }]
  },

  // ── Backward-compat 頂層 key（等同 course 子物件）─────────
  "all_time":       { /* 同 course.all_time */ },
  "period":         { /* 同 course.period  */ },
  "trends":         { /* 同 course.trends  */ },
  "peak_hours":     [ /* 同 course.peak_hours */ ],
  "daily_trend":    [ /* 同 course.daily_trend */ ],
  "tools_usage":    [ /* 同 course.tools_usage */ ],
  "activity_trend": [ /* 同 course.activity_trend */ ]
}
```

### `GET /api/monitor/db-stats`

回傳基礎設施靜態統計（**快取 600 秒**）。

```jsonc
{
  "infra": {
    "server_uptime_seconds": 9240,
    "neon_region":           "ap-southeast-1",
    "qdrant_region":         "us-west-1",
    "qdrant_total_points":   12450
  },
  "postgres": {
    "connections": 4, "cache_hit_pct": 98.3, "db_size": "8.2 MB",
    "tables": [
      { "name": "chat_turns",         "rows": 2341, "size_bytes": 4407296, "size_pretty": "4.2 MB" },
      { "name": "pdf_agent_messages", "rows": 512,  "size_bytes": 819200,  "size_pretty": "800 KB" }
    ]
  },
  "qdrant": {
    "collections": [
      { "name": "ncu_courses_ug", "points_count": 3200, "segments_count": 2, "optimizer_ok": true, "status": "green" }
    ]
  },
  "cloudinary": {
    "total_resources": 459, "storage_bytes": 2411724800,
    "storage_pretty": "2.25 GB", "bandwidth_pretty": "0 KB", "plan": "Free"
  },
  "cloudinary_error": null
}
```

---

## 資料庫 Schema 異動

### `chat_turns`（`session_store.py` `_ensure_schema()` 動態 ALTER）

```sql
ALTER TABLE chat_turns ADD COLUMN IF NOT EXISTS input_tokens   INT NOT NULL DEFAULT 0;
ALTER TABLE chat_turns ADD COLUMN IF NOT EXISTS output_tokens  INT NOT NULL DEFAULT 0;
ALTER TABLE chat_turns ADD COLUMN IF NOT EXISTS llm_latency_ms INT NOT NULL DEFAULT 0;
ALTER TABLE chat_turns ADD COLUMN IF NOT EXISTS model_name     TEXT;
```

| 欄位 | 說明 |
|------|------|
| `input_tokens` / `output_tokens` | 每輪對話的 Azure OpenAI token 消耗 |
| `llm_latency_ms` | 路由接到請求到 LLM 回應完成的總時間（含工具呼叫） |
| `model_name` | 使用的 Azure 部署名稱（如 `gpt-5.4-mini`） |

### `pdf_agent_messages`（Alembic migration `003_add_token_latency`）

```sql
ALTER TABLE pdf_agent_messages
  ADD COLUMN input_tokens         INT NOT NULL DEFAULT 0,
  ADD COLUMN output_tokens        INT NOT NULL DEFAULT 0,
  ADD COLUMN router_input_tokens  INT NOT NULL DEFAULT 0,
  ADD COLUMN router_output_tokens INT NOT NULL DEFAULT 0,
  ADD COLUMN latency_ms           INT NOT NULL DEFAULT 0,
  ADD COLUMN model_name           TEXT;
```

| 欄位 | 說明 |
|------|------|
| `input_tokens` / `output_tokens` | 一輪 PDF 對話所有 LLM 呼叫合計（含 router） |
| `router_input_tokens` / `router_output_tokens` | 只有 router（gpt-4o-mini）的 token，用於費用拆分 |
| `latency_ms` | `route_agent_stream` 端到端毫秒數 |
| `model_name` | 主要 agent 使用的部署名稱（gpt-4o） |

> **部署注意**：`pdf_agent_messages` 欄位須執行 `alembic upgrade head` 才會套用到生產 DB；`chat_turns` 欄位在服務啟動時自動 `ALTER`，無需手動執行。

---

## Token 成本計算

### 三種 Model 定價

| Model | 用途 | Input（per 1M） | Output（per 1M） |
|-------|------|----------------|-----------------|
| gpt-5.4-mini | 課程推薦 agent | $0.75 | $4.50 |
| gpt-4o | 大專生計畫 agent | $2.50 | $10.00 |
| gpt-4o-mini | 大專生計畫 router | $0.15 | $0.60 |

```python
_COURSE_PRICE  = {"input": 0.75 / 1_000_000, "output": 4.50 / 1_000_000}
_PDF_AGENT_PX  = {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000}
_PDF_ROUTER_PX = {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000}
```

PDF 費用計算：
```
agent_inp = input_tokens - router_input_tokens
agent_out = output_tokens - router_output_tokens
cost = agent_inp × $2.50 + agent_out × $10.00
     + router_input_tokens × $0.15 + router_output_tokens × $0.60
```

費用在 Python 層即時計算，不存入資料庫。

---

## PDF Token 收集機制

PDF 功能的 LLM 呼叫分散在多個 agent 與 router，使用 **`contextvars.ContextVar`** 模式彙整：

```
route_agent_stream() 開始
  → 建立 _TurnCostAccumulator()，set 到 _turn_cost_var
  → router._orchestrate() 用 include_raw=True 擷取 router tokens → 寫入 acc
  → agent LLM 呼叫觸發 @after_model 中介層 _track_model_cost() → 累積到 acc
route_agent_stream() 結束
  → 計算 latency_ms
  → reset _turn_cost_var
  → _write_agent_message() 將 acc 內容寫入 pdf_agent_messages
```

---

## 關鍵設計決策

### API Latency 追蹤（in-process）
- `LatencyMiddleware`（`main.py`）記錄所有 `/api/*` 請求的回應時間
- 儲存於 `latency_store.py` 的模組級 `deque(maxlen=500)`，程序重啟後重置
- 不進資料庫，適合短期趨勢觀察；多 worker 部署時各自獨立

### Model Latency 追蹤（持久化）
- **課程推薦**：`chat.py` 在 `generate_with_tools()` 前後計時，存入 `chat_turns.llm_latency_ms`
- **大專生計畫**：`route_agent_stream()` 計算端到端時間，存入 `pdf_agent_messages.latency_ms`

### 時段選擇與快取

| 模式 | TTL | 說明 |
|------|-----|------|
| `preset=1d` | 60 秒 | 今日（小時分組） |
| `preset=7d` | 300 秒 | 近 7 天 |
| `preset=30d` | 600 秒 | 近 30 天 |
| 自訂日期 | 不快取 | 每次即時查詢 |
| `db-stats` | 600 秒 | 基礎設施統計 |

快取 key 包含 `feature` 參數（如 `7d:all`），避免不同 feature 汙染快取。

### Combined 用戶去重
```sql
SELECT COUNT(DISTINCT uid) FROM (
  SELECT user_id AS uid FROM chat_sessions    WHERE user_id IS NOT NULL
  UNION
  SELECT user_id AS uid FROM pdf_conversations WHERE user_id IS NOT NULL
) sub
```
前提：`chat_sessions` 與 `pdf_conversations` 在同一 Postgres 實例，`user_id` 格式相同（Firebase UID）。

### Cloudinary 串接
- 使用 Cloudinary SDK（`cloudinary.api.usage()`）
- 回傳 `cloudinary_error` 欄位供前端顯示診斷訊息

### Backward Compatibility
回應頂層保留舊 key（`all_time`、`period`、`trends`、`daily_trend`、`tools_usage`、`peak_hours`、`activity_trend`），內容等同 `course` 子物件，確保舊程式碼不中斷。

---

## 部署注意事項

### 後端環境變數

```env
DEVELOPER_EMAILS=dev@example.com

# Azure OpenAI
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-5.4-mini   # 課程推薦
AZURE_CHAT_DEPLOYMENT=gpt-4o                # PDF agent
AZURE_MINI_DEPLOYMENT=gpt-4o-mini           # PDF router

# Cloudinary（選填，無則 cloudinary 卡片不顯示）
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
```

### 前端環境變數

```env
VITE_DEVELOPER_EMAILS=dev@example.com
```

### 首次部署 PDF 監控功能

```bash
cd backend
python -m alembic upgrade head   # 套用 003_add_token_latency migration
```

### Render 冷啟動
`server_uptime_seconds` 在每次冷啟動後重置為 0，可用來判斷是否為新實例。

---

## 相關檔案

| 路徑 | 說明 |
|------|------|
| `backend/app/routes/monitor.py` | `/api/monitor/stats` 和 `/api/monitor/db-stats` 路由，含 `feature` query param |
| `backend/app/services/session_store.py` | `get_monitor_stats()`、`_get_pdf_stats()`、費用計算、`get_db_stats()` |
| `backend/app/services/latency_store.py` | API 回應時間 in-process 儲存 |
| `backend/app/agents/pdf/runner.py` | `_TurnCostAccumulator`、`_turn_cost_var`、`_track_model_cost()` |
| `backend/app/agents/pdf/router_agent.py` | `route_agent_stream()` 包裝、router token 擷取、`_write_agent_message()` |
| `backend/app/models/pdf_models.py` | `PdfAgentMessage` ORM，含 6 個新監控欄位 |
| `backend/alembic/versions/003_add_token_latency_to_messages.py` | Alembic migration |
| `backend/app/main.py` | `LatencyMiddleware` |
| `backend/app/routes/chat.py` | 課程推薦 LLM 計時邏輯 |
| `frontend/src/pages/MonitorPage.tsx` | 完整儀表板 UI（5 tabs） |
| `frontend/src/api/services.ts` | `MonitorStats`、`PdfStats`、`CourseStats`、`CombinedStats` 等型別定義 |
| `frontend/src/auth/developerUtils.ts` | `isDeveloper()` helper |
