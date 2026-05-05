# NLP 萃取 Pipeline

> 模型：Qwen3-14B-AWQ via vLLM（`http://localhost:8000/v1`）  
> 資料來源：`data/raw/courses/114_1/`（44 個系所 JSON，~1,700 門課）  
> 完成時間：2026-04-13  
> 詳細執行紀錄：另見 `nlp_extraction_report.md`

---

## 一、目的

課程 JSON 原始資料僅含課程目標、授課內容等自然語言文字，無法直接進行精確的語意查詢（例如「哪些課教 Python？」「哪些課涵蓋梯度下降？」）。本 Pipeline 使用本地 LLM 從課程文字萃取**結構化語意節點**，供知識圖譜建構與向量索引使用。

---

## 二、課程分類器（策略分流）

在呼叫任何 LLM 之前，先以**規則式分類器**決定每門課需要哪些萃取步驟，避免對不相關課程浪費算力。

| 分類 | 條件 | 萃取步驟 |
|------|------|---------|
| `SKIP` | 體育、軍訓、已停開、三欄全空 | 不做任何萃取 |
| `SEQUENCE_ONLY` | 語言中心、服務學習、職涯中心 | 只做序列先修（規則式） |
| `TOPICS_ONLY` | 通識教育中心、核心通識 | Agent 3 主題分類 |
| `FULL` | 其餘（工程、理科、管理、文學等） | Agent 1 + Agent 2 + Agent 4 |

```python
DEPT_SKIP_ALL      = {'體育室', '軍訓室'}
DEPT_SEQUENCE_ONLY = {'語言中心', '服務學習發展中心', '職涯發展中心'}
DEPT_TOPICS_ONLY   = {'通識教育中心', '核心通識課程'}

def classify_course(course: dict) -> str:
    dept = course.get('系所', '')
    if any(kw in dept for kw in ['體育', '軍訓']):
        return 'SKIP'
    if any(kw in dept for kw in ['語言中心', '服務學習', '職涯']):
        return 'SEQUENCE_ONLY'
    if any(kw in dept for kw in ['通識', '核心通識']):
        return 'TOPICS_ONLY'
    return 'FULL'
```

---

## 三、Pipeline 執行順序

```
normalize_teacher_specialties.py
  └→ dept_professor_map.json（300 KB，前置依賴）

run_agent1_tech.py
  └→ nlp_tech_nodes.json（857 KB）
       ├─ fix_tech_nodes.py（後處理：英文概念翻繁中）
       └→（依賴此檔）run_agent2_domain.py
            ├→ nlp_domain_tags.json（1.1 MB）
            └→ nlp_professor_links.json（1.4 MB）

run_agent3_topics.py（無依賴，獨立執行）
  └→ nlp_topic_tags.json（38 KB）

run_agent4_simplify.py（依賴 nlp_tech_nodes.json）
  └→ nlp_simplified_concepts.json（2.6 MB）
       └─ postprocess_simplified.py（後處理：去標籤、繁體化）
```

---

## 四、各 Agent 詳細說明

### Agent 1：技術節點萃取（run_agent1_tech.py）

**適用**：`FULL` 類課程

**輸入**：課程目標 + 授課內容 + 教科書

**萃取項目**：
- `languages`：程式語言（Python, C++, Java, R...）
- `tools`：框架/工具（PyTorch, TensorFlow, GDB, Makefile...）
- `concepts`：核心學術概念（梯度下降、記憶體管理、資料結構...）

**輸出格式**（`nlp_tech_nodes.json`）：
```json
{
  "CS1001": {
    "languages": ["C", "Python"],
    "tools": ["GDB", "Makefile"],
    "concepts": ["系統程式設計", "記憶體管理", "行程排程"]
  }
}
```

**後處理**（`fix_tech_nodes.py`）：
- 將英文概念名稱翻為繁體中文
- NFKC Unicode 正規化

**規模**：857 KB，涵蓋 ~1,200 門 FULL 類課程

---

### Agent 2：領域標籤 + 教授關聯（run_agent2_domain.py）

**適用**：`FULL` 類課程

**輸入**：
- 課程資訊（目標、內容、技術節點）
- 該系所教授研究領域詞彙表（from `dept_professor_map.json`）

**萃取項目**：
- **課程→領域標籤**（含 relevance 等級 high/medium/low，1-15 個）
- **課程→相關教授**（規則反查：領域詞彙 ∩ 教授專長）

**輸出格式**：

`nlp_domain_tags.json`（1.1 MB）：
```json
{
  "CS1001": {
    "domain_tags": [
      {"field": "系統程式設計", "relevance": "high"},
      {"field": "作業系統", "relevance": "medium"}
    ]
  }
}
```

`nlp_professor_links.json`（1.4 MB）：
```json
{
  "CS1001": [
    {"field": "系統程式設計", "professors": ["王○○", "李○○"], "relevance": "high"}
  ]
}
```

---

### Agent 3：通識課主題分類（run_agent3_topics.py）

**適用**：`TOPICS_ONLY`（通識教育中心、核心通識）

**萃取項目**：
- `topic_tags`：主題標籤（哲學、歷史、文學、語言學、藝術、社會學、心理學、法律、政治、經濟、物理、化學、生物、環境科學、數學、資訊科技、工程、醫學、倫理學、性別研究、族群文化、全球化、永續發展、宗教）
- `core_questions`：2-4 個核心議題問句

**輸出格式**（`nlp_topic_tags.json`，38 KB）：
```json
{
  "GE1001": {
    "topic_tags": ["哲學", "倫理學"],
    "core_questions": ["什麼是幸福？", "道德判斷有客觀標準嗎？"]
  }
}
```

---

### Agent 4：概念高中生友善化（run_agent4_simplify.py）

**適用**：依賴 `nlp_tech_nodes.json`（FULL 類課程的 concepts）

**目標**：將專業概念轉換為高中生能理解的說法，並連結高中科目

**萃取項目**：
- `display`：高中生友善版說明
- `high_school_subject`：對應高中科目（選填）

**輸出格式**（`nlp_simplified_concepts.json`，2.6 MB）：
```json
{
  "CS3001": {
    "college": "eecs",
    "simplified_concepts": [
      {"original": "梯度下降", "display": "最佳化方法"},
      {"original": "反向傳播", "display": "類神經網路的學習機制"}
    ]
  }
}
```

**後處理**（`postprocess_simplified.py`）：去除 Markdown 標籤、繁體化

---

## 五、先修關係萃取策略

### 5.1 關鍵發現

在 114_1 全部 ~1,700 門課中，Regex 明確文字標記只命中 **9 筆**（< 0.5%）：

| 命中課程 | 文字 |
|---------|------|
| 語言中心_漢語語法學 | 「建議先修畢語言學概論」 |
| 機械系_機械專題研究 | 「建議先修課程：熱力學、流體力學」 |
| 物理系_軟凝體物理 | 「prerequisite to joining the class」 |

**結論**：明確先修標記不到 1%，三種方法搭配才能達到有效覆蓋。

### 5.2 方法一：課號序列命名（規則式，覆蓋率最高）

中大課程命名慣例「課名(一)→課名(二)→課名(三)」、「課名I→課名II」、「課名上→課名下」。

```python
SEQUENCE_PATTERNS = [
    (r'(.+?)[（(]([一二三四五六])[)）]', ...),   # 日文(一) → 日文(二)
    (r'(.+?)\s*([ⅠⅡⅢⅣⅤⅥ])', ...),             # 計算機概論I → II
    (r'(.+?)\s*([上下])', ...),                    # 微積分上 → 微積分下
]
```

**實測命中**：114_1 中有 **133 門課**有序列模式，置信度 1.0。

範例：
- 語言中心：日文(一)→日文(二)→日文(三)（零失誤）
- 數學系：微積分上→微積分下、線性代數I→II

### 5.3 方法二：分發條件年級推算（規則式）

```python
def parse_eligible_years(condition_text: str) -> list[int]:
    # 「年級:限一、二年級。」→ [1, 2]
    match = re.search(r'年級[:：]限(.+?)(?:[。\n]|$)', condition_text)
```

- 為 Course 節點加 `eligible_years` 屬性
- 對「幫我規劃大一課表」查詢直接有用

### 5.4 方法三：LLM 推理（適用於有豐富授課內容的課程）

僅對有意義的 FULL 類課程做 LLM 隱含先修推理，覆蓋授課內容中的暗示（如「本課程假設學生已熟悉資料結構」）。

---

## 六、各系所萃取策略分類

不同類型系所，內容性質不同，萃取任務也要分開：

| 類型 | 系所 | 萃取任務 |
|------|------|---------|
| **A 技術/工程** | 資電學院、工學院、理學院、生醫理工、地科 | 序列先修 + 年級 + 技術節點 + 概念 + 領域 + 簡化 |
| **B 管理/社科** | 管理學院、文學院 | 序列先修 + 工具節點（Excel/SPSS/ERP）+ 主題標籤 |
| **C 語言課程** | 語言中心 | 規則式序列命名（最整齊） |
| **D 通識課** | 通識教育中心 | 主題標籤 + 核心議題問句 |
| **E 體育** | 體育室（199 門） | 規則式年級序列，跳過技術節點 |
| **F 行政類** | 服務學習、軍訓室 | 完全跳過或最小化 |

---

## 七、各系所欄位填寫率（實測 114_1）

| 系所類型 | 代表 | 有課程目標 | 有授課內容 | 有核心能力 |
|---------|------|---------|---------|---------|
| **資電工程** | 資工、電機、通訊 | 74-89% | 78-97% | 88-97% |
| **理學院** | 數學、物理、化學 | 77-90% | 76-93% | 100% |
| **工學院** | 機械、土木、化工 | 75-100% | 87-100% | 92-99% |
| **生醫** | 生科、生醫工 | 72-83% | 83-98% | 94-100% |
| **管理** | 企管、資管、財金 | 80-95% | 68-95% | 88-100% |
| **文學院** | 中文、英美、法文 | 88-100% | 88-100% | 99-100% |
| **通識** | 通識教育中心 | 73% | 72% | 73% |
| **語言中心** | 英日德法文 | 98% | 89% | 100% |

**關鍵發現**：欄位填寫率普遍很高，問題不在「有沒有」，而在「內容是否對萃取有用」。

---

## 八、輸出規模摘要

| 輸出檔案 | 大小 | 說明 |
|---------|------|------|
| `dept_professor_map.json` | 300 KB | 54 系所，1,009 位教師，2,469 個專長 |
| `nlp_tech_nodes.json` | 857 KB | 技術節點（languages/tools/concepts） |
| `nlp_domain_tags.json` | 1.1 MB | 課程→研究領域標籤 |
| `nlp_professor_links.json` | 1.4 MB | 課程→相關教授（規則反查） |
| `nlp_topic_tags.json` | 38 KB | 通識課主題標籤 + 核心議題問句 |
| `nlp_simplified_concepts.json` | 2.6 MB | 概念高中生友善化 |
| **合計** | **~6.3 MB** | 全部位於 `data/processed/nlp/` |

---

## 九、後續整合

NLP 萃取結果在兩個地方被消費：

1. **知識圖譜 Phase 2 豐富化**（`scripts/graph/build_graph.py`）
   - `nlp_tech_nodes` → Technology/Concept 節點 + TEACHES/COVERS 邊
   - `nlp_domain_tags` → Field 節點 + COVERS_FIELD 邊
   - `nlp_professor_links` → COURSE_EXPERT 邊
   - `dept_professor_map` → RELEVANT_EXPERT 邊

2. **Qdrant 向量索引**（`scripts/rag/build_vector_index.py`）
   - 整合進課程文件文字（提升語意搜尋品質）
   - 儲存為 payload 欄位（供 Qdrant 過濾器使用）
