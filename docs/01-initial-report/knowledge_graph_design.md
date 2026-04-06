# 課程知識圖譜設計文件

## 一、現有資料分析

### 1.1 目前擁有的資料

每門課程包含以下欄位：

| 欄位 | 內容範例 | 圖譜用途 |
|------|---------|---------|
| 學院 | 資訊電機學院 | 節點 |
| 系所 | 資訊工程學系 | 節點 |
| 課號-班別 | CE1001-* | 節點 ID |
| 課程名稱(中/英) | 計算機概論 Ⅰ | 節點屬性 |
| 授課教師 | 施國琛 | 節點 |
| 學分 | 3 | 節點屬性 |
| 上課時間 | Thu567 | 節點屬性 |
| 選修別 | 必修 | 節點屬性 |
| 分發條件 | 限資工系一年級 | 關係（限制） |
| 課程目標 | 文字描述 | NLP 萃取用 |
| **授課內容** | 詳細週次說明 | **NLP 萃取技術/知識節點** |
| **課程領域** | 人工智慧、資料科學... | **直接建立領域節點** |
| **核心能力** | 數理邏輯能力 (5)高 | **直接建立能力節點** |
| 評量方式 | 期中 25% + 作業 50% | 節點屬性 |
| 授課方式 | 講授 研討 實習/實驗 | 節點屬性 |
| 教科書 | 書名與版本 | NLP 萃取知識來源 |

資料量：**3316 門課程**，涵蓋 **2 個學期**（114_1, 114_2），**45 個系所**，**10 個學院**

---

## 二、可以直接建立的知識圖譜

> 「直接建立」= 不需要 NLP，從結構化欄位直接對應

### 2.1 節點類型（Nodes）

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   [學院]──────[系所]──────[課程]──────[教師]                    │
│                               │                                 │
│                         ┌─────┼─────┐                          │
│                         ▼     ▼     ▼                          │
│                       [能力][領域][授課方式]                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

| 節點 | 來源欄位 | 預估數量 | 信心度 |
|------|---------|---------|-------|
| `Course` | 課號-班別 | ~3316 | ⭐⭐⭐⭐⭐ |
| `College` | 學院 | ~10 | ⭐⭐⭐⭐⭐ |
| `Department` | 系所 | ~45 | ⭐⭐⭐⭐⭐ |
| `Instructor` | 授課教師 | ~數百 | ⭐⭐⭐⭐⭐ |
| `Competency` | 核心能力.能力名稱 | ~數十 | ⭐⭐⭐⭐⭐ |
| `Domain` | 課程領域 | ~數十 | ⭐⭐⭐⭐⭐ |
| `TeachingMethod` | 授課方式 | ~10 | ⭐⭐⭐⭐⭐ |

### 2.2 關係類型（Edges）— 直接可建立

```cypher
// 範例：Neo4j Cypher 語法

// 課程 → 學院
(Course)-[:BELONGS_TO]->(College)

// 課程 → 系所
(Course)-[:OFFERED_BY]->(Department)

// 系所 → 學院
(Department)-[:PART_OF]->(College)

// 課程 → 教師
(Course)-[:TAUGHT_BY]->(Instructor)

// 課程 → 核心能力（帶強度屬性）
(Course)-[:DEVELOPS {intensity: 5, method: "紙筆測驗"}]->(Competency)

// 課程 → 課程領域
(Course)-[:IN_DOMAIN]->(Domain)

// 課程 → 授課方式
(Course)-[:USES_METHOD]->(TeachingMethod)

// 課程限修：分發條件
(Course)-[:RESTRICTED_TO {priority: 1}]->(Department)

// 同教師教的課程（透過 Instructor 節點連接）
(Course)-[:TAUGHT_BY]->(Instructor)<-[:TAUGHT_BY]-(Course2)

// 同系必修課程
(Course)-[:REQUIRED_IN]->(Department)
```

### 2.3 跨學期關係

因為有兩個學期的資料，可以建立：

```cypher
// 同課號、不同學期的版本關係
(Course_114_1)-[:NEXT_SEMESTER]->(Course_114_2)

// 同系列課程（例如計算機概論Ⅰ → 計算機概論Ⅱ）
// 從課號推斷：CE1001 → CE1002
(Course)-[:SERIES_NEXT]->(Course)
```

---

## 三、需要 NLP 萃取的關係

> 資料裡有但需要解析，信心度較低

### 3.1 先修關係（最重要、最難）

**問題**：目前資料沒有結構化的先修欄位，先修資訊散落在：
- `備註` 欄位（如「先修：線性代數」）
- `分發條件` 中的年級限制（一年級 → 二年級暗示順序）
- `授課內容` 中的文字描述

**NLP 方法**：
```python
# 從備註中正則表達式匹配
patterns = [
    r"先修[：:]\s*(.+?)(?:[，,。]|$)",
    r"修過(.+?)者優先",
    r"需具備(.+?)基礎",
    r"prerequisite[:\s]+(.+?)(?:[,.]|$)",
]

# 從課程內容語意匹配
# 「本課程接續計算機概論Ⅰ」→ 推斷先修關係
```

**信心度**：⭐⭐⭐（需要人工驗證）

### 3.2 技術/知識節點萃取

從**授課內容**（最詳細的欄位）萃取：

```
計算機概論 I 授課內容包含：
├── 程式語言：Python、C++、Java
├── 概念：資料結構、演算法、作業系統
├── 工具：無
└── 主題：人工智慧、資安、資料壓縮
```

**NLP 方法**：
- Named Entity Recognition（命名實體識別）
- 技術詞彙字典比對
- LLM 萃取（最精準）

```cypher
// 建立後可查詢
(Course)-[:TEACHES]->(Technology {name: "Python"})
(Course)-[:COVERS]->(Concept {name: "資料結構"})
```

**信心度**：⭐⭐⭐⭐（LLM 萃取準確率高）

### 3.3 課程相似度關係

```cypher
// 從 Embedding 相似度計算
(Course)-[:SIMILAR_TO {score: 0.85}]->(Course2)

// 從核心能力重疊計算
(Course)-[:RELATED_BY_COMPETENCY]->(Course2)
```

**信心度**：⭐⭐⭐⭐⭐（向量計算，確定性高）

---

## 四、現有資料的限制（缺失的重要資訊）

### 4.1 高優先缺失項目

| 缺失資訊 | 影響 | 取得方式 | 難度 |
|---------|------|---------|------|
| **明確先修課程** | 無法建立學習路徑圖 | 爬取各系課程規劃表 | 🔴 高 |
| **畢業學分規定** | 無法規劃完整修課路徑 | 爬取各系必選修規定 | 🔴 高 |
| **課程難度/評價** | 無法推薦容易/適合的課 | 需要學生回饋資料 | 🔴 高 |
| **學程/Certificate 清單** | 無法建立學程節點 | 爬取學程說明頁面 | 🟡 中 |
| **歷年開課紀錄** | 只有2學期，無法分析趨勢 | 爬取歷史學期資料 | 🟡 中 |
| **實際選課人數** | 只有上限，看不出熱門程度 | 選課期間截圖/爬取 | 🟡 中 |

### 4.2 次要缺失項目

| 缺失資訊 | 影響 | 取得方式 |
|---------|------|---------|
| 教師基本資料（系所、研究領域） | 教師節點資訊不足 | 爬取教師個人頁面 |
| 課程開放外系/外院比例 | 跨域關係不完整 | 現有分發條件可部分推斷 |
| 課程地圖（官方版） | 先修關係需自行推斷 | 各系課程規劃 PDF |
| 職涯關聯資料 | 無法做就業方向推薦 | 外部資料集 |
| PTT/Dcard 課程評價 | 口碑評分 | 爬蟲（合法性需確認）|

---

## 五、知識圖譜完整架構

```
                          ┌────────────────┐
                          │    University   │
                          └───────┬────────┘
                                  │ HAS
                         ┌────────┴────────┐
                         ▼                 ▼
                    ┌─────────┐      ┌──────────┐
                    │ College  │      │  Center  │
                    └────┬────┘      └──────────┘
                         │ CONTAINS
                    ┌────▼────────┐
                    │ Department  │
                    └────┬────────┘
                         │ OFFERS
              ┌──────────┴──────────────────┐
              ▼                             ▼
        ┌──────────┐                ┌──────────────┐
        │  Course  │                │   Program     │  ← 缺失
        └────┬─────┘                │  (學程/學士班) │
             │                     └──────────────┘
    ┌────────┼──────────────────────────┐
    ▼        ▼        ▼         ▼       ▼
┌──────┐ ┌──────┐ ┌───────┐ ┌─────┐ ┌────────┐
│Instr.│ │Domain│ │Compet.│ │Tech │ │Prereq. │
│(教師)│ │(領域)│ │(能力) │ │(技術│ │(先修)  │
└──────┘ └──────┘ └───────┘ └─────┘ └────────┘
                                 ↑         ↑
                              NLP萃取    需補充
```

---

## 六、可以立刻回答的查詢（現有資料）

### 高中生常見問題 → 圖譜查詢

```cypher
// Q: 資工系大一必修有哪些？
MATCH (c:Course)-[:OFFERED_BY]->(d:Department {name: "資訊工程學系"})
WHERE c.required = "必修" AND c.grade = "一年級"
RETURN c.name, c.credits, c.instructor

// Q: 哪些課會培養「數理邏輯能力」?
MATCH (c:Course)-[r:DEVELOPS]->(comp:Competency {name: "數理邏輯能力"})
WHERE r.intensity >= 4
RETURN c.name, c.department, r.intensity ORDER BY r.intensity DESC

// Q: 施國琛老師開哪些課？
MATCH (c:Course)-[:TAUGHT_BY]->(i:Instructor {name: "施國琛"})
RETURN c.name, c.semester, c.credits

// Q: AI 相關課程有哪些？
MATCH (c:Course)-[:IN_DOMAIN]->(d:Domain)
WHERE d.name CONTAINS "人工智慧"
RETURN c.name, c.department, c.credits

// Q: 資工系和電機系有哪些共同課程？
MATCH (c:Course)-[:OFFERED_BY]->(d1:Department {name: "資訊工程學系"}),
      (c)-[:RESTRICTED_TO]->(d2:Department {name: "電機工程學系"})
RETURN c.name

// Q: 哪個系的課最注重「團隊合作」？
MATCH (dept:Department)<-[:OFFERED_BY]-(c:Course)
      -[r:DEVELOPS]->(comp:Competency {name: "溝通協調與團隊合作能力"})
RETURN dept.name, AVG(r.intensity) as avg_intensity
ORDER BY avg_intensity DESC

// Q: 不同系所開的 Python 相關課程？
MATCH (c:Course)-[:TEACHES]->(tech:Technology {name: "Python"})
MATCH (c)-[:OFFERED_BY]->(d:Department)
RETURN d.name, collect(c.name)
```

### 目前無法回答（缺資料）

```cypher
// Q: 要修哪些課才能畢業？← 缺畢業要求資料
// Q: 這門課的先修是什麼？← 缺結構化先修資料
// Q: 這門課好不好修？← 缺學生評價
// Q: 雙主修需要上哪些課？← 缺學程要求
```

---

## 七、建議的資料補充策略

### 7.1 立刻可做（爬蟲）

```
目標網頁：
├── 各系課程規劃表（必/選修結構）
│   URL: https://www.ncu.edu.tw/[dept]/curriculum
├── 教師個人頁面（研究領域）
│   URL: https://cis.ncu.edu.tw/...
├── 學程說明頁面
│   URL: 各學程官網
└── 歷史學期課程（112, 113 學年）
    URL: 修改 semester 參數即可
```

### 7.2 爬蟲優先順序

```
優先度 1（最高）:
  ✦ 各系必選修學分結構（畢業要求）
  ✦ 先修課程對照表（如果有公開）

優先度 2:
  ✦ 教師研究領域
  ✦ 學程（Program）課程清單
  ✦ 歷年課程資料（趨勢分析）

優先度 3:
  ✦ 課程評價（PTT 批踢踢、Dcard）← 注意法律問題
  ✦ 就業統計資料
```

### 7.3 可以用 LLM 自動補充的

```python
# 從現有授課內容萃取先修資訊
prompt = """
分析以下課程說明，找出提到的先修課程或需要的背景知識：

課程名稱：{course_name}
授課內容：{course_content}
備註：{notes}

請以 JSON 格式回傳：
{{
  "prerequisites_mentioned": ["課程名稱1", "課程名稱2"],
  "required_knowledge": ["知識1", "知識2"],
  "confidence": 0.0-1.0
}}
"""

# 從授課內容萃取技術標籤
prompt = """
從以下課程內容中，萃取所有技術、程式語言、工具、概念：

{course_content}

回傳 JSON：
{{
  "programming_languages": [],
  "tools": [],
  "concepts": [],
  "algorithms": []
}}
"""
```

---

## 八、實作計畫

### Phase 1：現有資料建圖（可立刻開始）

```
Week 1:
├── 建立 Neo4j / NetworkX 圖資料庫
├── 載入 College, Department, Course 節點
├── 建立 BELONGS_TO, OFFERED_BY, TAUGHT_BY 關係
└── 建立 Competency, Domain 節點和關係

Week 2:
├── 從分發條件萃取選課限制關係
├── 從課號識別課程系列（I → II → III）
├── 跨學期課程版本關係
└── 課程相似度計算（Embedding）
```

### Phase 2：NLP 萃取（需要 LLM）

```
Week 3-4:
├── 用 LLM 萃取技術/知識標籤
├── 從備註萃取先修資訊
├── 建立 Technology, Concept 節點
└── 人工抽樣驗證準確率
```

### Phase 3：資料補充（爬蟲）

```
Week 5-6:
├── 爬取各系課程規劃表
├── 爬取歷年學期資料
├── 整合教師資料
└── 建立完整先修關係
```

### Phase 4：與 RAG 整合

```
Week 7-8:
├── 圖增強型 RAG（Graph RAG）
├── 路徑查詢（學習路徑推薦）
├── 子圖萃取（相關課程推薦）
└── 測試與調整
```

---

## 九、技術選型

### 圖資料庫選擇

| 選項 | 特點 | 推薦場景 | 費用 |
|------|------|---------|------|
| **Neo4j** | 成熟、Cypher 語法、視覺化好 | 生產環境 | 免費（社群版） |
| **NetworkX** | Python 原生、輕量 | 快速驗證/開發 | 免費 |
| **ArangoDB** | 多模型（圖+文件） | 需要複雜查詢 | 免費 |
| **Kuzu** | 嵌入式、超快、DuckDB 風格 | 輕量生產 | 免費 |

**建議**：開發先用 NetworkX，確認圖結構後轉 Neo4j

### Graph RAG 框架

```python
# 選項 1: LlamaIndex + PropertyGraphIndex
from llama_index.core import PropertyGraphIndex

# 選項 2: LangChain + Neo4j
from langchain_community.graphs import Neo4jGraph
from langchain.chains import GraphCypherQAChain

# 選項 3: Microsoft GraphRAG（開源）
# 適合大規模文件知識圖譜
```

---

## 十、總結評估

### 現有資料能建出的圖譜品質

```
節點完整度：████████░░  80%
關係完整度：█████░░░░░  50%
先修鏈完整度：██░░░░░░░░  20%  ← 最大缺口
語意豐富度：███████░░░  70%（授課內容很詳細）
```

### 結論

**可行性**：✅ 高度可行

目前資料已足夠建立一個**有用的基礎知識圖譜**，核心能力和課程領域這兩個欄位特別有價值，直接提供了結構化的語意關係。

**最值得補充的一件事**：各系課程規劃表（畢業要求），這能讓圖譜從「課程索引」升級為真正的「學習路徑地圖」。

**如果資源有限**，建議：
1. 先用現有資料建基礎圖
2. 用 LLM 萃取技術標籤和推斷先修
3. 集中爬取 2-3 個重點系所的完整課程規劃作為 demo
