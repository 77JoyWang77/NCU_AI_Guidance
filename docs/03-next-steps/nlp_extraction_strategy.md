# NLP 萃取策略：從課程資料建立先修關係與技術節點

> 建立時間：2026-04-07　　最後更新：2026-04-09
> 基於對 `data/raw/courses/114_1/` 44 個系所 JSON 的實際分析
> 第五節之後為實作版本（已完成腳本），取代原先的多模型設計方案

---

## 一、先看資料的真實情況

### 1.1 各系所欄位填寫率（實測）

| 系所類型 | 代表 | 總數 | 有課程目標 | 有授課內容 | 有備註 | 有核心能力 |
|---------|------|------|---------|---------|------|---------|
| **資電工程** | 資工、電機、通訊 | ~180 | 74–89% | 78–97% | 27–72% | 88–97% |
| **理學院** | 數學、物理、化學 | ~247 | 77–90% | 76–93% | 2–54% | 100% |
| **工學院** | 機械、土木、化工 | ~234 | 75–100% | 87–100% | 38–67% | 92–99% |
| **生醫** | 生科、生醫工 | ~82 | 72–83% | 83–98% | 42–65% | 94–100% |
| **管理** | 企管、資管、財金 | ~237 | 80–95% | 68–95% | 16–63% | 88–100% |
| **文學院** | 中文、英美、法文 | ~181 | 88–100% | 88–100% | 10–56% | 99–100% |
| **通識教育中心** | 通識課 | 81 | 73% | 72% | 32% | 73% |
| **語言中心** | 英日德法文 | 112 | 98% | 89% | 100% | 100% |
| **體育室** | 大一/大二體育 | 199 | 93% | 93% | 99% | 93% |
| **服務學習** | 學務處 | 33 | 88% | 79% | 97% | 91% |
| **軍訓室** | 2門 | 2 | 100% | 100% | 100% | 100% |

**關鍵發現：** 欄位填寫率普遍很高，問題不在「有沒有」，而在「內容是否對萃取有用」。

---

### 1.2 先修關係 Regex 實際命中率（最重要的發現）

在 114_1 全部 ~1,700 門課中，Regex 只命中 **9 筆**（約 0.5%）：

| 命中課程 | 文字 |
|---------|------|
| 語言中心_漢語語法學 | 「建議先修畢語言學概論」 |
| 機械系_機械專題研究 | 「建議先修課程：熱力學、流體力學」 |
| 機械系_機械專題研究(E) | 「建議先修熱力學」 |
| 機械系_製造學 | 「建議先修材料科學、精密機械製造」 |
| 物理系_軟凝體物理 | 「prerequisite to joining the class」 |
| 工學院_普通化學 | 「需具備的化學背景」 |
| 生醫工_物件導向程式設計 | 「建議先修過本門課程」 |
| 地科系_無人機測量 | 「需具備無人機操作經驗」 |
| 企管系_企業政策 | 「需具備整合企業功能…能力」 |

**結論：明確文字標記的先修關係覆蓋率不到 1%，Regex 幾乎不夠用。**

真正的先修資訊藏在：
1. **課號序列命名**（覆蓋率高，規則可靠）
2. **分發條件年級限制**（大量資料，結構化）
3. **授課內容的隱含描述**（需要 LLM 推理）

---

## 二、三種先修資訊的來源與策略

### 2.1 方法一：課號序列命名（規則式，無需模型，覆蓋率最高）

**原理：** 中大課程命名慣例「課名(一)→課名(二)→課名(三)」、「課名Ⅰ→課名Ⅱ」、「課名上→課名下」

**實測命中：** 114_1 中有 133 門課有序列模式

```python
import re, itertools

SEQUENCE_PATTERNS = [
    # 日文(一) → 日文(二)
    (r'(.+?)[（(]([一二三四五六])[)）]', lambda m: (m.group(1), m.group(2))),
    # 計算機概論Ⅰ → 計算機概論Ⅱ
    (r'(.+?)\s*([ⅠⅡⅢⅣⅤⅥⅦⅧ])', lambda m: (m.group(1).strip(), m.group(2))),
    # 微積分上 → 微積分下
    (r'(.+?)\s*([上下])', lambda m: (m.group(1).strip(), m.group(2))),
]

ORDER = {'一': 1, '二': 2, '三': 3, '四': 4, 'Ⅰ': 1, 'Ⅱ': 2, 'Ⅲ': 3, '上': 1, '下': 2}

def find_sequence_prerequisites(course_list):
    """
    從課程清單中找出序列命名的先修關係。
    回傳 [(course_A, course_B, 'PREREQUISITE_OF')] 意為「A 是 B 的先修課」
    """
    groups = {}
    for course in course_list:
        for pattern, extractor in SEQUENCE_PATTERNS:
            m = re.match(pattern, course['name'])
            if m:
                base = extractor(m)
                key = (course['dept'], base[0])
                groups.setdefault(key, []).append((ORDER.get(base[1], 99), course))
    
    edges = []
    for key, items in groups.items():
        items.sort(key=lambda x: x[0])
        for (_, a), (_, b) in zip(items, items[1:]):
            edges.append((a['code'], b['code'], {'type': 'SEQUENCE', 'confidence': 1.0}))
    return edges
```

**效果：**
- 語言中心：日文(一)→日文(二)→日文(三)，幾十條邊，零失誤
- 資工系：計算機概論Ⅰ→Ⅱ、資料結構→演算法（序列推斷）
- 數學系：微積分上→下、線性代數Ⅰ→Ⅱ

---

### 2.2 方法二：分發條件年級推算（規則式，無需模型）

**原理：** 分發條件有「年級:限X年級」，可建立年級層次的先修推斷

```python
import re

YEAR_MAP = {'一': 1, '二': 2, '三': 3, '四': 4}

def parse_eligible_years(condition_text: str) -> list[int]:
    """從分發條件文字提取可修課的年級"""
    # 「年級:限一年級。」→ [1]
    # 「年級:限一、二年級。」→ [1, 2]
    # 無年級限制 → [1, 2, 3, 4]
    
    match = re.search(r'年級[:：]限(.+?)(?:[。\n]|$)', condition_text)
    if not match:
        return [1, 2, 3, 4]
    
    years_text = match.group(1)
    result = []
    for char, year_num in YEAR_MAP.items():
        if char in years_text:
            result.append(year_num)
    return sorted(result) if result else [1, 2, 3, 4]
```

**用途：**
- 為 Course 節點加 `eligible_years` 屬性
- 限一年級的課 → 限二年級的課，暗示可能有先後順序（間接推斷）
- 此資訊對「幫我規劃大一課表」查詢直接有用

---

### 2.3 方法三：LLM 推理（適用於有豐富內容的課程）

**何時使用：** 只對**有意義的課程**做 LLM 推理，其他跳過。

---

## 三、不同系所類型的萃取策略

這是最重要的部分。**不同類型的系所，內容性質完全不同**，要分開處理。

### 類型 A：技術/工程類（完整萃取）

**涵蓋：** 資電學院、工學院、理學院、生醫理工、地科學院

| 萃取任務 | 方法 | 覆蓋率預估 |
|---------|------|---------|
| 序列先修關係 | 規則式 | ★★★★★ |
| 分發條件年級 | 規則式 | ★★★★★ |
| 技術節點（語言/框架/工具） | LLM | ★★★★ |
| 隱含先修關係 | LLM 推理 | ★★★（需驗證）|
| 核心概念節點 | LLM | ★★★★ |

**範例課程資料品質：**
```
資工系「資料結構」（必修，限二年級）：
  目標：訓練學生熟悉陣列、矩陣、堆疊、佇列、串列、樹、圖形，以及排序、搜尋等演算法
  內容：1. 簡介 C 語言 2. Stack 3. Queue 4. Linked list 5. Tree 6. Graph 7. Sorting

→ 技術節點：C 語言
→ 概念節點：資料結構、堆疊、佇列、串列、樹、圖、排序、雜湊
→ 隱含先修：計算機概論（LLM 推理）
```

---

### 類型 B：管理/社科類（部分萃取）

**涵蓋：** 管理學院各系所、文學院

| 萃取任務 | 方法 | 覆蓋率預估 |
|---------|------|---------|
| 序列先修關係 | 規則式 | ★★★ |
| 工具節點（Excel, SPSS, ERP）| LLM/關鍵字 | ★★★ |
| 主題標籤 | LLM | ★★★★ |
| 隱含先修 | LLM（效果有限） | ★★ |

**注意：** 管理類課程有 SQL、Excel、ERP、SPSS 等工具，值得萃取。文學類通常沒有技術工具，主題標籤（如「古典文學」「現代詩」）更有價值。

---

### 類型 C：語言課程（只做序列）

**涵蓋：** 語言中心（英日德法韓文等）

| 萃取任務 | 方法 | 覆蓋率預估 |
|---------|------|---------|
| 序列先修關係 | 規則式 | ★★★★★（最整齊）|
| 語言技能標籤 | 規則式 | ★★★★ |
| 技術節點 | 不做 | N/A |

**範例：** 日文(一)→日文(二)→日文(三)，德文(一)→德文(二)，完整序列鏈，規則式就夠。

---

### 類型 D：通識課（主題分類為主）

**涵蓋：** 通識教育中心、核心通識課程

| 萃取任務 | 方法 | 說明 |
|---------|------|------|
| 先修關係 | **不做** | 通識課設計上無先後關係 |
| 技術節點 | **幾乎不做** | 少數數位通識例外 |
| 主題標籤 | LLM | 哲學/藝術/社會/自然科學等 |
| 備註限修資訊 | 規則式 | 如「限未修過HK2032者」|

---

### 類型 E：體育室（跳過大部分）

**涵蓋：** 體育室所有課程（199 門）

| 萃取任務 | 方法 | 說明 |
|---------|------|------|
| 先修關係 | 規則式 | 大一體育→大二體育（年級序列）|
| 技術節點 | **跳過** | 無任何程式/技術內容 |
| 運動類型標籤 | 備註/規則式 | 游泳/球類/體能等 |

---

### 類型 F：服務學習 / 軍訓室 / TAICA（跳過或最小化）

- 服務學習：只做年級序列，其餘跳過
- 軍訓室：完全跳過 NLP 萃取（只有 2 門課，內容非常固定）
- TAICA（跨校 AI 學程）：只有 10 門，手動處理更快

---

## 四、課程分類器（決定萃取策略的第一步）

在呼叫任何 LLM 之前，先用規則式分類課程，決定要做哪些萃取。

```python
DEPT_SKIP_ALL = {'體育室', '軍訓室'}
DEPT_SEQUENCE_ONLY = {'語言中心', '服務學習發展中心', '職涯發展中心'}
DEPT_TOPICS_ONLY = {'通識教育中心', '核心通識課程'}

# 大學院系 → 完整萃取
DEPT_FULL_EXTRACT = {
    '資訊工程學系', '電機工程學系', '通訊工程學系',
    '機械工程學系', '化學工程與材料工程學系', '土木工程學系',
    '物理學系', '數學系', '化學學系', '光電科學與工程學系',
    '生命科學系', '生醫科學與工程學系',
    # ...
}

def classify_course(course: dict) -> str:
    dept = course.get('系所', '')
    if any(kw in dept for kw in ['體育', '軍訓']):
        return 'SKIP'
    if any(kw in dept for kw in ['語言中心', '服務學習', '職涯']):
        return 'SEQUENCE_ONLY'
    if any(kw in dept for kw in ['通識', '核心通識']):
        return 'TOPICS_ONLY'
    # 工程/理科系所
    if any(kw in dept for kw in ['工程', '理學', '物理', '數學', '化學', '電機', '資訊', '生醫']):
        return 'FULL'
    # 管理/文學
    return 'PARTIAL'
```

---

## 五、模型與設定

**統一使用 Qwen3-14B (Q8_0)**，via Ollama openai-compatible API。

| 項目 | 設定 |
|------|------|
| 模型 | `qwen3:14b`（Q8_0，約 15GB VRAM，4090 可跑） |
| 端點 | `http://localhost:11434/v1` |
| `num_ctx` | **8192**（Ollama 預設 2048 太小，每次 API 呼叫帶入） |
| `temperature` | 0.1（降低隨機性，JSON 輸出更穩定） |

**為什麼統一一個模型：** 4090 切換載入多模型費時，單用 Qwen3-14B Q8_0 全任務通吃，不需切換。

---

## 六、前置處理：教師專長正規化

> **腳本：** `scripts/nlp/normalize_teacher_specialties.py`
> **輸入：** `data/raw/114_ulistteacher.csv`
> **輸出：** `data/processed/dept_professor_map.json`

CSV 的「教師專長」欄位是教授領域資訊的唯一來源（「領域代碼/名稱」欄位全為 `-`）。

**處理邏輯：**
- 用 `[,，、；;/]+` 切割（實測 `/` 也是常見分隔符，59 筆）
- 按「系所名稱」分組，每個系所產生：
  - `specialty_vocab`：所有教授專長的聯集（作為 Agent 2 的可選詞彙表）
  - `professors`：教師列表（含姓名、職級、專長）

**輸出格式：**
```json
{
  "資訊工程學系": {
    "specialty_vocab": ["機器學習", "深度學習", "自然語言處理", ...],
    "professors": [
      {"name": "陳某某", "rank": "教授", "employment": "專任",
       "specialties": ["機器學習", "深度學習"]}
    ]
  }
}
```

**實測結果：** 54 個系所，1009 位教師，2469 個專長詞彙（含跨系所重複）。

---

## 七、三個 Agent 的 Prompt 設計

### 輸入欄位說明

每個 Agent 都使用以下欄位，**除教科書外不截斷**（實測 p99 合計僅 3876 字元，遠低於 8192 token 上限）：

| 欄位 | 截斷規則 | 理由 |
|------|---------|------|
| 課程目標 | 完整送入 | p99 約 650 字元 |
| 授課內容 | 完整送入 | p99 約 1700 字元 |
| 教科書/參考書 | **截斷至 2000 字元** | 有 64K 字元的異常值（整份書目誤貼入） |

---

### Agent 1：技術節點萃取

> **腳本：** `scripts/nlp/run_agent1_tech.py`
> **適用：** 類型 FULL / PARTIAL

```
你是一個課程資訊萃取助手。
請從以下課程資料中，找出技術名詞，分成三類輸出 JSON。

開課系所：{dept}
課程名稱：{course_name}
課程目標：{objective}
授課內容：{content}
教科書/參考書：{books}

輸出格式（只輸出 JSON，不要有其他文字，不要有 markdown）：
{
  "languages": [],   // 程式語言：Python, C++, R, MATLAB, Java...
  "tools": [],       // 框架/工具/軟體：PyTorch, Docker, AutoCAD, SPSS, Excel...
  "concepts": []     // 核心學科概念：資料結構, 傅立葉變換, 微積分, 貝氏統計...
}

- 教科書書名本身不算技術名詞，但書中提到的技術/語言/工具可以算
- 如果某一類沒有，輸出空陣列 []
- 不要包含人名、機構名、課程名
```

**注意：** 教科書欄位對技術萃取特別有用，書名常直接含有 Python、MATLAB 等關鍵字。

**輸出：** `data/processed/nlp_tech_nodes.json`

---

### Agent 2：教授專長領域匹配

> **腳本：** `scripts/nlp/run_agent2_domain.py`
> **適用：** 類型 FULL / PARTIAL（在 Agent 1 之後執行）
> **依賴：** `dept_professor_map.json`（前置處理輸出）、`nlp_tech_nodes.json`（Agent 1 輸出，作為 CoT 線索）

**設計邏輯：**
- 提供該系所教授的研究領域作為**可選詞彙表**，LLM 只能從中選，不能自創新詞
- Agent 1 的輸出（languages/tools/concepts）作為 CoT 線索，幫助 LLM 更有根據地做領域匹配
- LLM 只輸出領域名稱，**教授姓名由後處理反查帶入**（更準確，師資更新時只需重跑後處理）

```
你是一個課程分析助手。
請根據課程資訊，從以下「可選領域詞彙表」中挑選最符合的領域標籤。

開課系所：{dept}
課程名稱：{course_name}
課程目標：{objective}
授課內容（節錄）：{content}
教科書/參考書：{books}
Agent 1 已識別的技術資訊（供參考）：
程式語言：{languages}
使用工具/框架：{tools}
涉及概念：{concepts}

本系所教授的研究領域詞彙表（只能從這裡面選）：
{vocab}

請先思考：這門課用到哪些技術/工具/概念？這些技術屬於哪些學術研究領域？
詞彙表中哪些領域和這些技術最相關？
然後選出 1-5 個最相關的領域，並為每個領域標記關聯強度。

輸出格式（只輸出 JSON）：
{
  "domain_tags": [
    {"field": "領域名稱", "relevance": "high|medium|low"}
  ]
}

- high：這門課的核心內容就是這個領域
- medium：這門課會用到或涉及這個領域
- low：這門課的背景知識需要這個領域
- 不確定時寧可少選；若詞彙表中沒有符合的，輸出 {"domain_tags": []}
```

**後處理（無需 LLM）：** 根據 domain_tags 反查 dept_professor_map，找出各領域對應的教授：
```python
# 輸出：nlp_professor_links.json
{"CS1001": [{"field": "機器學習", "professors": ["陳某某"], "relevance": "high"}]}
```

**輸出：**
- `data/processed/nlp_domain_tags.json`
- `data/processed/nlp_professor_links.json`

---

### Agent 3：通識課程主題分類與核心議題萃取

> **腳本：** `scripts/nlp/run_agent3_topics.py`
> **適用：** 類型 TOPICS_ONLY（通識教育中心、核心通識課程）

通識課不做技術萃取，也不做教授專長匹配（通識教師不一定是研究型）。改為：
1. **主題分類**：歸類到大類標籤
2. **核心議題萃取**：用問句描述這門課想讓學生思考什麼（相當於工程課的 concepts，存為節點屬性）

```
請分析以下通識課程，萃取出主題分類與核心議題。

開課系所：{dept}
課程名稱：{course_name}
課程目標：{objective}
授課內容（節錄）：{content}
教科書/參考書：{books}

可選主題標籤（最多選 3 個）：
人文領域：哲學、歷史、文學、語言學、藝術、音樂
社會領域：社會學、心理學、法律、政治、經濟
自然科學：物理、化學、生物、環境科學、數學
應用科技：資訊科技、工程、醫學
跨域通識：倫理學、性別研究、族群文化、全球化、永續發展

輸出 JSON：
{
  "topic_tags": ["主題標籤1"],
  "core_questions": ["這門課探討的核心問題1", "問題2"]
}

core_questions 用一句問句描述，2-4 個，要具體不要太抽象。
範例：「什麼是幸福？」、「全球化如何影響在地文化認同？」
```

**輸出：** `data/processed/nlp_topic_tags.json`

`core_questions` 不建圖的邊，存為 Course 節點的屬性。

---

## 八、完整 Pipeline

```
前置準備（一次性，幾秒）
└── normalize_teacher_specialties.py → dept_professor_map.json

課程分類（規則式，幾秒）
└── classify_course() → SKIP / SEQUENCE_ONLY / FULL / PARTIAL / TOPICS_ONLY

FULL / PARTIAL 課程：
├── Agent 1（Qwen3-14B Q8_0）：技術節點萃取 → nlp_tech_nodes.json
├── Agent 2（Qwen3-14B Q8_0）：教授專長領域匹配 → nlp_domain_tags.json
└── 後處理（規則式）：教授帶入 → nlp_professor_links.json

TOPICS_ONLY 課程（通識）：
└── Agent 3（Qwen3-14B Q8_0）：主題分類 + 核心議題 → nlp_topic_tags.json

圖譜整合
└── merge_nlp_to_graph.py → 更新 knowledge_graph.gpickle / .json
```

---

## 九、新增圖譜節點與邊

### 新節點類型

| 節點 | 說明 | ID 格式 |
|------|------|---------|
| `Field` | 學術研究領域（來自教師專長，細粒度） | `field::機器學習` |

與現有 `Domain` 節點（課程官方分類，較粗）區分，兩者共存。

### 新邊類型

| 邊 | 方向 | 屬性 | 來源 |
|----|------|------|------|
| `COVERS_FIELD` | Course → Field | `relevance: high/medium/low` | Agent 2 |
| `RELEVANT_EXPERT` | Instructor → Field | `dept` | 後處理（規則式） |
| `TAGGED_AS` | Course → Domain | `source: llm_agent3` | Agent 3 |

**查詢路徑範例：** 學生對某領域有興趣時：
```
Course → COVERS_FIELD → Field → RELEVANT_EXPERT → Instructor
（課程）              （領域）                   （可詢問的教授）
```

### 中間產出檔案

```
data/processed/
├── dept_professor_map.json       # 系所 → 教授專長詞彙表（前置處理）
├── nlp_tech_nodes.json           # Agent 1：技術節點（languages/tools/concepts）
├── nlp_domain_tags.json          # Agent 2：領域標籤（domain_tags + relevance）
├── nlp_professor_links.json      # 後處理：領域對應教授（反查）
└── nlp_topic_tags.json           # Agent 3：通識主題標籤 + core_questions
```

每步驟結果存 JSON，支援斷點恢復（重跑腳本會跳過已完成項目）。

---

## 十、腳本對應

| 腳本 | 功能 | 狀態 |
|------|------|------|
| `scripts/nlp/normalize_teacher_specialties.py` | 前置：教師專長正規化 | ✅ 已完成 |
| `scripts/nlp/run_agent1_tech.py` | Agent 1：技術節點萃取 | ✅ 已完成 |
| `scripts/nlp/run_agent2_domain.py` | Agent 2：教授專長領域匹配 | ✅ 已完成 |
| `scripts/nlp/run_agent3_topics.py` | Agent 3：通識主題分類 | ✅ 已完成 |
| `scripts/graph/merge_nlp_to_graph.py` | 整合所有 JSON 進圖譜 | ✅ 已完成 |
| `scripts/graph/build_knowledge_graph.py` | 基礎建圖（不修改） | ✅ 現有 |
