# GraphRAG 問答系統規劃

> 建立時間：2026-04-07  
> 更新時間：2026-04-14（依實際資料重新盤點）  
> 前置：知識圖譜三源整合已完成（`data/processed/knowledge_graph.gpickle`）  
> 前置：NLP 萃取六支檔案已完成（`data/processed/nlp/`）

---

## 一、實際資料盤點

### 1.1 課程原始資料

| 路徑 | 筆數 | 主要欄位 |
|------|------|---------|
| `data/raw/courses/114_1/*.json` | ~3,598 筆（合計） | 課程目標、授課內容、教科書/參考書、授課教師、學分、選修別、分發條件、課程綱要 |
| `data/raw/courses/114_2/*.json` | ↑ 同上（不同學期） | 同上 |
| `data/raw/graduate_courses/114_1+2/*.json` | 959 筆 | 同上（研究所課程） |
| `data/raw/scraped_missing/courses.json` | 若干筆 | 補充漏爬課程 |

> 課程綱要完整欄位：課程目標、授課內容、教科書/參考書、自編教材比例、授課方式、評量配分比重、辦公時間、課程領域、核心能力

### 1.2 NLP 萃取結果（已完成，可直接用）

| 檔案 | 涵蓋課程數 | 內容 |
|------|-----------|------|
| `nlp/nlp_tech_nodes.json` | 2,505 筆 | 每門課的 `languages`、`tools`、`concepts` |
| `nlp/nlp_simplified_concepts.json` | 2,252 筆 | 技術名詞→白話解釋對照（`original` + `display`） |
| `nlp/nlp_domain_tags.json` | 3,114 筆 | 領域標籤（部分 skipped） |
| `nlp/nlp_topic_tags.json` | 124 筆 | 通識課的主題標籤 + 核心問題 |
| `nlp/nlp_professor_links.json` | 2,505 筆 | 每門課連結的教授與其研究領域 |
| `nlp/dept_professor_map.json` | 54 個系所 | 系所專業詞彙庫 |

### 1.3 應修科目（修課規劃）資料

| 路徑 | 涵蓋系所 | 內容 |
|------|---------|------|
| `data/processed/schedule_draft/[學院]/[系所].json` | 28 個系所 | `required_courses`（含 `when`：大一上~大一下、`verified`）、`elective_groups`（含選修學分門檻）、`graduation_rules`、`certifications` |

> `when` 欄位已透過 PDF 解析填入，待人工驗證（`verified: false`）。現在即可作為 metadata 儲存，驗證完成後不需重建索引。

### 1.4 學分學程資料

| 路徑 | 筆數 | 內容 |
|------|------|------|
| `data/processed/credit_programs/*.json` | 11 個學院檔，共 39+ 個學程 | 學程 id、名稱、必/選修課程列表（含課號）、最低學分 |
| `data/processed/program_descriptions.json` | 39 個學程 | 學程描述自由文字（from pdfplumber）|

### 1.5 教師官方資料

| 路徑 | 筆數 | 內容 |
|------|------|------|
| `data/raw/114_ulistteacher.csv` | 1,009 筆 | 系所名稱、聘書職級（教授/副教授/助理教授/講師）、專兼任、教師名稱、**教師專長**（逗號分隔） |

> **與 NLP 資料的關係：**
> - CSV = 教育部官方申報的教師專長（權威來源，1,009 人全部有填）
> - `nlp_professor_links.json` = 從課程內容 LLM 推算的師生關聯（859 人，100% 在 CSV 中）
> - 課程 JSON 的授課教師有 673 位可和 CSV 直接對到名字
> - **兩者互補**：CSV 用於「找專長 X 的教授」；NLP links 用於「這門課涉及哪些教授的研究領域」

### 1.6 系所介紹

| 路徑 | 筆數 | 內容 |
|------|------|------|
| `data/raw/collego_ncu.json` | 32 個系所 | 學系特色、學科意涵、學習方法、生涯進路、能力特質（Collego 來源） |

---

## 二、核心決策

### Q1：NLP 萃取要不要重做？

**結論：不需要。** `data/processed/nlp/` 六支檔案已備妥。
在建立向量索引時，直接把 NLP 結果合併進 document text 與 metadata 即可。

### Q2：schedule_draft 的 `when` 欄位如何用？

**結論：現在就能用，不等驗證完成。**

`when` 值為「大一上」、「大一上~大二下」等格式（無年級的「僅上/下學期」選項已移除）。

解析後存入以下 metadata 欄位：

| 欄位 | 型態 | 說明 | 範例 |
|------|------|------|------|
| `when_raw` | str | 原始字串，供前端直接顯示 | `"大一上~大二下"` |
| `when_year_start` | int | 起始年（0 = 未填） | `1` |
| `when_year_end` | int | 結束年（0 = 未填） | `2` |
| `when_sem_start` | int | 起始學期（1=上/2=下，0=未填） | `1` |
| `when_sem_end` | int | 結束學期（0=未填） | `2` |
| `when_semesters` | str | 逗號分隔的覆蓋學期代碼，供 `$contains` 過濾 | `"1_1,1_2,2_1,2_2"` |
| `schedule_verified` | bool | 人工驗證完成旗標 | `false` |

過濾範例：
- 查「大一下的課」→ `{"when_semesters": {"$contains": "1_2"}}`
- 查「大三開的課」→ `{"$or": [{"when_semesters": {"$contains": "3_1"}}, {"when_semesters": {"$contains": "3_2"}}]}`

前端顯示時直接用 `when_raw`；`schedule_verified: false` 時加上「資訊待確認」提示。  
人工驗證完成後只需更新 metadata，不需重建 embedding。

### Q3：向量文件怎麼組成最佳？

**結論：分層組裝——核心文字 + NLP 白話擴充。**

```
文件 = 課程名稱（中英）
     + 課程目標（原文）
     + 授課內容（原文）
     + simplified_concepts 白話解釋（讓語意搜尋更自然）
     + topic_tags（通識課專用）
```

技術節點（languages/tools/concepts）存 metadata，供 structured filter 使用，不混入 embedding 文字（避免 embedding 被技術詞彙拉偏）。

---

## 三、ChromaDB Collection 設計

### Collection 1：`ncu_courses_ug`（大學部課程）

**文件數量**：約 3,600 筆（114_1 + 114_2 去重後）

**Document text 組裝：**
```
{課程名稱(中文)} ({課程名稱(英文)})
課程目標：{課程目標}
授課內容：{授課內容}
{simplified_concepts 的 display 欄位，每個一行（若有）}
{topic_tags（若有，通識課）}
```

**Metadata 欄位：**
```json
{
  "course_code":    "CE1001",
  "name_zh":        "計算機概論 Ⅰ",
  "name_en":        "Introduction to Computer Science Ⅰ",
  "dept":           "資訊工程學系",
  "college":        "資訊電機學院",
  "credits":        3,
  "type":           "必修",
  "semester":       1,
  "academic_year":  "114",
  "languages":      ["Python", "C++"],
  "tools":          ["PyTorch", "Docker"],
  "concepts":       ["資料結構", "演算法"],
  "domain_tags":    ["資訊工程", "系統軟體"],
  "required_year":  1,
  "required_sem":   1,
  "verified":       false
}
```

> `required_year` / `required_sem` 只有在 schedule_draft 中明確列為必修的課才填入；選修課留 null。

---

### Collection 2：`ncu_courses_grad`（研究所課程）

**文件數量**：約 960 筆

結構同 `ncu_courses_ug`，type 欄固定為 `"研究所"`。

---

### Collection 3：`ncu_credit_programs`（學分學程）

**文件數量**：39 個學程

**Document text：**
```
{學程名稱}（{學院}，最低 {min_credits} 學分）
{program_descriptions.json 的 description 自由文字}
包含課程：{required_courses 名稱} / {elective_groups 課程名稱列表}
```

**Metadata：**
```json
{
  "program_id":    "ai_technology",
  "program_name":  "「人工智慧技術應用」國際學分學程",
  "college":       "資電學院",
  "min_credits":   15,
  "cross_school":  false
}
```

---

### Collection 4：`ncu_teachers`（教師專長）

**文件數量**：1,009 筆

**Document text 組裝：**
```
{教師名稱}（{系所名稱}，{聘書職級}，{專兼任}）
專長：{教師專長（逗號拆成分行）}
```

**Metadata 欄位：**
```json
{
  "name":       "施國琛",
  "dept":       "資訊工程學系",
  "rank":       "教授",
  "type":       "專任",
  "specialties": ["演算法", "計算理論", "生物資訊"]
}
```

> **用途：**
> - 「哪位教授專長是機器學習？」→ 向量搜尋 `ncu_teachers`
> - 「施教授的研究領域是什麼？」→ 直接 metadata filter by name
>
> **課程 metadata 擴充：** 建立 `ncu_courses_ug` 時，若 `授課教師` 可對到 CSV，則附加 `teacher_specialties` 到課程 metadata，使「找教 X 的課」同時能命中老師的官方專長。

---

### Collection 5：`ncu_departments`（系所介紹）

**文件數量**：32 個系所

**Document text：**
```
{dept_name}
學系特色：{學系特色}
學科意涵：{學科意涵}
學習方法：{學習方法列表}
生涯進路：{生涯進路}
能力特質：{能力特質}
```

**Metadata：**
```json
{
  "dept_name": "資訊工程學系",
  "dept_id":   "016001"
}
```

---

## 四、整體問答架構

```
用戶問題
    │
    ▼
FastAPI 後端  POST /api/chat
    │
    ├─ 意圖分類（輕量 Regex / few-shot）
    │   ├─ 語意類：「計算機概論在講什麼？」        → 向量搜尋
    │   ├─ 技術找課：「有哪些課教 PyTorch？」      → metadata filter（tools）
    │   ├─ 結構類：「資工系必修有哪些？」           → 圖查詢
    │   ├─ 學程類：「量子技術學程要修哪些課？」     → 圖查詢 + 向量搜尋
    │   ├─ 年次類：「大一下有哪些必修？」           → metadata filter（required_year/sem）
    │   ├─ 路徑類：「線代修完下一步？」             → PREREQUISITE 邊遍歷（圖）
    │   ├─ 教師類：「哪位教授專長是機器學習？」     → ncu_teachers 向量搜尋
    │   └─ 系所類：「電機系適合什麼人？」           → ncu_departments 向量搜尋
    │
    ├─ 向量搜尋（ChromaDB）
    │   ├─ ncu_courses_ug / ncu_courses_grad
    │   ├─ ncu_credit_programs
    │   └─ ncu_departments
    │
    ├─ 圖查詢（NetworkX，載入 .gpickle）
    │   └─ 必修/選修結構、學程規定、教師、先修邊（若已建）
    │
    └─ Context 融合 → Azure OpenAI GPT-4o → 回答
```

---

## 五、技術選型

| 元件 | 工具 | 說明 |
|------|------|------|
| 向量 DB | **ChromaDB** | pip 安裝，零依賴，開發期夠用；後期可遷移 Qdrant |
| 圖 DB | **NetworkX**（.gpickle） | 已有，不需要 Neo4j |
| Embedding | **Azure OpenAI** `text-embedding-3-large` | 部署名稱由 `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` 指定 |
| LLM（問答） | **Azure OpenAI** `gpt-4o` | 部署名稱由 `AZURE_OPENAI_CHAT_DEPLOYMENT` 指定 |
| LLM（NLP） | 已完成，不需再跑 | — |

---

## 六、實作順序與對應檔案

### Phase 1：建立向量索引（ChromaDB）

```
scripts/rag/build_vector_index.py          ← 新建
```

**邏輯：**
1. 讀 `data/raw/courses/114_1+2/*.json`，合併兩學期（同課號保留最新學期）
2. 對每門課，從 NLP 六支檔案補充 simplified_concepts / domain_tags / tech_nodes
3. 對每門課，從 schedule_draft 補充 required_year / required_sem / verified
4. 組裝 document text + metadata，寫入 ChromaDB `ncu_courses_ug`
5. 同理處理研究所課程 → `ncu_courses_grad`
6. 學分學程（credit_programs + program_descriptions）→ `ncu_credit_programs`
7. 系所介紹（collego_ncu）→ `ncu_departments`

```
→ 輸出：data/processed/chroma_db/（ChromaDB 持久化目錄）
```

**所需輸入資料一覽（Phase 1 用到的全部）：**
```
data/raw/courses/114_1/*.json
data/raw/courses/114_2/*.json
data/raw/graduate_courses/114_1+2/*.json
data/raw/scraped_missing/courses.json
data/raw/collego_ncu.json
data/raw/114_ulistteacher.csv              ← 教師官方專長
data/processed/nlp/nlp_tech_nodes.json
data/processed/nlp/nlp_simplified_concepts.json
data/processed/nlp/nlp_domain_tags.json
data/processed/nlp/nlp_topic_tags.json
data/processed/nlp/nlp_professor_links.json
data/processed/schedule_draft/[學院]/[系所].json
data/processed/credit_programs/*.json
data/processed/program_descriptions.json
```

---

### Phase 2：後端服務層

```
backend/app/services/
    graph_service.py     ← 新建：載入 .gpickle，提供圖查詢介面
    retriever.py         ← 新建：ChromaDB 向量搜尋（支援 metadata filter）
    llm_service.py       ← 新建：Claude API 呼叫
    intent_classifier.py ← 新建：意圖分類（Regex + few-shot）
backend/app/routes/
    chat.py              ← 新建：POST /api/chat 統一入口
```

**`retriever.py` 關鍵 API：**
```python
search_courses(query, filters=None, n_results=10)
# filters 範例：
#   {"type": "必修", "college": "資訊電機學院"}
#   {"required_year": 1, "required_sem": 1}
#   {"tools": {"$contains": "PyTorch"}}

search_programs(query, n_results=5)
search_departments(query, n_results=3)
```

---

### Phase 3：前端整合

```
frontend/src/pages/CourseSearchPage.tsx    ← 修改：接真實 /api/chat
frontend/src/pages/ProjectsPage.tsx        ← 修改：接真實 /api/chat
```

---

### Phase 4（選做）：圖譜先修邊

`schedule_draft` 中的必修課已有修課順序（`when`），可推算隱含先修。  
NLP tech_nodes 可合併進圖譜成為 Technology/Concept 節點。

```
scripts/graph/enrich_graph_with_nlp.py    ← 新建（依需求）
→ 合併 nlp_tech_nodes → TEACHES/COVERS 邊
→ 合併 schedule_draft when → PREREQUISITE 邊（同系必修順序推算）
→ 更新 data/processed/knowledge_graph.gpickle
```

---

## 七、可回答的問題類型（Phase 1-3 完成後）

| 問題類型 | 使用系統 | 範例 |
|---------|---------|------|
| 課程語意搜尋 | 向量 RAG | 「有什麼和機器學習相關的課？」 |
| 技術找課 | metadata filter | 「哪些課會教 PyTorch？」 |
| 系所必修查詢 | 圖查詢 + schedule_draft | 「資工系大學部有哪些必修？」 |
| 年次規劃 | metadata filter（required_year/sem） | 「大一下有哪些課是必修？」 |
| 學程查詢 | 圖查詢 + 向量 | 「量子技術學程要修哪些課？」 |
| 系所介紹 | ncu_departments 向量 | 「電機系在學什麼，適合什麼人？」 |
| **教師專長查詢** ★ | ncu_teachers 向量 | 「哪位教授專長是機器學習？」 |
| 教師開課查詢 | 圖查詢 | 「XXX 教授教哪些課？」 |
| 跨域查詢 | 圖 + 向量 | 「資工系有哪些課和管理學院相關？」 |
| **先修路徑** ★ | PREREQUISITE 邊（Phase 4） | 「修深度學習前要先修哪些課？」 |

---

## 八、驗證方式

1. **向量索引**：查詢「機器學習」，確認回傳 CE/EE 相關課程
2. **技術過濾**：`tools contains "PyTorch"`，確認只回傳有教 PyTorch 的課
3. **年次過濾**：`required_year=1, required_sem=1`，確認只回傳大一上必修
4. **學程查詢**：問「人工智慧技術應用學程」，確認命中 `ncu_credit_programs`
5. **系所介紹**：問「資工系適合什麼人」，確認命中 `ncu_departments` 且內容來自 collego
6. **圖查詢**：問「資工系大學部必修有哪些」，確認圖查詢回傳正確結構
7. **GraphRAG 融合**：問「AI 相關選修課有哪些」，確認同時命中向量 + 圖

---

## 九、待處理事項

| 項目 | 優先度 | 狀態 |
|------|--------|------|
| 建立 ChromaDB 向量索引（Phase 1） | 🔴 高 | 未開始 |
| 後端 retriever.py（向量搜尋） | 🔴 高 | 未開始 |
| 後端 graph_service.py（圖查詢） | 🔴 高 | 未開始 |
| 後端 intent_classifier.py | 🔴 高 | 未開始 |
| 後端 llm_service.py（Azure OpenAI GPT-4o） | 🔴 高 | 未開始 |
| 後端 chat.py 路由 | 🔴 高 | 未開始 |
| 前端接 chat API | 🟡 中 | 未開始 |
| schedule_draft 人工驗證（when 欄位） | 🟡 中 | 進行中 |
| 圖譜擴充：NLP 技術節點合併（Phase 4） | 🟢 低 | 未開始 |
| 圖譜擴充：PREREQUISITE 邊推算（Phase 4） | 🟢 低 | 未開始 |
