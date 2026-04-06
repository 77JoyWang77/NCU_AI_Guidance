# NCU 科系探索系統 - Azure 部署方案分析

## 目錄
1. [系統架構概覽](#系統架構概覽)
2. [三層資料架構（核心理念）](#三層資料架構核心理念)
3. [為什麼不要把 Embedding 放資料庫](#為什麼不要把-embedding-放資料庫)
4. [Azure 服務選擇](#azure-服務選擇)
5. [部署架構圖](#部署架構圖)
6. [詳細服務說明](#詳細服務說明)
7. [資料層實作細節](#資料層實作細節)
8. [成本估算](#成本估算)
9. [部署步驟](#部署步驟)
10. [替代方案比較](#替代方案比較)

---

## 系統架構概覽

### 當前本地架構

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   React     │ ───▶ │   FastAPI    │ ───▶ │ JSON Files  │
│  (前端)      │      │   (後端)      │      │  (資料)      │
└─────────────┘      └──────────────┘      └─────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │   Qdrant     │
                     │ (向量搜尋)    │
                     └──────────────┘
```

**元件清單：**
- **前端**: React 18 + TypeScript + Vite
- **後端**: FastAPI (Python 3.8+)
- **資料儲存**:
  - JSON 檔案 (3,316 門課程)
  - JSON 檔案 (459 筆研究計畫)
  - JSON 檔案 (189 題量表)
  - CSV 檔案 (學測標準)
  - PDF 檔案 (研究報告)
- **AI 功能**: RAG (Retrieval-Augmented Generation) 課程搜尋

---

## 三層資料架構（核心理念）

### 🎯 業界標準：分層儲存，各司其職

```
┌────────────────────────────────────────────────────────────┐
│  Layer 1: 原始資料層 (Azure Blob Storage)                    │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • PDF 檔案（研究報告）                                       │
│  • 原始 JSON 檔案（課程、計畫）                               │
│  • 圖片、影片等多媒體                                         │
│                                                              │
│  用途: 歷史記錄、備份、重新處理                                │
│  成本: 超便宜 ($0.02/GB/月)                                  │
│  特性: 不可變、版本控制、CDN 加速                             │
└────────────────────────────────────────────────────────────┘
                          ↓ ETL Pipeline
┌────────────────────────────────────────────────────────────┐
│  Layer 2: 結構化資料層 (Azure Cosmos DB)                     │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • 提取的文字內容（從 PDF）                                   │
│  • AI 生成的摘要（短、中、長版本）                            │
│  • Metadata（系所、年份、標籤等）                            │
│  • 關聯資訊（相關課程、參考資料）                             │
│                                                              │
│  用途: CRUD 操作、結構化查詢、關聯查詢                        │
│  成本: 中等 ($25/GB/月，Serverless 更便宜)                   │
│  特性: NoSQL 彈性、全球分散、自動擴展                         │
│  ⚠️ 重點: 不存 Embedding！                                  │
└────────────────────────────────────────────────────────────┘
                          ↓ Vectorization
┌────────────────────────────────────────────────────────────┐
│  Layer 3: 向量搜尋層 (Azure AI Search)                       │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • 文字 Embeddings (1536 維向量)                            │
│  • 向量索引 (HNSW 演算法)                                    │
│  • 最小 Metadata（用於篩選）                                 │
│                                                              │
│  用途: 語意搜尋、相似度檢索、向量查詢                         │
│  成本: 固定 ($0-$75/月，視規模)                              │
│  特性: 毫秒級回應、自動優化、混合搜尋                         │
│  ⭐ 核心: 只存向量和 ID，不存完整文檔！                       │
└────────────────────────────────────────────────────────────┘
```

### 📊 查詢流程範例

```python
# 使用者查詢："我想學人工智慧相關的課程"

# Step 1: Azure AI Search 向量搜尋 (10-50ms)
query_embedding = openai.Embedding.create(input=user_query)
doc_ids = ai_search.vector_search(query_embedding, top_k=20)
# 回傳: ["course_001", "course_042", "course_089", ...]

# Step 2: Cosmos DB 批次查詢詳細資料 (50-100ms)
courses = cosmos_db.query(f"SELECT * FROM c WHERE c.id IN ({doc_ids})")
# 回傳: 完整的課程資訊（名稱、摘要、學分、教師等）

# Step 3: 必要時從 Blob Storage 取得原始檔案
if need_pdf:
    pdf_url = blob_storage.get_url(course['references']['blob_path'])

# 總回應時間: < 200ms ⚡
```

### ⚡ 效能對比

| 操作 | 傳統方式 (DB 存 Embedding) | 三層架構 | 差異 |
|------|-------------------------|---------|------|
| 向量搜尋 (1,000 筆) | 2-5 秒 | 10-50ms | **100-500x** ⚡ |
| 向量搜尋 (10,000 筆) | 20-50 秒 | 20-100ms | **200-500x** ⚡ |
| 向量搜尋 (100,000 筆) | 3-5 分鐘 | 50-200ms | **1000x+** ⚡ |
| 資料儲存成本 | $500/月 | $100/月 | **5x 節省** 💰 |

---

## 為什麼不要把 Embedding 放資料庫？

### ❌ 問題 1：效能災難

**錯誤做法：**
```python
# ❌ 從資料庫讀取所有 embeddings
def bad_vector_search(query):
    # 生成查詢向量
    query_vector = generate_embedding(query)  # 1536 維

    # 從資料庫讀取所有文檔（災難！）
    cursor.execute("SELECT id, embedding FROM documents")
    all_docs = cursor.fetchall()  # ⚠️ 3,316 筆 × 6KB = 20MB 傳輸！

    # 在 Python 中逐一計算相似度（超慢！）
    results = []
    for doc_id, embedding in all_docs:
        similarity = cosine_similarity(query_vector, embedding)
        results.append((doc_id, similarity))

    # 排序取 Top 10
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:10]

# 時間複雜度: O(N) - 線性增長
# 3,316 筆: ~2-5 秒
# 10,000 筆: ~20-50 秒
# 100,000 筆: ~3-5 分鐘 💀
```

**正確做法：**
```python
# ✅ 使用專門的向量搜尋引擎
def good_vector_search(query):
    # 生成查詢向量
    query_vector = generate_embedding(query)

    # 向量搜尋（HNSW 演算法）
    results = search_client.search(
        vector_queries=[{
            "vector": query_vector,
            "k_nearest_neighbors": 10,
            "fields": "content_vector"
        }]
    )

    return list(results)

# 時間複雜度: O(log N) - 對數增長
# 3,316 筆: ~10-50ms ⚡
# 10,000 筆: ~20-100ms ⚡
# 100,000 筆: ~50-200ms ⚡
```

### ❌ 問題 2：資料膨脹

**Embedding 大小分析：**
```
單一課程文檔:
├─ 文字內容: ~2-5 KB
├─ Metadata: ~500 bytes
└─ Embedding: ~6 KB (1536 維 × 4 bytes/float)

總計: ~8-12 KB

3,316 門課程:
├─ 不含 Embedding: ~10 MB
└─ 含 Embedding: ~30-40 MB

成本影響:
├─ Cosmos DB (不含 Embedding): $25/月
└─ Cosmos DB (含 Embedding): $100-150/月  💸

差距: 4-6 倍成本！
```

### ❌ 問題 3：查詢效能差

**為什麼資料庫不適合向量搜尋：**

1. **沒有向量索引優化**
   - 一般資料庫用 B-Tree 索引（適合數值、文字）
   - 向量需要 HNSW / IVF 索引（專門演算法）

2. **無法利用 GPU 加速**
   - 向量計算高度並行
   - AI Search 內建 GPU 優化

3. **網路傳輸開銷大**
   - 每次查詢需傳輸 MB 級資料
   - AI Search 只回傳結果 ID

4. **無法做近似搜尋**
   - 精確搜尋 = O(N) 複雜度
   - 近似搜尋 (ANN) = O(log N) 複雜度

### ✅ 正確架構的優勢

```
查詢："找與『量子物理』相關的課程"

┌─────────────────────────────────────────────────┐
│ Step 1: Azure AI Search (10-50ms)               │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ • 生成查詢向量                                    │
│ • HNSW 演算法快速搜尋                            │
│ • 回傳 Top 20 document IDs                      │
│                                                 │
│ 輸出: ["course_042", "course_089", ...]         │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ Step 2: Cosmos DB (50-100ms)                    │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ • 批次查詢 (一次性取得所有詳細資料)                │
│ • SELECT * FROM c WHERE c.id IN (...)           │
│                                                 │
│ 輸出: 完整課程資訊（名稱、摘要、學分、教師...）     │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ Step 3: 回傳給使用者 (總時間: <200ms)            │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ {                                               │
│   "results": [...],                            │
│   "total": 20,                                 │
│   "took_ms": 156                               │
│ }                                              │
└─────────────────────────────────────────────────┘
```

**vs. 錯誤做法：**
```
┌─────────────────────────────────────────────────┐
│ 從資料庫讀取所有 embeddings (2-5 秒)             │
│ → 在 Python 中計算相似度 (1-2 秒)               │
│ → 排序取 Top 10 (0.5 秒)                        │
│ → 再次查詢資料庫取得詳細資料 (0.5 秒)            │
│                                                 │
│ 總時間: 4-8 秒 💀                                │
└─────────────────────────────────────────────────┘
```

---

## Azure 服務選擇

### 推薦方案：完整 Azure 原生服務

```
┌────────────────────────────────────────────────────────────┐
│                      使用者                                  │
└───────────────────────┬────────────────────────────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │  Azure Front Door     │ ← CDN + WAF + 全球加速
            │  (可選，提升效能)      │
            └───────────┬───────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
        ▼                               ▼
┌──────────────────┐          ┌────────────────────┐
│ Azure Static     │          │ Azure App Service  │
│ Web Apps         │          │ (Python/FastAPI)   │
│ (React 前端)     │          │ (後端 API)          │
└──────────────────┘          └─────────┬──────────┘
                                        │
                        ┌───────────────┼───────────────┐
                        │               │               │
                        ▼               ▼               ▼
              ┌─────────────┐  ┌──────────────┐  ┌────────────────┐
              │ Azure Blob  │  │ Azure AI     │  │ Azure Cosmos DB│
              │ Storage     │  │ Search       │  │ (可選，進階版)  │
              │ (檔案儲存)  │  │ (向量搜尋)   │  │                │
              └─────────────┘  └──────────────┘  └────────────────┘
                                        │
                                        ▼
                              ┌──────────────────┐
                              │ Azure OpenAI     │
                              │ Service          │
                              │ (GPT-4/Embeddings)│
                              └──────────────────┘
```

---

## 詳細服務說明

### 1. 前端部署：Azure Static Web Apps ⭐ 推薦

**為什麼選擇 Static Web Apps？**
- ✅ **完美適配 React + Vite**
- ✅ **自動化 CI/CD**（GitHub/Azure DevOps 整合）
- ✅ **免費 SSL 憑證**
- ✅ **全球 CDN 分發**
- ✅ **自訂域名支援**
- ✅ **免費層非常慷慨**（100 GB 頻寬/月）

**部署流程：**
```bash
# 1. 建立 Azure Static Web App
az staticwebapp create \
  --name ncu-course-explorer-frontend \
  --resource-group ncu-course-rg \
  --source https://github.com/your-repo \
  --location "East Asia" \
  --branch main \
  --app-location "/frontend" \
  --output-location "dist"

# 2. 設定環境變數（API endpoint）
# 在 Azure Portal 中設定：
# VITE_API_URL=https://ncu-api.azurewebsites.net
```

**靜態網站組態：**
```json
// staticwebapp.config.json
{
  "routes": [
    {
      "route": "/api/*",
      "rewrite": "https://ncu-api.azurewebsites.net/api/*"
    },
    {
      "route": "/*",
      "rewrite": "/index.html"
    }
  ],
  "navigationFallback": {
    "rewrite": "/index.html"
  }
}
```

---

### 2. 後端部署：Azure App Service (Python)

**為什麼選擇 App Service？**
- ✅ **原生支援 Python + FastAPI**
- ✅ **自動擴展**（根據流量）
- ✅ **內建負載平衡**
- ✅ **支援 WebSocket**（未來可能需要）
- ✅ **簡單的 CI/CD 整合**
- ✅ **Log 管理和監控**

**規格建議：**
- **開發/測試環境**: Basic B1 (1 Core, 1.75 GB RAM) - 約 NT$ 450/月
- **正式環境**: Standard S1 (1 Core, 1.75 GB RAM) - 約 NT$ 2,000/月
- **高流量**: Premium P1V2 (1 Core, 3.5 GB RAM) - 約 NT$ 2,800/月

**部署流程：**
```bash
# 1. 建立 App Service Plan
az appservice plan create \
  --name ncu-course-plan \
  --resource-group ncu-course-rg \
  --sku B1 \
  --is-linux

# 2. 建立 Web App
az webapp create \
  --name ncu-course-api \
  --resource-group ncu-course-rg \
  --plan ncu-course-plan \
  --runtime "PYTHON:3.11"

# 3. 部署程式碼
cd backend
zip -r backend.zip .
az webapp deploy \
  --resource-group ncu-course-rg \
  --name ncu-course-api \
  --src-path backend.zip
```

**startup.sh 配置：**
```bash
#!/bin/bash
python -m pip install --upgrade pip
pip install -r requirements.txt
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:8000
```

---

### 3. 資料儲存層（三層架構）

#### Layer 1: Azure Blob Storage（原始資料層）

**為什麼選擇 Blob Storage？**
- ✅ **超便宜**（Hot tier: $0.0184/GB/月）
- ✅ **高可用性**（99.9% SLA）
- ✅ **支援大檔案**（最大 5 TB/檔案）
- ✅ **CDN 整合**
- ✅ **版本控制和備份**
- ✅ **不可變儲存**（適合法規遵循）

**儲存結構設計：**
```
ncu-course-storage/
├── raw/                          # 原始資料（不可變）
│   ├── courses/
│   │   ├── 114_1/*.json         # 原始課程 JSON
│   │   └── 114_2/*.json
│   ├── projects/
│   │   └── 104-114/
│   │       ├── 資訊工程學系/
│   │       │   └── *.pdf        # 研究報告 PDF
│   │       └── [其他系所]/
│   └── admission/
│       └── ncu_caac.csv
│
└── processed/                    # 處理後檔案（備份用）
    ├── courses_backup.json
    └── projects_backup.json

⚠️ 注意：不要在 Blob Storage 存 embeddings！
```

**存取方式：**

**方案 A: 靜態檔案直接讀取**（推薦，簡單）
```python
# backend/app/config.py
BLOB_STORAGE_URL = "https://ncucourse.blob.core.windows.net"
COURSES_URL = f"{BLOB_STORAGE_URL}/data/processed/courses.json"

# backend/app/routes/courses.py
import requests

def load_courses():
    response = requests.get(COURSES_URL)
    return response.json()
```

**方案 B: Azure SDK**（進階，有認證）
```python
from azure.storage.blob import BlobServiceClient

connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
blob_service = BlobServiceClient.from_connection_string(connection_string)

def load_courses():
    blob_client = blob_service.get_blob_client(
        container="data",
        blob="processed/courses.json"
    )
    data = blob_client.download_blob().readall()
    return json.loads(data)
```

---

#### Layer 2: Azure Cosmos DB（結構化資料層）⭐ 新增

**為什麼需要 Cosmos DB？**
- ✅ **原生 NoSQL**：彈性 schema，適合非結構化資料
- ✅ **全球分散**：低延遲存取
- ✅ **自動擴展**：按需求付費
- ✅ **強大查詢**：SQL-like 語法
- ✅ **向量搜尋整合**（可選，但不推薦存 embedding）

**規格建議：**
- **開發/測試**: Serverless（按需計費）- 約 $0-30/月
- **正式環境**: Provisioned (400 RU/s) - 約 $750/月
- **高流量**: Autoscale (1000-4000 RU/s) - 約 $2,000-4,000/月

**Schema 設計（重點！）：**

```python
# 課程文檔結構
{
    "id": "course_114_1_CS101",
    "type": "course",
    "title": "計算機程式設計",

    # ⭐ 核心內容（從原始 JSON 提取和增強）
    "content": {
        "course_name_zh": "計算機程式設計",
        "course_name_en": "Computer Programming",
        "full_text": "課程目標 + 課程內容的完整文字",
        "course_objective": "培養學生程式設計能力...",
        "course_content": "1. Python 基礎 2. 資料結構...",
        "textbooks": "Python 程式設計入門",
        "grading": "期中考 30%, 期末考 30%, 作業 40%"
    },

    # ⭐ AI 生成的摘要
    "summary": {
        "short": "教授 Python 程式設計基礎（50字）",
        "medium": "本課程介紹程式設計基本概念，使用 Python 語言教學..（200字）",
        "high_school_friendly": "如果你對寫程式有興趣，這門課會從零開始教你..（高中生版）"
    },

    # ⭐ Metadata（用於篩選和查詢）
    "metadata": {
        "college": "資訊電機學院",
        "department": "資訊工程學系",
        "instructor": "王教授",
        "credits": 3,
        "required_elective": "必修",
        "semester": "114_1",
        "semester_display": "上學期",
        "year": 2024,
        "tags": ["程式設計", "Python", "入門"],
        "level": "大一"
    },

    # 參考資訊
    "references": {
        "blob_path": "raw/courses/114_1/資訊電機學院_資訊工程學系.json",
        "original_id": "CS101",
        "related_courses": ["CS102", "CS201"]
    },

    # 統計資訊
    "stats": {
        "views": 0,
        "searches": 0,
        "recommendations": 0
    },

    # 系統欄位
    "_timestamp": "2024-03-22T10:00:00Z",
    "_version": "1.0"
}

# ⚠️ 重點：沒有 embedding 欄位！
# embedding 只存在 Azure AI Search
```

```python
# 研究計畫文檔結構
{
    "id": "proj_109_H_001",
    "type": "project",
    "title": "基於深度學習的影像辨識系統",

    # ⭐ 核心內容（未來從 PDF 提取）
    "content": {
        "full_text": "研究動機、方法、結果的完整文字",
        "sections": {
            "abstract": "本研究探討...",
            "introduction": "研究動機與問題...",
            "methodology": "使用 CNN 模型...",
            "results": "準確率達 95%...",
            "conclusion": "結論..."
        },
        "keywords": ["深度學習", "CNN", "影像辨識"]
    },

    # ⭐ AI 生成的摘要
    "summary": {
        "short": "使用深度學習進行影像辨識研究",
        "medium": "本研究開發了基於 CNN 的影像辨識系統...",
        "high_school_friendly": "這個研究教電腦如何「看懂」圖片..."
    },

    # ⭐ Metadata
    "metadata": {
        "college": "資訊電機學院",
        "department": "資訊工程學系",
        "student_name": "王小明",
        "advisor": "李教授",
        "year": 2020,
        "type_code": "H",  # E/H/M/B
        "tags": ["人工智慧", "深度學習", "影像處理"]
    },

    # 參考資訊
    "references": {
        "pdf_path": "raw/projects/104-114/資訊工程學系/109H001_王小明_xxx.pdf",
        "pdf_url": "https://...",
        "related_projects": ["proj_110_E_005"]
    },

    # 統計資訊
    "stats": {
        "views": 0,
        "downloads": 0,
        "citations": 0
    }
}
```

**Cosmos DB 查詢範例：**

```python
# 範例 1: 結構化查詢
query = """
    SELECT c.title, c.summary, c.metadata
    FROM c
    WHERE c.type = 'course'
      AND c.metadata.department = '資訊工程學系'
      AND c.metadata.required_elective = '必修'
      AND c.metadata.credits >= 3
    ORDER BY c.metadata.semester DESC
"""

# 範例 2: 聚合查詢
query = """
    SELECT c.metadata.department, COUNT(1) as course_count
    FROM c
    WHERE c.type = 'course'
    GROUP BY c.metadata.department
    ORDER BY course_count DESC
"""

# 範例 3: 全文搜尋（Cosmos DB 內建）
query = """
    SELECT *
    FROM c
    WHERE CONTAINS(c.content.full_text, "深度學習")
      AND c.type = 'project'
"""
```

#### Layer 3: Azure AI Search（向量搜尋層）⭐ 推薦（取代 Qdrant）

**為什麼不用 Qdrant？**
- ❌ Qdrant 需要額外的 Container 或 VM 運行
- ❌ 增加維護複雜度
- ❌ 成本較高（需要持續運行）
- ❌ 需要自己管理擴展和備份

**為什麼選擇 Azure AI Search？**
- ✅ **原生向量搜尋支援**
- ✅ **整合 Azure OpenAI Embeddings**
- ✅ **自動擴展和管理**
- ✅ **強大的查詢語法**
- ✅ **內建 RAG 功能**
- ✅ **語意搜尋 + 關鍵字搜尋混合**

**規格建議：**
- **開發/測試**: Free (50 MB, 10K 文件) - 免費
- **正式環境**: Basic (2 GB, 1M 文件) - 約 NT$ 2,300/月
- **高流量**: Standard S1 (25 GB) - 約 NT$ 7,500/月

**設定流程：**

```bash
# 1. 建立 Azure AI Search 服務
az search service create \
  --name ncu-course-search \
  --resource-group ncu-course-rg \
  --sku basic \
  --location "East Asia"

# 2. 取得 API Key
az search admin-key show \
  --resource-group ncu-course-rg \
  --service-name ncu-course-search
```

**索引定義（輕量級，只存必要資訊）：**
```python
# scripts/setup_azure_search.py
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    VectorSearchProfile,
    HnswAlgorithmConfiguration
)

index_schema = SearchIndex(
    name="ncu-courses-index",
    fields=[
        # ⭐ 基本識別欄位
        SearchField(name="id", type=SearchFieldDataType.String, key=True),
        SearchField(name="type", type=SearchFieldDataType.String, filterable=True),

        # ⭐ 最小顯示資訊（用於快速預覽）
        SearchField(name="title", type=SearchFieldDataType.String, searchable=True),
        SearchField(name="short_summary", type=SearchFieldDataType.String),

        # ⭐ Metadata（用於篩選）
        SearchField(name="department", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchField(name="college", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchField(name="year", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
        SearchField(name="semester", type=SearchFieldDataType.String, filterable=True),
        SearchField(
            name="tags",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            filterable=True,
            facetable=True
        ),

        # 課程特有欄位
        SearchField(name="credits", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
        SearchField(name="required_elective", type=SearchFieldDataType.String, filterable=True),

        # ⭐⭐⭐ 向量欄位（核心！）
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=1536,  # OpenAI text-embedding-ada-002
            vector_search_profile_name="myHnswProfile",
        ),
    ],
    vector_search=VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="myHnsw",
                parameters={
                    "m": 4,  # 連接數（越大越準確，但越慢）
                    "efConstruction": 400,  # 建立索引時的精確度
                    "efSearch": 500,  # 搜尋時的精確度
                    "metric": "cosine"  # 相似度計算方式
                }
            )
        ],
        profiles=[
            VectorSearchProfile(
                name="myHnswProfile",
                algorithm_configuration_name="myHnsw",
            )
        ]
    ),
)

# ⚠️ 重點觀察：
# 1. 沒有存完整的 content、course_objective 等大欄位
# 2. 只存 title 和 short_summary 用於快速預覽
# 3. 完整資料從 Cosmos DB 取得
# 4. 這樣可以大幅減少索引大小和成本
```

**搜尋實作（三層架構整合）：**
```python
# backend/app/routes/course_search.py
from azure.search.documents import SearchClient
from azure.cosmos import CosmosClient
from azure.core.credentials import AzureKeyCredential
import openai

# 初始化客戶端
search_client = SearchClient(
    endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
    index_name="ncu-courses-index",
    credential=AzureKeyCredential(os.getenv("AZURE_SEARCH_KEY"))
)

cosmos_client = CosmosClient(
    url=os.getenv("COSMOS_ENDPOINT"),
    credential=os.getenv("COSMOS_KEY")
)
cosmos_container = cosmos_client.get_database_client("ncu-db") \
    .get_container_client("documents")

@router.post("/api/search")
async def search_courses(request: CourseSearchRequest):
    # ⭐ Step 1: 生成查詢向量
    response = openai.Embedding.create(
        model="text-embedding-ada-002",
        input=request.query
    )
    query_vector = response['data'][0]['embedding']

    # ⭐ Step 2: Azure AI Search 向量搜尋
    # 混合搜尋：語意 (向量) + 關鍵字
    search_results = search_client.search(
        search_text=request.query,  # 關鍵字搜尋（可選）
        vector_queries=[{
            "kind": "vector",
            "vector": query_vector,
            "k_nearest_neighbors": 20,  # 取 Top 20 候選
            "fields": "content_vector"
        }],
        filter=f"type eq 'course'",  # 只要課程
        select=["id", "title", "short_summary"],  # 只取基本資訊
        top=20
    )

    # ⭐ Step 3: 取得 document IDs
    doc_ids = [result['id'] for result in search_results]

    if not doc_ids:
        return {"results": [], "total": 0}

    # ⭐ Step 4: 從 Cosmos DB 批次查詢詳細資料
    # 使用 IN 查詢，一次取得所有文檔
    id_list = ",".join([f"'{id}'" for id in doc_ids])
    query = f"""
        SELECT c.id, c.title, c.summary, c.content, c.metadata
        FROM c
        WHERE c.id IN ({id_list})
    """

    detailed_results = list(cosmos_container.query_items(
        query=query,
        enable_cross_partition_query=True
    ))

    # ⭐ Step 5: 合併結果（保持 AI Search 的排序）
    # 建立 ID 到詳細資料的映射
    details_map = {doc['id']: doc for doc in detailed_results}

    # 按照 AI Search 的順序組織結果
    final_results = []
    for doc_id in doc_ids:
        if doc_id in details_map:
            doc = details_map[doc_id]
            final_results.append({
                "id": doc['id'],
                "title": doc['title'],
                "summary": doc['summary']['medium'],
                "department": doc['metadata']['department'],
                "college": doc['metadata']['college'],
                "credits": doc['metadata'].get('credits'),
                "tags": doc['metadata'].get('tags', [])
            })

    return {
        "results": final_results[:10],  # 只回傳 Top 10
        "total": len(final_results)
    }

# ⚡ 效能分析：
# - AI Search 向量搜尋: 10-50ms
# - Cosmos DB 批次查詢: 50-100ms
# - 總時間: < 200ms（比純資料庫快 100 倍！）
```

**進階：混合查詢（結構化 + 語意）：**
```python
@router.post("/api/search/advanced")
async def advanced_search(request: AdvancedSearchRequest):
    """
    支援複雜查詢：
    - 先用 Cosmos DB 做結構化篩選
    - 再用 AI Search 做語意搜尋
    """

    # ⭐ Step 1: Cosmos DB 結構化篩選
    filters = []
    if request.college:
        filters.append(f"c.metadata.college = '{request.college}'")
    if request.department:
        filters.append(f"c.metadata.department = '{request.department}'")
    if request.min_credits:
        filters.append(f"c.metadata.credits >= {request.min_credits}")

    where_clause = " AND ".join(filters) if filters else "1=1"

    query = f"""
        SELECT c.id
        FROM c
        WHERE c.type = 'course' AND {where_clause}
    """

    filtered_ids = [
        doc['id'] for doc in
        cosmos_container.query_items(query, enable_cross_partition_query=True)
    ]

    if not filtered_ids:
        return {"results": [], "total": 0}

    # ⭐ Step 2: AI Search 語意搜尋（加上 filter）
    query_vector = generate_embedding(request.query)

    # 使用 search.in() 函數過濾 IDs
    id_filter = " or ".join([f"id eq '{id}'" for id in filtered_ids])

    search_results = search_client.search(
        vector_queries=[{
            "vector": query_vector,
            "k_nearest_neighbors": 20,
            "fields": "content_vector"
        }],
        filter=id_filter,  # ⭐ 關鍵：只在篩選後的文檔中搜尋
        select=["id"],
        top=20
    )

    # ⭐ Step 3: 取得詳細資料（同上）
    # ...

# 📊 這種方式的優勢：
# 1. 精確的結構化篩選（Cosmos DB）
# 2. 強大的語意理解（AI Search）
# 3. 兩者結合 = 最佳查詢體驗
```

---

## 資料層實作細節

### 完整的資料處理 Pipeline

```python
# scripts/data_pipeline.py
"""
完整的 ETL Pipeline：
Blob Storage → Cosmos DB → Azure AI Search
"""

import json
import openai
from azure.storage.blob import BlobServiceClient
from azure.cosmos import CosmosClient
from azure.search.documents import SearchClient

class DataPipeline:
    def __init__(self):
        self.blob_client = BlobServiceClient.from_connection_string(...)
        self.cosmos_client = CosmosClient(...)
        self.search_client = SearchClient(...)
        self.cosmos_container = self.cosmos_client.get_database_client("ncu-db") \
            .get_container_client("documents")

    def process_course_data(self):
        """處理課程資料的完整流程"""

        # ⭐ Step 1: 從 Blob Storage 讀取原始資料
        blob_client = self.blob_client.get_blob_client(
            container="data",
            blob="processed/courses.json"
        )
        courses_data = json.loads(blob_client.download_blob().readall())

        print(f"📥 從 Blob Storage 讀取 {len(courses_data)} 筆課程")

        # ⭐ Step 2: 轉換並存入 Cosmos DB
        cosmos_docs = []
        for course in courses_data:
            # 建立 Cosmos DB 文檔
            doc = {
                "id": f"course_{course['serial_no']}",
                "type": "course",
                "title": course['course_name_zh'],

                "content": {
                    "course_name_zh": course['course_name_zh'],
                    "course_name_en": course['course_name_en'],
                    "full_text": f"{course.get('course_objective', '')} {course.get('course_content', '')}",
                    "course_objective": course.get('course_objective', ''),
                    "course_content": course.get('course_content', ''),
                },

                # TODO: 使用 GPT 生成摘要
                "summary": {
                    "short": course['course_name_zh'][:50],
                    "medium": course.get('course_objective', '')[:200],
                    "high_school_friendly": ""  # 需要 GPT 生成
                },

                "metadata": {
                    "college": course['college'],
                    "department": course['department'],
                    "instructor": course['instructor'],
                    "credits": course['credits'],
                    "required_elective": course['required_elective'],
                    "semester": course.get('semester', ''),
                    "semester_display": course.get('semester_display', ''),
                    "year": int(course.get('semester', '114_1').split('_')[0]),
                    "tags": []  # TODO: 使用 NLP 提取標籤
                },

                "references": {
                    "blob_path": f"raw/courses/{course['semester']}/...",
                    "original_id": course['course_id']
                },

                "stats": {
                    "views": 0,
                    "searches": 0
                },

                "_timestamp": datetime.utcnow().isoformat()
            }

            cosmos_docs.append(doc)

        # 批次寫入 Cosmos DB
        for doc in cosmos_docs:
            self.cosmos_container.upsert_item(doc)

        print(f"✓ 已存入 Cosmos DB: {len(cosmos_docs)} 筆")

        # ⭐ Step 3: 生成 Embeddings 並存入 AI Search
        search_docs = []
        for doc in cosmos_docs:
            # 生成 embedding（批次處理以節省成本）
            text_to_embed = f"{doc['title']} {doc['content']['course_objective']}"

            embedding = openai.Embedding.create(
                model="text-embedding-ada-002",
                input=text_to_embed
            )['data'][0]['embedding']

            # 準備 AI Search 文檔（輕量級）
            search_doc = {
                "id": doc['id'],
                "type": doc['type'],
                "title": doc['title'],
                "short_summary": doc['summary']['short'],
                "department": doc['metadata']['department'],
                "college": doc['metadata']['college'],
                "year": doc['metadata']['year'],
                "semester": doc['metadata']['semester'],
                "credits": doc['metadata']['credits'],
                "required_elective": doc['metadata']['required_elective'],
                "tags": doc['metadata']['tags'],
                "content_vector": embedding  # ⭐ 只有這裡有 embedding
            }

            search_docs.append(search_doc)

        # 批次上傳到 AI Search
        self.search_client.upload_documents(documents=search_docs)
        print(f"✓ 已存入 AI Search: {len(search_docs)} 筆（含 embeddings）")

        return len(cosmos_docs)

    def generate_summaries_with_gpt(self, docs):
        """使用 GPT 批次生成摘要"""
        for doc in docs:
            prompt = f"""
            請為以下課程生成三個版本的摘要：
            課程名稱: {doc['title']}
            課程目標: {doc['content']['course_objective']}
            課程內容: {doc['content']['course_content']}

            請以 JSON 格式回傳：
            {{
                "short": "一句話摘要（50字以內）",
                "medium": "段落摘要（200字以內）",
                "high_school_friendly": "高中生版本（用簡單的話解釋這門課在學什麼）"
            }}
            """

            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )

            summary = json.loads(response.choices[0].message.content)
            doc['summary'] = summary

        return docs

# 執行 Pipeline
if __name__ == "__main__":
    pipeline = DataPipeline()
    pipeline.process_course_data()
```

### 資料同步策略

```python
# scripts/sync_service.py
"""
保持三層資料同步的服務
"""

class DataSyncService:
    def __init__(self):
        self.cosmos_container = ...
        self.search_client = ...

    async def sync_document(self, doc_id: str, doc_type: str):
        """
        同步單一文檔：
        Cosmos DB → AI Search
        """

        # 1. 從 Cosmos DB 讀取
        cosmos_doc = self.cosmos_container.read_item(
            item=doc_id,
            partition_key=doc_type
        )

        # 2. 檢查是否需要更新 embedding
        needs_embedding = (
            not cosmos_doc.get('_embedding_synced') or
            cosmos_doc.get('_content_updated')
        )

        if needs_embedding:
            # 生成新的 embedding
            text = f"{cosmos_doc['title']} {cosmos_doc['content']['full_text']}"
            embedding = self.generate_embedding(text)

            # 更新 AI Search
            search_doc = {
                "id": cosmos_doc['id'],
                "type": cosmos_doc['type'],
                "title": cosmos_doc['title'],
                "short_summary": cosmos_doc['summary']['short'],
                **cosmos_doc['metadata'],
                "content_vector": embedding
            }

            self.search_client.merge_or_upload_documents([search_doc])

            # 標記已同步
            cosmos_doc['_embedding_synced'] = True
            cosmos_doc['_content_updated'] = False
            cosmos_doc['_last_sync'] = datetime.utcnow().isoformat()

            self.cosmos_container.upsert_item(cosmos_doc)

            print(f"✓ 同步完成: {doc_id}")

    async def handle_cosmos_change_feed(self):
        """
        監聽 Cosmos DB Change Feed
        當資料更新時自動同步到 AI Search
        """

        # Cosmos DB Change Feed 配置
        async for changes in self.cosmos_container.query_items_change_feed():
            for changed_doc in changes:
                await self.sync_document(
                    doc_id=changed_doc['id'],
                    doc_type=changed_doc['type']
                )

# 📊 同步策略：
# 1. 即時同步：Change Feed（推薦）
# 2. 定時同步：每日凌晨批次處理
# 3. 手動同步：管理後台觸發
```

---

### 5. AI 服務：Azure OpenAI Service

**為什麼選擇 Azure OpenAI？**
- ✅ **企業級 SLA**（99.9% 可用性）
- ✅ **資料隱私保證**（不會用於訓練）
- ✅ **區域部署**（東亞資料中心）
- ✅ **整合 Azure 生態系**
- ✅ **成本控制和配額管理**

**可用模型：**
- `gpt-4` - 用於複雜查詢理解
- `gpt-35-turbo` - 用於一般對話
- `text-embedding-ada-002` - 用於向量化

**申請流程：**
```bash
# 1. 申請 Azure OpenAI 存取（需審核，約 1-2 週）
# https://aka.ms/oai/access

# 2. 建立 Azure OpenAI 資源
az cognitiveservices account create \
  --name ncu-course-openai \
  --resource-group ncu-course-rg \
  --kind OpenAI \
  --sku S0 \
  --location "East US"  # 注意：目前只有特定區域支援

# 3. 部署模型
az cognitiveservices account deployment create \
  --name ncu-course-openai \
  --resource-group ncu-course-rg \
  --deployment-name gpt-4 \
  --model-name gpt-4 \
  --model-version "0613" \
  --model-format OpenAI \
  --sku-capacity 10 \
  --sku-name "Standard"
```

**使用方式：**
```python
# backend/app/config.py
import openai

openai.api_type = "azure"
openai.api_base = os.getenv("AZURE_OPENAI_ENDPOINT")
openai.api_version = "2023-05-15"
openai.api_key = os.getenv("AZURE_OPENAI_KEY")

# backend/app/routes/course_search.py
def generate_course_summary(course_data):
    response = openai.ChatCompletion.create(
        engine="gpt-4",  # 部署名稱
        messages=[
            {"role": "system", "content": "你是一個專業的課程顧問，幫助高中生理解大學課程。"},
            {"role": "user", "content": f"請用高中生能理解的方式說明這門課：{course_data}"}
        ],
        temperature=0.7,
        max_tokens=500
    )
    return response.choices[0].message.content
```

---

### 6. 資料庫選項（可選，進階版）

#### 選項 A: 繼續使用 JSON + Blob Storage（推薦，成本最低）
- ✅ 簡單、便宜
- ✅ 當前資料結構完美適配
- ⚠️ 無法高效處理複雜查詢
- ⚠️ 無法支援即時更新

#### 選項 B: Azure Cosmos DB（NoSQL，向量搜尋整合）
**優點：**
- ✅ **原生支援向量搜尋**（可完全取代 Qdrant + AI Search）
- ✅ 全球分散式
- ✅ 自動擴展
- ✅ 彈性 schema
- ✅ 支援 MongoDB API（易於遷移）

**成本：**
- Serverless: $0.25/百萬 RU（請求單位）
- 預配輸送量: 約 NT$ 750/月（400 RU/s）

**何時考慮？**
- 🔹 需要即時更新課程資料
- 🔹 需要複雜的查詢和聚合
- 🔹 需要全球多區域部署
- 🔹 未來可能大幅擴充功能

```python
# 使用 Cosmos DB 的向量搜尋
from azure.cosmos import CosmosClient

cosmos_client = CosmosClient(
    url=os.getenv("COSMOS_ENDPOINT"),
    credential=os.getenv("COSMOS_KEY")
)

database = cosmos_client.get_database_client("ncu-course-db")
container = database.get_container_client("courses")

# 向量搜尋查詢
query = """
SELECT TOP 10 c.course_name_zh, c.department,
       VectorDistance(c.content_vector, @query_vector) as similarity
FROM c
ORDER BY VectorDistance(c.content_vector, @query_vector)
"""

results = container.query_items(
    query=query,
    parameters=[{"name": "@query_vector", "value": query_embedding}],
    enable_cross_partition_query=True
)
```

#### 選項 C: Azure SQL Database（關聯式資料庫）
**優點：**
- ✅ 強大的 SQL 查詢
- ✅ ACID 交易保證
- ✅ 成熟的管理工具

**成本：**
- Basic: 約 NT$ 150/月（2 GB）
- Standard S0: 約 NT$ 450/月（250 GB）

**何時考慮？**
- 🔹 需要複雜的關聯查詢
- 🔹 需要資料完整性約束
- 🔹 團隊熟悉 SQL

---

## 成本估算

### 方案 A: 基礎版（推薦用於初期）⭐

**適合：開發、測試、小規模部署（<1,000 使用者/天）**

| 服務 | 規格 | 月費用（TWD） | 說明 |
|------|------|--------------|------|
| **前端** | | | |
| Azure Static Web Apps | Free tier | $0 | 100 GB 頻寬/月 |
| **後端** | | | |
| Azure App Service | Basic B1 | $450 | 1 Core, 1.75 GB RAM |
| **資料層** | | | |
| Azure Blob Storage | 1 GB Hot tier | $1 | 原始檔案 |
| **Azure Cosmos DB** | **Serverless** | **$30-100** | **按請求計費** |
| Azure AI Search | Free tier | $0 | 50 MB, 10K 文件 |
| **AI 服務** | | | |
| Azure OpenAI | Pay-as-you-go | $300-1,000 | ~10K 次查詢/月 |
| **總計** | | **$780-1,550/月** | |

**💡 成本節省技巧：**
- Cosmos DB 使用 Serverless（開發階段可能只需 $20-30/月）
- AI Search 免費層足夠初期使用
- OpenAI 設定使用上限避免超支

---

### 方案 B: 正式版（推薦用於正式上線）⭐⭐⭐

**適合：正式上線、中等流量（1,000-10,000 使用者/天）**

| 服務 | 規格 | 月費用（TWD） | 說明 |
|------|------|--------------|------|
| **前端** | | | |
| Azure Static Web Apps | Standard | $300 | 自訂域名、進階功能 |
| **後端** | | | |
| Azure App Service | Standard S1 | $2,000 | 1 Core, 1.75 GB, 自動擴展 |
| **資料層** | | | |
| Azure Blob Storage | 5 GB Hot tier | $5 | 原始檔案 + 備份 |
| **Azure Cosmos DB** | **400 RU/s** | **$750** | **足夠中等流量** |
| Azure AI Search | Basic | $2,300 | 2 GB, 1M 文件 |
| **AI 服務** | | | |
| Azure OpenAI | Pay-as-you-go | $1,000-3,000 | ~50K 次查詢/月 |
| **可選** | | | |
| Azure Front Door (CDN) | 可選 | $500-1,500 | 全球加速 |
| **總計** | | **$6,355-9,855/月** | **無 CDN: $5,855-8,355** |

**📊 流量預估：**
- 10,000 使用者/天
- 每人 5 次查詢 = 50,000 次/天
- Cosmos DB: ~150,000 讀取請求/天（在 400 RU/s 範圍內）

---

### 方案 C: 企業版（高流量、高可用）

**適合：大規模部署（>10,000 使用者/天）、企業級 SLA**

| 服務 | 規格 | 月費用（TWD） | 說明 |
|------|------|--------------|------|
| **前端** | | | |
| Azure Static Web Apps | Standard | $300 | |
| **後端** | | | |
| Azure App Service | Premium P1V2 (×2) | $5,600 | 雙實例高可用 |
| **資料層** | | | |
| Azure Blob Storage | 20 GB Hot + CDN | $50 | |
| **Azure Cosmos DB** | **Autoscale 1000-4000 RU/s** | **$2,500-4,000** | **按需擴展** |
| Azure AI Search | Standard S1 | $7,500 | 25 GB, 高效能 |
| **AI 服務** | | | |
| Azure OpenAI | Pay-as-you-go | $3,000-8,000 | ~200K 次查詢/月 |
| **營運** | | | |
| Azure Front Door | Standard | $1,500 | WAF + 全球加速 |
| Azure Monitor | 進階監控 | $800 | 詳細遙測 |
| Azure Application Insights | 包含在 App Service | $0 | |
| **總計** | | **$21,250-27,750/月** | |

**🚀 企業級特性：**
- 99.99% SLA
- 多區域部署
- 自動災難復原
- 詳細監控和告警

---

### 💰 成本對比分析

#### 資料層成本對比（最關鍵！）

**❌ 錯誤做法（把 Embedding 放 Cosmos DB）：**

```
3,316 門課程 × 6 KB embedding = 20 MB 額外資料

Cosmos DB (30 MB total):
- Provisioned 400 RU/s: $750/月
- 儲存成本: $7.5/月
- 額外 RU 消耗: +30% (傳輸 embedding)
────────────────────────────
總計: ~$1,000/月

效能:
- 查詢延遲: 2-5 秒 💀
- 無法擴展
```

**✅ 正確做法（三層架構）：**

```
Cosmos DB (10 MB, 純文字):
- Provisioned 400 RU/s: $750/月
- 儲存成本: $2.5/月

Azure AI Search (Basic):
- 固定成本: $2,300/月
- 包含向量索引

Blob Storage:
- $5/月
────────────────────────────
總計: ~$3,057/月

效能:
- 查詢延遲: 50-200ms ⚡
- 可擴展到百萬級

差距: 成本相近，但效能差 100 倍！
```

#### 每次查詢成本分析

| 方案 | 查詢延遲 | 每次查詢成本 | 1,000 次查詢 |
|------|---------|-------------|-------------|
| **三層架構** | 50-200ms | $0.0006 | $0.60 |
| Embedding 在 DB | 2-5 秒 | $0.015 | $15.00 |

**差距：25 倍！**

---

## 部署步驟

### 階段 1: 準備階段（1-2 天）

#### 1.1 建立 Azure 帳號和訂閱
```bash
# 安裝 Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# 登入
az login

# 設定訂閱
az account set --subscription "YOUR_SUBSCRIPTION_ID"
```

#### 1.2 建立資源群組
```bash
az group create \
  --name ncu-course-rg \
  --location "East Asia"
```

#### 1.3 建立 Blob Storage
```bash
# 建立儲存體帳戶
az storage account create \
  --name ncucoursestorage \
  --resource-group ncu-course-rg \
  --location "East Asia" \
  --sku Standard_LRS

# 建立容器
az storage container create \
  --account-name ncucoursestorage \
  --name data \
  --public-access blob

# 上傳資料
az storage blob upload-batch \
  --account-name ncucoursestorage \
  --destination data \
  --source ./data/processed/
```

### 階段 2: 後端部署（半天）

#### 2.1 準備 requirements.txt
```txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-multipart==0.0.6
pydantic==2.5.0
openai==1.3.0
azure-search-documents==11.4.0
azure-storage-blob==12.19.0
python-dotenv==1.0.0
```

#### 2.2 建立 App Service
```bash
# 建立 App Service Plan
az appservice plan create \
  --name ncu-course-plan \
  --resource-group ncu-course-rg \
  --sku B1 \
  --is-linux

# 建立 Web App
az webapp create \
  --name ncu-course-api \
  --resource-group ncu-course-rg \
  --plan ncu-course-plan \
  --runtime "PYTHON:3.11"

# 設定環境變數
az webapp config appsettings set \
  --resource-group ncu-course-rg \
  --name ncu-course-api \
  --settings \
    AZURE_STORAGE_ACCOUNT="ncucoursestorage" \
    AZURE_SEARCH_ENDPOINT="https://ncu-course-search.search.windows.net" \
    AZURE_SEARCH_KEY="YOUR_SEARCH_KEY" \
    AZURE_OPENAI_ENDPOINT="https://ncu-course-openai.openai.azure.com/" \
    AZURE_OPENAI_KEY="YOUR_OPENAI_KEY"

# 部署
cd backend
zip -r ../backend.zip .
az webapp deploy \
  --resource-group ncu-course-rg \
  --name ncu-course-api \
  --src-path ../backend.zip \
  --type zip
```

### 階段 3: Azure AI Search 設定（1 天）

#### 3.1 建立搜尋服務
```bash
az search service create \
  --name ncu-course-search \
  --resource-group ncu-course-rg \
  --sku basic \
  --location "East Asia"
```

#### 3.2 匯入課程資料
```bash
cd scripts
python setup_azure_search.py
python import_to_azure_search.py
```

### 階段 4: 前端部署（半天）

#### 4.1 修改環境變數
```bash
# frontend/.env.production
VITE_API_URL=https://ncu-course-api.azurewebsites.net/api
```

#### 4.2 部署到 Static Web Apps
```bash
# 方法 1: 透過 Azure Portal（推薦）
# 1. 前往 Azure Portal
# 2. 建立 Static Web App
# 3. 連結 GitHub repository
# 4. 設定 build configuration

# 方法 2: 透過 CLI
az staticwebapp create \
  --name ncu-course-frontend \
  --resource-group ncu-course-rg \
  --source https://github.com/your-username/your-repo \
  --location "East Asia" \
  --branch main \
  --app-location "/frontend" \
  --output-location "dist" \
  --token YOUR_GITHUB_TOKEN
```

### 階段 5: 測試與驗證（1 天）

#### 5.1 健康檢查
```bash
# 測試後端 API
curl https://ncu-course-api.azurewebsites.net/health

# 測試課程查詢
curl https://ncu-course-api.azurewebsites.net/api/courses

# 測試搜尋功能
curl -X POST https://ncu-course-api.azurewebsites.net/api/course-search \
  -H "Content-Type: application/json" \
  -d '{"query": "人工智慧"}'
```

#### 5.2 效能測試
```bash
# 使用 Apache Bench
ab -n 1000 -c 10 https://ncu-course-api.azurewebsites.net/api/courses

# 使用 Azure Load Testing
az load create \
  --name ncu-course-load-test \
  --resource-group ncu-course-rg \
  --test-id test-001
```

---

## 替代方案比較

### 向量搜尋方案比較

| 方案 | 優點 | 缺點 | 月成本 | 推薦度 |
|------|------|------|--------|--------|
| **Qdrant (自架)** | • 開源免費<br>• 功能完整 | • 需要 Container/VM<br>• 自己維護<br>• 擴展複雜 | $1,500-3,000 | ⭐⭐ |
| **Azure AI Search** | • 全託管<br>• 整合 Azure<br>• 自動擴展 | • 成本較高<br>• 學習曲線 | $0-2,300 | ⭐⭐⭐⭐⭐ |
| **Cosmos DB** | • 向量搜尋內建<br>• NoSQL 彈性<br>• 全球分散 | • 成本高<br>• 複雜度高 | $750-5,000 | ⭐⭐⭐⭐ |
| **PostgreSQL + pgvector** | • 便宜<br>• SQL 熟悉 | • 效能較差<br>• 需自己維護向量 | $450-1,500 | ⭐⭐⭐ |

### 後端部署方案比較

| 方案 | 優點 | 缺點 | 月成本 | 推薦度 |
|------|------|------|--------|--------|
| **App Service** | • 簡單易用<br>• 自動擴展<br>• 內建 CI/CD | • 成本較高<br>• 冷啟動（低階層） | $450-2,800 | ⭐⭐⭐⭐⭐ |
| **Container Instances** | • 彈性<br>• 按秒計費 | • 需要容器化<br>• 管理較複雜 | $300-2,000 | ⭐⭐⭐⭐ |
| **Azure Functions** | • Serverless<br>• 按使用計費 | • 冷啟動延遲<br>• 不適合長時間執行 | $0-1,000 | ⭐⭐⭐ |
| **Virtual Machine** | • 完全控制<br>• 便宜（長期） | • 需要自己維護<br>• 管理複雜 | $600-2,500 | ⭐⭐ |

---

## 最終推薦配置

### 🏆 推薦方案（平衡效能與成本）

```
前端: Azure Static Web Apps (Free)
後端: Azure App Service (Basic B1)
資料: Azure Blob Storage (Hot tier)
搜尋: Azure AI Search (Free → Basic)
AI: Azure OpenAI Service (Pay-as-you-go)
```

**總成本: $750-1,500/月（初期）→ $5,000-7,000/月（正式）**

### 💡 成本節省建議

1. **使用 Azure for Students**（如果適用）
   - $100 免費額度
   - 12 個月免費服務

2. **善用免費層**
   - Static Web Apps: Free
   - AI Search: Free (開發用)
   - Blob Storage: 5 GB 免費

3. **按需擴展**
   - 從 Basic 開始
   - 監控使用量
   - 逐步升級

4. **資料優化**
   - 壓縮 JSON 檔案
   - 啟用 CDN 快取
   - 減少不必要的 API 呼叫

---

## 附錄：完整的環境變數清單

```bash
# frontend/.env.production
VITE_API_URL=https://ncu-course-api.azurewebsites.net/api

# backend/.env
AZURE_STORAGE_ACCOUNT=ncucoursestorage
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;...
AZURE_SEARCH_ENDPOINT=https://ncu-course-search.search.windows.net
AZURE_SEARCH_KEY=YOUR_SEARCH_ADMIN_KEY
AZURE_OPENAI_ENDPOINT=https://ncu-course-openai.openai.azure.com/
AZURE_OPENAI_KEY=YOUR_OPENAI_KEY
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-ada-002
CORS_ORIGINS=https://ncu-course-frontend.azurestaticapps.net
```

---

## 後續步驟

1. ✅ 建立 Azure 帳號（免費試用）
2. ✅ 申請 Azure OpenAI 存取權限（需審核）
3. ✅ 準備 GitHub repository（用於 CI/CD）
4. ✅ 依照部署步驟逐步執行
5. ✅ 設定監控和告警
6. ✅ 進行負載測試
7. ✅ 正式上線

---

**文件版本**: v1.0
**最後更新**: 2026-03-22
**作者**: NCU 科系探索系統開發團隊
