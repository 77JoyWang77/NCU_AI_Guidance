# 雲端部署架構

> 更新時間：2026-05-02

---

## 一、三層部署架構

```
┌─────────────────────────────────────────────────────────┐
│                      使用者                              │
└──────────────────────────┬──────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│  Firebase Hosting（前端）                                │
│  React 19 + TypeScript + Vite                           │
│  網址：ncu-ai-guidance.web.app                          │
└──────────────────────────┬──────────────────────────────┘
                            ↓ HTTPS API
┌─────────────────────────────────────────────────────────┐
│  Render（後端）                                          │
│  FastAPI + Python 3.11+                                 │
│  /api/chat/stream（SSE）                                │
│  含本地 Qdrant（file-mode）                             │
└────────────┬───────────────────┬────────────────────────┘
             ↓                   ↓
┌────────────┴──┐   ┌────────────┴──────────────────────┐
│  Cloudinary   │   │  Azure OpenAI                      │
│  PDF 靜態存儲  │   │  GPT-4o（對話）                   │
│  大專生研究計畫│   │  text-embedding-3-large（嵌入）   │
└───────────────┘   └───────────────────────────────────┘
```

---

## 二、Firebase Hosting（前端）

### 2.1 設定檔

**`firebase.json`**：
```json
{
  "hosting": {
    "public": "frontend/dist",
    "rewrites": [
      {"source": "**", "destination": "/index.html"}
    ],
    "headers": [
      {
        "source": "**/*.@(js|css)",
        "headers": [{"key": "Cache-Control", "value": "max-age=31536000"}]
      }
    ]
  }
}
```

**`.firebaserc`**：
```json
{
  "projects": {
    "default": "ncu-ai-guidance"
  }
}
```

### 2.2 前端建置

```bash
cd frontend
npm run build        # 輸出至 frontend/dist/
firebase deploy      # 部署至 Firebase Hosting
```

**技術棧**：
- React 19 + TypeScript
- Vite（建置工具）
- Tailwind CSS 3.4
- React Router v7
- Axios（HTTP 客戶端）

### 2.3 特色

- SPA（Single Page Application）：所有路由由前端 React Router 處理
- 靜態資源 CDN 加速（Firebase 全球 CDN）
- 自動 HTTPS

---

## 三、Render（後端）

### 3.1 服務配置

Render 免費方案部署 FastAPI 後端（Web Service）：

| 項目 | 設定 |
|------|------|
| 執行環境 | Python 3.11 |
| 啟動指令 | `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT` |
| 健康檢查 | `GET /health` |

### 3.2 環境變數（.env）

```bash
# Azure OpenAI
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://claire1.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-5.4-mini
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large

# Cloudinary（PDF 存儲）
CLOUDINARY_CLOUD_NAME=dvozvbpai
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
CLOUDINARY_PROJECT_FOLDER=ncu-ai-guidance/data/raw/projects

# LangSmith（可選，LLM 監控）
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_PROJECT=ncu-rag-system
LANGSMITH_TRACING=true
```

### 3.3 Qdrant 本地部署

Render 服務啟動時，Qdrant 以 **file-mode** 運行（不需要 Docker 或外部服務）：

```python
from qdrant_client import QdrantClient
client = QdrantClient(path="data/processed/qdrant_data")
```

- 資料持久儲存在 `data/processed/qdrant_data/`
- 無需額外 Qdrant Cloud 費用
- 首次查詢較慢（需初始化），後續快取加速

**注意**：Render 免費方案每 15 分鐘無活動後休眠，首次請求需等待冷啟動（約 30s）。

---

## 四、Cloudinary（PDF 存儲）

### 4.1 用途

儲存大專生研究計畫 PDF 檔案，供前端直接讀取顯示。

| 項目 | 說明 |
|------|------|
| Cloud Name | `dvozvbpai` |
| 資料夾 | `ncu-ai-guidance/data/raw/projects` |
| 存取 | 公開 URL 直接訪問 |

### 4.2 前端整合

前端從後端 API 取得 Cloudinary PDF URL，透過 `<iframe>` 或 PDF.js 嵌入顯示：

```
projects_metadata.json
  → FastAPI /api/projects
  → 前端取得 pdf_url（Cloudinary）
  → <iframe src={pdf_url} /> 直接渲染
```

---

## 五、Azure OpenAI

### 5.1 服務配置

| 服務 | 模型 | 用途 |
|------|------|------|
| 對話 | GPT-4o（或 gpt-5.4-mini） | ReAct Agent 主 LLM |
| 嵌入 | text-embedding-3-large（3,072 維） | Qdrant 向量索引建立 |

### 5.2 API 版本

```
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

支援 `max_completion_tokens`（替代舊版 `max_tokens`）：

```python
def _build_completion_params(self, ...):
    # 相容性處理
    if self.api_version >= "2024-12-01":
        params["max_completion_tokens"] = MAX_TOKENS
    else:
        params["max_tokens"] = MAX_TOKENS
```

---

## 六、LangSmith 監控（可選）

啟用後自動追蹤所有 LLM 呼叫：

```python
from langsmith import wrap_openai
client = wrap_openai(AzureOpenAI(...))
```

**追蹤內容**：
- 每次 LLM 呼叫的 prompt / response
- Token 用量（input / output / total）
- 延遲時間
- 工具呼叫序列（tool_start → tool_done）

**Dashboard**：https://smith.langchain.com/project/ncu-rag-system

---

## 七、本地開發環境

```bash
# 後端（Hot reload）
cd backend
uvicorn app.main:app --reload --port 8000

# 前端（Hot reload）
cd frontend
npm run dev    # → http://localhost:5173

# 環境變數（後端）
cp .env.example .env
# 填入 AZURE_OPENAI_API_KEY 等必要設定
```

**前端 API 代理**（`vite.config.ts`）：
```typescript
server: {
  proxy: {
    '/api': 'http://localhost:8000'
  }
}
```

---

## 八、成本估算

| 項目 | 方案 | 費用 |
|------|------|------|
| Firebase Hosting | Spark（免費） | $0 |
| Render Web Service | Free（每月 750 小時） | $0（限制：休眠 15min） |
| Cloudinary | Free（25 GB 存儲） | $0 |
| Azure OpenAI（對話） | Pay-as-you-go | ~$0.01/千 token |
| Azure OpenAI（嵌入） | 一次性建立索引 | ~$0.13/百萬 token |
| LangSmith | Developer（免費） | $0（限制：5,000 traces/月） |
| **合計（開發期）** | | **$0-5/月** |
