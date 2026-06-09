# PDF 研究計畫 RAG 系統設計說明

> 撰寫日期：2026-06-03  
> 對應版本：`main` branch（RAG 問答基礎建設）+ `report-agent` branch（PDF 攝入與摘要 Pipeline）

---

## 概述

本系統以國科會大專學生研究計畫 PDF（104–114 學年度，共約 459 份）為資料來源，提供三個功能：

| 功能 | 說明 | 資料形式 |
|------|------|---------|
| **研究計畫大綱** | 呈現每份計畫的基本資訊（標題、系所、學年） | 靜態 metadata |
| **興趣量表** | 高中生閱讀真實研究摘要 + 導讀問題，評分後推薦科系 | AI 生成（report-agent branch pipeline） |
| **PDF 問答（RAG）** | 對任一 PDF 進行自然語言問答 | 即時向量搜尋 + 多 Agent 推理 |

---

## 一、PDF 攝入 Pipeline（report-agent branch）

### 1.1 多解析器策略

`report-agent` branch 的 `rag/ingestion.py` 支援三種 PDF 解析器，依品質需求自動升級：

```
PDF 原始檔
  │
  ▼
parser = "auto"（預設）
  ├─ pymupdf4llm（本地端，速度快，無費用）
  │   → 品質檢查（is_garbled / is_html_table / is_nmr_params...）
  │   → 品質合格 → 直接使用
  │   → 品質不合格 → 升級解析器
  │
  ├─ azure_di（Azure Document Intelligence，雲端）
  │   → 適合版面複雜、含公式的文件
  │   → 有解析快取（避免重複呼叫 API）
  │
  └─ llamaparse（LlamaParse，雲端）
      → 最高品質，公式/圖表處理最佳
      → 最貴，僅用於前兩者都不合格的情況

→ 成功解析 → 清理文字（_clean_text）+ 品質標記
```

### 1.2 章節偵測與語意切 Chunk

```
已解析文字
  │
  ▼
章節偵測（rag/section.py）
  ├─ 從 Markdown heading 提取標題（Heading 1/2/3）
  ├─ 建立 page → section 對照表
  └─ 識別常見學術章節：abstract / introduction /
     related_work / methods / results / conclusion

  │
  ▼
語意切分（rag/chunking.py）
  ├─ 同時考慮：文字長度、語意邊界、章節脈絡
  ├─ 每個 chunk 保留 metadata：
  │   {document_id, page, page_end, section, filename}
  └─ 過濾品質不佳頁面：
      封面頁 / 目錄頁 / 參考文獻頁 / 純表格頁 / 亂碼頁

  │
  ▼
Embedding & 上傳
  ├─ Dense：text-embedding-3-large（3072 維）
  ├─ Sparse：BM25（FastEmbedSparse）
  └─ 上傳至 Qdrant Collection: reports
```

### 1.3 摘要自動抽取

`ingestion.py` 的 `extract_abstract()` 在攝入時從 PDF 前幾頁自動抽取摘要文字，以正規表達式定位「摘要」/「Abstract」標題段落，存入 `Document.abstract_text`，供 Router Agent 作為文件背景摘要。

---

## 二、三步驟摘要與問題生成 Pipeline（report-agent branch）

這是本系統最核心的 AI 設計，在 `services/extraction.py` 實作。每份 PDF 完成攝入後，可觸發以下三步驟流程生成結構化摘要與興趣量表題目：

### 2.1 整體流程

```
PDF 已攝入 Qdrant
  │
  ▼
Step 1：Research Agent（RAG 取證）
  ├─ 呼叫 run_research_summary()（與 PDF 問答共用同一個 Research Agent）
  ├─ 固定問題：「請整理這份研究的動機、方法、成果與限制」
  ├─ 最多 10 次搜尋，coverage-driven（確保四個面向都有文件證據）
  └─ 輸出：raw_research_answer（高資訊量研究摘要文字） + sources

  │（Step 1 完成後，Step 2 + Step 3 並行執行）
  │
  ├──────────────────────────────────────────────────────────────┐
  │                                                              │
  ▼                                                              ▼
Step 2：結構化摘要（structure_research_step2）         Step 3：導讀與問題生成（generate_interest_step3）
  ├─ 輸入：Step 1 raw_research_answer                   ├─ 輸入：Step 1 raw_research_answer
  ├─ 使用 LLM Structured Output                         ├─ 使用 LLM Structured Output
  ├─ 模型：CoreExtractionResponse（Pydantic）           ├─ 模型：QuestionGenerationResponse（Pydantic）
  └─ 輸出：                                             └─ 輸出：
       {                                                       {
         motivation: "≤200字，繁體中文",                         intro:     "100~220字導讀文字",
         method:     "≤200字，可條列",                          questions: ["45~80字×3題"]
         results:    "≤200字，具體成果",                      }
         tags:       ["3~5個關鍵標籤"]
       }
  │                                                              │
  └──────────────────┬───────────────────────────────────────────┘
                     ▼
              合併寫入 DocumentExtraction
              {motivation, method, results, tags, intro, questions}
```

### 2.2 三個步驟的設計邏輯

#### Step 1：用 Research Agent 取證，而非直接摘要

關鍵設計：**先讓 RAG Agent 帶著問題搜尋文件，拿到有文件依據的高資訊量摘要，再讓 LLM 結構化**，而非直接對全文做一次性摘要。

好處：
- 確保每個欄位（動機/方法/成果/限制）都有實際的文件片段支撐
- Research Agent 的 coverage 機制確保四個面向不遺漏
- 避免 LLM 憑訓練知識補充文件沒有寫的內容

#### Step 2：CoreExtractionResponse（學術摘要）

```python
class CoreExtractionResponse(BaseModel):
    motivation: str  # 研究動機與背景，上限 200 字
    method:     str  # 研究方法與步驟，上限 200 字，多步驟可條列
    results:    str  # 研究成果與發現，上限 200 字，具體成果可條列
    tags:       list[str]  # 3-5 個關鍵標籤，繁體中文
```

#### Step 3：QuestionGenerationResponse（高中生版）

```python
class QuestionGenerationResponse(BaseModel):
    intro:     str        # 100~220 字導讀：讓高中生感受研究世界為什麼迷人
    questions: list[str]  # 3 題，每題 45~80 字
                          # 題型分別對應：
                          #   情境吸引力
                          #   研究方式吸引力
                          #   思考方式吸引力
                          # 不是考研究內容，讓學生評 1~5 分個人興趣
                          # 不可三題都用「你是否對...」開頭
```

### 2.3 資料儲存（DocumentExtraction 表）

```
documents 表（1:1）
  └── document_extractions 表
        ├── summary_json         ← Step 2 + Step 3 合併結果
        │     {motivation, method, results, tags, intro, questions}
        ├── raw_research_answer  ← Step 1 原始 RAG 文字（供重跑 Step 2/3 用）
        ├── raw_research_sources ← Step 1 引用頁碼
        ├── tags                 ← 複製自 summary_json.tags（方便查詢）
        ├── category             ← 研究類別
        └── department_hint      ← 推測科系
```

### 2.4 Job Queue 基礎建設

每份文件的摘要生成由 `job_service.py` 管理，支援：

```
POST /api/documents/{id}/extract        → 完整三步驟
POST /api/documents/{id}/extract-step/step1  → 只跑 Step 1（RAG 取證）
POST /api/documents/{id}/extract-step/step2  → 只跑 Step 2（需先有 Step 1）
POST /api/documents/{id}/extract-step/step3  → 只跑 Step 3（需先有 Step 1）

Job 狀態機：queued → running → done / error / cancelled
Stage 事件：「研究文獻中」→「整理結構中」→「生成導讀與問題」→「完成」

持久化：JobHistory 表（DB）+ in-memory state（執行期 source of truth）
選用 Redis：Pub/Sub 跨 instance 廣播、LIST 佇列跨 instance 任務分配
```

---

## 三、研究計畫大綱（Outline View）

### 3.1 資料來源

```
data/processed/projects.json
  ├─ 從 PDF 檔名結構解析：
  │   {學年度}{類型}{編號}_{學生姓名}_{研究題目}.pdf
  ├─ 欄位：{id, year, type, department, studentName, title, pdfPath}
  └─ documentId：由 scripts/populate_document_ids.py 比對 pdf_documents 表後寫入

scripts/populate_document_ids.py
  ├─ 讀 data/processed/projects.json
  ├─ 比對 pdf_documents.filename（三段策略）：
  │   1. ilike 精確比對
  │   2. NFKC 正規化後比對（處理 CJK 相容字符）
  │   3. prefix 比對（處理截斷檔名）
  └─ 寫回 projects.json["documentId"]
```

### 3.2 PDF 原始檔存取

PDF 上傳至 Cloudinary（Raw 類型），前端透過 Cloudinary URL 串流顯示：

```
scripts/storage/upload_pdfs_to_cloudinary.py
  ├─ 掃描 data/raw/projects/104-114/
  └─ 上傳保留原始資料夾結構（系所/檔名）

後端 build_pdf_url()：
  組合 Cloudinary CDN URL → 前端 PdfViewer 直接載入
```

### 3.3 前端呈現（ProjectsPage）

```
viewMode: 'outline'（預設）
  ├─ 左側：計畫列表（依年份/系所篩選）
  └─ 右側：
       ├─ 計畫基本資訊（標題、年份、系所、學生）
       ├─ PDF Viewer（Cloudinary URL 串流）
       └─ [切換為 PDF Chat] 按鈕

viewMode: 'pdf-chat'
  └─ 切換為 RAG 問答介面
```

---

## 四、興趣量表（Interest Assessment）

### 4.1 題目結構

每份研究計畫產生一筆量表題目：

```json
{
  "department": "資訊工程學系",
  "title":      "真實研究計畫標題",
  "intro":      "100~220字，高中生導讀文字（Step 3 生成）",
  "questions":  [
    "情境吸引力題目（45~80字）",
    "研究方式吸引力題目（45~80字）",
    "思考方式吸引力題目（45~80字）"
  ],
  "tags":       ["機器學習", "影像辨識", "深度學習"],
  "mode":       "grade1 | grade2 | grade3"
}
```

`mode` 依年份自動決定：≤107 → grade1；108–110 → grade2；111+ → grade3。

### 4.2 三種年級模式

| 模式 | 對應年級 | 篩選邏輯 |
|------|---------|---------|
| `grade1`（高一） | 高一 | 無分組限制，廣泛探索 |
| `grade2`（高二） | 高二 | 可依文組 / 理組過濾題目 |
| `grade3`（高三） | 高三 | 可依學測選考科目（`ncu_caac.csv`）進一步篩選可選的科系 |

### 4.3 前端評分流程（AssessmentPage）

```
1. 選年級模式
2. （grade2）選文組 / 理組
3. （grade3）選學測科目 → 系統過濾符合學測條件的科系
4. 逐題閱讀 intro + 三個問題，各評 1~5 分
5. POST /api/assessment/submit
6. 後端依科系累加平均分 → 回傳前 15 名推薦科系
7. 顯示各科系學院分類（文學院 / 理學院 / 工學院...）+ matchedTags
```

---

## 五、PDF RAG 問答系統（main branch）

### 5.1 多 Agent 對話流程

```
POST /projects/{project_id}/chat/stream
  │
  ├─ [Quota Check]  pdf_quota_service.check_and_reserve()
  ├─ [Stream Lock]  _stream_lock：防同一使用者+計畫重複並行串流
  │
  ▼
route_agent_stream()
  │
  ▼
Router Agent（gpt-4o-mini + Structured Output）
  ├─ 輸入：問題文字 + 文件摘要（abstract_text）+ 前輪 agent 狀態
  ├─ 輸出：chat | retrieval | research
  └─ 預設：retrieval（LLM 失敗時的 fallback）

    ┌──────────────┬──────────────┬──────────────────────┐
    ▼              ▼              ▼
┌─────────┐  ┌──────────┐  ┌─────────────────────────┐
│  Chat   │  │Retrieval │  │      Research           │
│  Agent  │  │  Agent   │  │      Agent              │
│         │  │          │  │   (LangGraph)           │
│ 無 RAG  │  │ 單次搜尋 │  │ max_searches=14         │
│ 對話回應│  │ → 直接回 │  │ coverage-driven 多跳    │
└────┬────┘  └────┬─────┘  └────────────┬────────────┘
     │            │                     │
     │ [INSUFFICIENT_CONTEXT]           │
     │    → 清空已輸出 → 升級           │
     └────────────┴──────────┬──────────┘
                              ▼
                    SSE 串流（最多 MAX_HANDOFFS=3 跳）
```

### 5.2 Research Agent 狀態機（LangGraph）

```
create_research_plan()
  ├─ 動態生成 coverage_items（最多 6 個）
  ├─ 每個 item：{id, label, description, search_hints, required, use_hyde}
  └─ 情境計畫（依問題關鍵字自動選）：
       student（高中生/導讀）/ method（方法）/ result（成果）/ summary（通用）

研究迴圈（max_searches=14，max_consecutive_no_new=2）：
  ┌─ planner ──► scheduler（run_search_report）──► reflector ─┐
  │                                                            │
  └──────────── [未滿足] ◄──────────────────────────────────── ┘
                [已滿足] ──► writer → 最終回答
```

### 5.3 向量搜尋配置

| 設定 | 值 |
|------|---|
| Qdrant Collection | `reports` |
| 密集向量 | `text-embedding-3-large`（3072 維） |
| 稀疏向量 | BM25（FastEmbedSparse `Qdrant/bm25`） |
| 每次查詢候選數 | `RETRIEVAL_K = 10` |
| Rerank 保留數 | `RERANK_TOP_N = 4`（最大 12） |
| 語言自動偵測 | `zh` / `en` / `mixed` |
| 混合語言策略 | Dense + Hybrid 雙路，interleave 候選後統一 rerank |
| Reranking | FlashrankRerank（本地，8 秒 timeout per query） |
| 品質過濾 | 封面頁 / 參考文獻頁 / 表格公式頁自動排除 |
| HyDE fallback | 無結果時生成假設性段落再搜尋 |

### 5.4 查詢展開

每次搜尋接受多個欄位，展開為多路查詢後並行打 Qdrant：

```
{
  query:         "主查詢（必填）",
  keyword_query: "關鍵字版（BM25 偏重）",
  semantic_query:"語意句（dense 偏重）",
  section_terms: ["research_methods", "results"],  # 段落過濾
  sub_queries:   ["同主題換句話說1", "換句話說2"]
}
```

### 5.5 使用者長期記憶

```json
{
  "preferred_language":     "Traditional Chinese",
  "academic_background":    "高中生",
  "topics_of_interest":     ["機器學習", "生物資訊"],
  "answer_style_preference": "簡潔"
}
```

由 `pdf_user_profile_service.py` 在背景非同步更新，注入 system prompt 調整回答深度與語言。

### 5.6 SSE 串流事件

| 事件類型 | 說明 |
|---------|------|
| `session_id` | thread_id，前端保存供多輪對話 |
| `stage:XXX` | 當前階段（「搜尋文件中」「研究中」「組織回答中」） |
| `token:XXX` | LLM 逐字輸出 |
| `heartbeat` | 每 15 秒保持連線 |
| `replace:XXX` | escalation 或 composition 後替換已輸出內容 |
| `sources:XXX` | 引用頁碼（`p.3-5` 格式） |
| `done` | 完成 |
| `error` | 錯誤訊息 |

### 5.7 並行控制

| 機制 | 位置 | 用途 |
|------|------|------|
| `_stream_lock` | `routes/projects.py` | 同一用戶+計畫不允許兩個並行串流 |
| `pdf_llm_gate.py` | `services/pdf_llm_gate.py` | 全域 LLM 並行呼叫上限 |
| `pdf_quota_service.py` | `services/pdf_quota_service.py` | 用戶配額（check_and_reserve + exit_reservation） |
| `_RERANK_THREAD_SEM` | `rag.py` | Reranking 執行緒上限（BoundedSemaphore(6)） |

---

## 六、資料庫 Schema

### main branch（PDF 問答）

```sql
pdf_documents      (id, filename, abstract_text, status)
pdf_conversations  (id, thread_id, user_id, document_id,
                   message_count, last_agent_name, stream_started_at)
pdf_agent_messages (id, message_id, thread_id, agent_name,
                   user_question, agent_answer,
                   sources JSONB, trace_summary JSONB, observation_id)
```

### report-agent branch（摘要與問題生成）

```sql
documents          (id, filename, file_path, status,
                   abstract_text, batch_status)
document_extractions (id, document_id,
                   summary_json JSONB,    -- {motivation, method, results, tags, intro, questions}
                   raw_research_answer TEXT,
                   raw_research_sources JSONB,
                   tags JSONB,
                   category, department_hint)
job_history        (id, job_id, doc_id, filename, job_type,
                   status, stage, stage_log, error,
                   started_at, updated_at, completed_at)
```

---

## 七、API 端點

### main branch

| 方法 | 路徑 | 說明 |
|------|------|------|
| `GET` | `/projects` | 計畫列表（year/dept 篩選） |
| `GET` | `/projects/{id}` | 單一計畫詳情 |
| `POST` | `/projects/{id}/chat/stream` | SSE 串流問答 |
| `POST` | `/projects/{id}/chat/{thread_id}/cancel` | 取消串流 |
| `GET` | `/assessment/questions` | 取得量表題目（依 mode） |
| `POST` | `/assessment/submit` | 提交評分，取得科系推薦 |
| `GET` | `/assessment/admission-criteria` | 學測篩選標準 |
| `POST` | `/assessment/filter-by-subjects` | 依學測科目過濾可選科系 |

### report-agent branch（摘要生成）

| 方法 | 路徑 | 說明 |
|------|------|------|
| `POST` | `/api/documents/{id}/extract` | 觸發完整三步驟摘要生成 |
| `POST` | `/api/documents/{id}/extract-step/{step}` | 觸發單一步驟（step1/2/3） |
| `GET` | `/api/documents/{id}` | 取得文件與摘要結果 |

---

## 八、技術棧

| 類別 | 技術 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| LLM | Azure OpenAI：gpt-4o（主要）、gpt-4o-mini（router） |
| Embedding | text-embedding-3-large（3072 維） |
| PDF 解析 | PyMuPDF4LLM（本地）、Azure Document Intelligence、LlamaParse（雲端） |
| 向量資料庫 | Qdrant Cloud（Collection: `reports`） |
| 資料庫 | PostgreSQL（Neon Serverless） |
| Agent 框架 | LangGraph（Research Agent 狀態機） |
| Reranking | FlashrankRerank（本地） |
| 追蹤 | Langfuse（report-agent branch） |
| Job Queue | 自製 in-memory + Redis Pub/Sub（選用） |
| PDF 存取 | Cloudinary（Raw 上傳，CDN 串流） |
| 認證 | Firebase Authentication（JWT） |
| 前端 | React + TypeScript + Tailwind CSS |
| PDF 渲染 | react-pdf（PDF.js） |
| 串流 | SSE（Server-Sent Events） |
