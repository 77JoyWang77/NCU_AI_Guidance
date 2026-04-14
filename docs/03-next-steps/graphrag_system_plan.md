# GraphRAG 問答系統規劃

> 建立時間：2026-04-07
> 前置：知識圖譜三源整合已完成（`data/processed/knowledge_graph.gpickle`）

---

## 一、三個核心問題的決策

### Q1：應修科目表 / 學分學程 — 要掃 PDF 原文，還是用 processed JSON？

**結論：用已處理的 JSON，不需要重掃 PDF。**

| 資料 | 形式 | 用途 |
|------|------|------|
| `data/raw/courses/114_1+2/*.json` | 完整自由文字（課程目標、授課內容） | RAG 主要材料 |
| `data/processed/curriculum_requirements_114.json` | 結構化，已整合進圖 | 圖查詢即可 |
| `data/processed/credit_programs/*.json` | 結構化，已整合進圖 | 圖查詢即可 |

課程 JSON 裡的「課程目標」與「授課內容」是最豐富的自由文字，不需要再解析 PDF。
唯一例外是**修課學期年次**（大一上/大一下…），目前 processed JSON 沒有保存 → 見 Q2。

---

### Q2：要不要提取應修科目表的修課學期年份？

**結論：值得做，分兩步走。**

#### 方案 A（快速）：解析分發條件 → 推算資格年級
- 來源：課程 JSON 的 `分發條件.優先順序列表[].相關條件限制說明`
- 方法：Regex 提取「年級:限X年級」
- 輸出：Course 節點加 `eligible_years: [1, 2, 3, 4]` 屬性
- 限制：只知道誰「有資格修」，不知道課程設計上「建議幾年修」

#### 方案 B（精確）：pdfplumber 提取應修科目表 PDF 表格
- 來源：`data/raw/應修科目表/*.pdf`（表格格式：課程名稱 | 大一上 | 大一下 | 大二上 | …）
- 輸出：REQUIRES 邊加屬性 `suggested_year: 1, suggested_semester: 1`
- 效益：啟用「幫我規劃大一課表」類複雜查詢

建議先做方案 A 快速上線，再排程做方案 B。

---

### Q3：要不要做 NLP 萃取？（有 RTX 4090）

**結論：強烈推薦做，代價低、效益高。**

現有圖譜缺少兩種關鍵語意邊：
1. **PREREQUISITE（先修關係）** — 啟用學習路徑查詢
2. **TEACHES / COVERS（技術/知識節點）** — 啟用「找教 PyTorch 的課」

約 1 小時批次處理，跑一次永久生效。

---

## 二、本地 LLM 模型選型（2026 年最新）

| 推薦 | 模型 | 大小 | VRAM（Q4） | 速度（4090） | 繁中支援 | JSON 輸出 |
|-----|------|------|-----------|------------|---------|---------|
| 🥇 首選 | **GLM-4.7-Flash** | 30B MoE / 3B 激活 | 12-16GB | ~70 tok/s | ★★★★★ | 原生支援 |
| 🥈 次選 | **Qwen3-30B-A3B** | 30B MoE / 3B 激活 | 17GB | ~75 tok/s | ★★★★★ | 原生支援 |
| 🥉 備選 | **Breeze2-8B** | 8B | ~8GB | ~40 tok/s | ★★★★★（台灣） | 部分支援 |

**首選 GLM-4.7-Flash 的理由：**
- 清華 + 智譜出品，繁體中文理解最好，對台灣學術用語熟悉
- 原生函數呼叫 + JSON Schema 輸出，格式輸出零失敗率
- 12-16GB VRAM，4090 非常舒服
- `ollama pull glm4:4.7-flash` 一行啟動

**Breeze2-8B 適合的情境：** VRAM 要留給其他工作，或快速原型測試。MediaTek Research 台灣繁中特化模型，僅需 8GB。

---

## 三、整體架構

```
用戶問題
    │
    ▼
FastAPI 後端
    │
    ├─ 意圖分類（輕量正則 / few-shot）
    │   ├─ 語意類：「計算機概論在講什麼？」 → 向量搜尋
    │   ├─ 結構類：「資工系必修有哪些？」   → 圖查詢
    │   ├─ 路徑類：「線代修完下一步？」     → PREREQUISITE 邊遍歷
    │   └─ 規劃類：「幫我規劃大一選課」    → 圖（年次屬性）+ 向量
    │
    ├─ 向量搜尋（ChromaDB）
    │   └─ 課程目標、授課內容、系所介紹 → embedding
    │
    ├─ 圖查詢（NetworkX，載入 .gpickle）
    │   ├─ 現有：必修/選修結構、學程規定、教師、領域
    │   └─ 新增：PREREQUISITE 邊、Technology/Concept 節點
    │
    └─ Context 融合 → Claude API（claude-sonnet-4-6）→ 回答
```

### 技術選型

| 元件 | 工具 | 理由 |
|------|------|------|
| 向量 DB | **ChromaDB**（開發期） | `pip install chromadb` 零設定，後期可遷移 Qdrant |
| 圖 DB | **NetworkX**（.gpickle） | 已有，不需要 Neo4j |
| Embedding | `text-embedding-3-small`（OpenAI） | 已有 API key |
| LLM（問答） | **Claude API**（claude-sonnet-4-6） | 繁中理解強、API 穩定 |
| LLM（萃取） | **GLM-4.7-Flash**（Ollama 本地） | 繁中最強 + 免費 + 4090 跑 |

> ChromaDB vs Qdrant：開發/Demo 階段用 ChromaDB 完全夠，零依賴不需要開 Docker。生產部署再換 Qdrant，API 幾乎一樣，遷移成本低。

---

## 四、各資料用途

| 資料 | 用途 | 方式 |
|------|------|------|
| `data/raw/courses/114_1+2/*.json` | 向量 RAG 主要材料 + NLP 萃取來源 | embedding → ChromaDB |
| `data/raw/graduate_courses/114_1+2/*.json` | 研究所課程向量索引 | embedding → ChromaDB |
| `data/raw/scraped_missing/courses.json` | 補充課程向量索引 | embedding → ChromaDB |
| `data/raw/collego_ncu.json` | 系所語意介紹 | embedding → ChromaDB |
| `data/processed/knowledge_graph.gpickle` | 結構查詢（必修/選修/學程） | NetworkX 圖遍歷 |
| `data/raw/應修科目表/*.pdf` | 修課建議學期（方案 B） | pdfplumber 提取 |
| 課程 JSON 分發條件 | 修課資格年級（方案 A）、隱含先修 | Regex + LLM |
| 課程 JSON 授課內容 | Technology / Concept 節點萃取 | 本地 LLM |

---

## 五、NLP 萃取詳細設計

### 5.1 先修關係（PREREQUISITE_OF）

**層 1：Regex（不需 GPU，幾秒跑完）**

```python
import re

patterns = [
    r"先修[：:]\s*(.+?)(?:[，,。\n]|$)",
    r"修過(.+?)者優先",
    r"需具備(.+?)基礎",
    r"本課程接續(.+?)",
    r"prerequisite[:\s]+(.+?)(?:[,.\n]|$)",
]

def extract_prereq_regex(text: str) -> list[str]:
    results = []
    for p in patterns:
        matches = re.findall(p, text, re.IGNORECASE)
        results.extend(matches)
    return results
```

預估覆蓋率：約 150–400 筆（明確文字）

**層 2：LLM 萃取（GLM-4.7-Flash，~30 分鐘）**

```python
prompt = """
課程名稱：{course_name}
課程目標與內容：{text}

可選先修課程清單（只能從此清單中選）：
{course_list}

請判斷此課程隱含哪些先修課程，不確定請回答「無」。
輸出 JSON：{{"prerequisites": ["課程名稱1", "課程名稱2"]}}
"""
```

注意：提供課程名稱清單給 LLM，防止幻覺。

### 5.2 技術/知識節點（TEACHES / COVERS）

**LLM 萃取（GLM-4.7-Flash，~30 分鐘）**

```python
prompt = """
從以下課程的授課內容，分類提取技術名詞：

授課內容：{content}

輸出 JSON：
{{
  "languages": [],      // 程式語言，如 Python, C++
  "tools": [],          // 框架/工具，如 PyTorch, Docker
  "concepts": []        // 核心概念，如 資料結構, 微積分
}}
"""
```

輸出邊：
- `Course -[:TEACHES]-> Technology`
- `Course -[:COVERS]-> Concept`

### 5.3 執行規模估算

| 任務 | 課程數 | 每課耗時 | 總時間（4090 + GLM-4.7） |
|------|-------|---------|------------------------|
| Regex 先修 | 3,800 | <1ms | 幾秒 |
| LLM 先修萃取 | 3,800 | ~0.5s | ~30 分鐘 |
| LLM 技術節點萃取 | 3,800 | ~0.5s | ~30 分鐘 |

合計約 **1 小時**，結果存 JSON 後更新 `.gpickle`，之後不需重跑。

---

## 六、建成後可回答的問題類型

| 問題類型 | 使用的系統 | 查詢範例 |
|---------|---------|---------|
| 課程語意搜尋 | 向量 RAG | 「有什麼和機器學習相關的課？」 |
| 系所必修查詢 | 圖查詢 | 「資工系大學部有哪些必修？」 |
| 學程規定查詢 | 圖查詢 | 「量子技術學程要修哪些課？」 |
| **先修路徑查詢** ★ | PREREQUISITE 邊遍歷 | 「修深度學習前要先修哪些課？」 |
| **技術找課** ★ | Technology 節點查詢 | 「有哪些課會教 PyTorch？」 |
| 選課規劃 | 圖（年次屬性）+ 向量 | 「幫我規劃大一的課表」 |
| 系所介紹 | 向量 RAG | 「電機系在學什麼？適合什麼人？」 |
| 教師查詢 | 圖查詢 | 「XXX 教授教哪些課？」 |
| 跨域查詢 | 圖 + 向量 | 「資工系有哪些課和管理學院有關聯？」 |

---

## 七、實作順序與對應檔案

### Phase 1：向量索引（ChromaDB）

```
scripts/rag/build_vector_index.py     （新建）
→ 輸出：data/processed/chroma_db/（ChromaDB 持久化目錄）
→ collection: ncu_courses（~3,800 筆）
→ collection: ncu_departments（~38 筆系所介紹）
```

### Phase 2：NLP 萃取（本地 LLM）

```
scripts/graph/extract_nlp_relations.py    （新建）
→ 輸入：data/raw/courses/ + graduate_courses/ + scraped_missing/
→ 中間產出：data/processed/nlp_relations.json
→ 最終：更新 data/processed/knowledge_graph.gpickle
```

### Phase 3：後端 RAG API

```
backend/app/services/graph_service.py    （新建）載入 .gpickle，提供圖查詢介面
backend/app/services/retriever.py        （新建）ChromaDB 向量搜尋
backend/app/services/llm_service.py      （新建）Claude API 呼叫
backend/app/routes/chat.py               （新建）統一問答入口 POST /api/chat
```

### Phase 4：圖譜年次擴充

```
scripts/graph/enrich_course_eligibility.py    （新建，方案 A）
→ 解析分發條件 Regex → eligible_years 屬性

scripts/graph/extract_curriculum_schedule.py  （新建，方案 B）
→ pdfplumber 提取 PDF 表格 → suggested_year / suggested_semester 屬性
```

### Phase 5：前端整合

```
frontend/src/pages/CourseSearchPage.tsx    （修改）接真實 /api/chat
frontend/src/pages/ProjectsPage.tsx        （修改）接真實 /api/chat
```

---

## 八、驗證方式

1. **向量索引**：查詢「機器學習」，確認回傳 CE/EE 相關課程
2. **圖查詢**：問「資工系大學部必修有哪些？」，確認回答含 CE 開頭課號
3. **先修路徑**：問「修深度學習前要先修什麼？」，確認沿 PREREQUISITE 邊回溯
4. **技術找課**：問「哪些課教 PyTorch？」，確認命中 `TEACHES→Technology{name:PyTorch}` 的課程
5. **GraphRAG 融合**：問「AI 相關的選修課」，確認同時命中語意 + 圖中 OFFERS_ELECTIVE 的課程

---

## 九、待處理事項

| 項目 | 優先度 | 狀態 |
|------|--------|------|
| 建立 ChromaDB 向量索引 | 🔴 高 | 未開始 |
| NLP 先修關係萃取（Regex） | 🔴 高 | 未開始 |
| NLP 技術節點萃取（LLM） | 🔴 高 | 未開始 |
| 後端 graph_service.py | 🔴 高 | 未開始 |
| 後端 retriever.py | 🔴 高 | 未開始 |
| 後端 llm_service.py | 🔴 高 | 未開始 |
| 後端 chat.py 路由 | 🔴 高 | 未開始 |
| 圖譜擴充：分發條件年級（方案 A） | 🟡 中 | 未開始 |
| 圖譜擴充：應修科目表學期（方案 B） | 🟡 中 | 未開始 |
| 前端接 chat API | 🟡 中 | 未開始 |
| 聯網功能 | 🟢 低 | 暫緩 |
