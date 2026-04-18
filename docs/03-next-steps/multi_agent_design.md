# Multi-Agent 架構設計（基於實際資料）

> 建立時間：2026-04-18  
> 前置文件：`docs/01-initial-report/graphrag_integration.md`、`agent_architecture.md`

---

## 一、為什麼現有單一管道不夠用

### 1.1 現況的根本限制

現有架構每次只觸發**一個意圖**，任何複合問題都會失敗：

```
問：「資工系大一必修中，哪些課和機器學習有關？」

現況做的事：
  Intent → dept_required（只取到必修列表）
         OR schedule（只取到大一課程）
  → 兩個條件只能滿足一個，答案不完整

正確做法：
  Step 1: get_dept_required_courses("資工系")  → [CE1001, MA1003, ...]
  Step 2: search_courses("機器學習", codes=上述清單)  → 交集
  Step 3: 合併回答
```

```
問：「我是資工系大二，線代修完後下一步應該修什麼？」

現況做的事：
  Intent → semantic（只找「像線代」的課）
  → 沒有先修關係推理，沒有年級過濾

正確做法：
  Step 1: get_courses_by_code("MA1007")  → 確認是線性代數
  Step 2: search_courses(prereq="MA1007")  → 以線代為先修的課
  Step 3: search_courses(filters={year≥2, dept="資工系"})  → 大二以上限縮
  Step 4: 合併推薦
```

### 1.2 現有資料的多跳潛力（尚未開發）

| 資料 | 現在用到的 | 實際可支援的查詢 |
|-----|----------|---------------|
| `prereq_codes` | 單純顯示課號 | 先修鏈展開、路徑推理 |
| `when_semesters` | 過濾單一學期 | 整學年規劃、課表排列 |
| `eligible_years` | 過濾修課年級 | 「我是大X可以修哪些課？」 |
| `nlp_professor_links` | 未使用 | 「這門課涉及哪個教授的研究方向？」 |
| `domain_tags` + `dept` | 各自獨立 | 跨域推薦：「資工系有哪些金融科技相關課？」 |
| `graduation_rules` | 有函式但未串接 | 「我還差幾學分畢業？」（需加入對話記憶）|

---

## 二、架構設計：ReAct Tool-Use Agent

### 2.1 為何選 ReAct Tool-Use（而非多個獨立 Agent）

| 方案 | 優點 | 缺點 | 適合場景 |
|-----|-----|-----|---------|
| 現有單管道 | 快、便宜 | 只能單意圖 | 簡單問題 |
| ReAct Tool-Use | 多步推理、彈性高、現有函式直接複用 | 多 1-2 次 LLM round-trip | **本專題最適合** |
| 多個獨立 Sub-Agent | 最靈活 | 架構複雜、延遲倍增、成本高 | 大型系統 |

選 ReAct 的理由：
- 現有 `graph_service.py` 和 `retriever.py` 的函式直接對應成工具，幾乎不需要重寫
- 對話輪數通常只需要 2-3 次工具呼叫，延遲增加有限（+300-600ms）
- GPT-4o 的 function calling 可以並行執行獨立工具

### 2.2 整體架構

```
使用者提問（含對話歷史）
          │
          ▼
┌─────────────────────────────────────────────────────────┐
│  ChatAgent（ReAct + Function Calling）                  │
│                                                         │
│  System Prompt：角色定義 + 工具使用指引                  │
│  Message History：對話記憶（最近 6 輪）                  │
│                                                         │
│  思考：這個問題需要哪些工具？可以並行哪些？               │
│  ↓                                                      │
│  tool_call: [tool1, tool2, ...]  ← 可並行               │
│  ↓                                                      │
│  收到工具結果，判斷是否需要繼續呼叫                       │
│  ↓                                                      │
│  生成最終回答                                            │
└─────────────────────────────────────────────────────────┘
          │
          ▼
    {answer, tools_used, sources}
```

### 2.3 工具清單（基於現有函式設計）

#### 工具 1：search_courses — 語意/條件搜尋課程

```python
def search_courses(
    query: str,              # 搜尋關鍵詞或自然語言描述
    dept: str = None,        # 限縮系所（如 "資訊工程學系"）
    college: str = None,     # 限縮學院
    course_type: str = None, # "必修" / "選修"
    year: int = None,        # 建議修習年級（1-4）
    sem: int = None,         # 學期（1=上, 2=下）
    tech: str = None,        # 技術/工具（如 "PyTorch"）
    is_grad: bool = False,   # 是否搜尋研究所課程
    eligible_year: int = None,  # 幾年級可修（修課資格）
    n: int = 8               # 回傳筆數
) -> list[CourseResult]
```

**觸發情境：** 語意搜尋、技術篩選、年次過濾、修課資格查詢

---

#### 工具 2：get_dept_courses — 系所必/選修課程（圖查詢）

```python
def get_dept_courses(
    dept_name: str,          # 系所名稱（支援模糊匹配）
    course_type: str = "required"  # "required"=必修 / "elective"=選修 / "all"=全部
) -> list[CourseItem]
```

**觸發情境：** 「資工系必修有哪些」、「哪些是系訂必修」

---

#### 工具 3：get_program_courses — 學分學程課程（圖查詢）

```python
def get_program_courses(
    program_name: str        # 學程名稱（支援模糊匹配）
) -> ProgramCourseResult
```

**觸發情境：** 「人工智慧學程要修什麼」、「資安學程有哪些課」

---

#### 工具 4：get_teacher_info — 教師開課與專長

```python
def get_teacher_info(
    teacher_name: str        # 教師姓名（如 "施國琛"）
) -> TeacherInfo            # 含 specialties + taught_courses
```

**觸發情境：** 「王小明教授教哪些課」、「他的研究方向是什麼」

---

#### 工具 5：search_teachers — 依專長找教師

```python
def search_teachers(
    query: str,              # 研究領域描述（如 "機器學習 NLP"）
    n: int = 5
) -> list[TeacherResult]
```

**觸發情境：** 「哪位教授專長是自然語言處理」

---

#### 工具 6：get_prereq_info — 先修課程查詢

```python
def get_prereq_info(
    course_query: str        # 課名或課號（如 "深度學習" 或 "CE4011"）
) -> PrereqResult           # 含目標課程資訊 + 先修課詳情
```

**觸發情境：** 「修深度學習要先修什麼」、「CE4011 的前置課程」

---

#### 工具 7：get_graduation_rules — 系所畢業規定

```python
def get_graduation_rules(
    dept_name: str           # 系所名稱
) -> GraduationInfo         # min_credits, required_credits, rules[], certs[]
```

**觸發情境：** 「資工系要幾學分才能畢業」、「有哪些畢業規定」

---

#### 工具 8：get_dept_info — 系所介紹

```python
def get_dept_info(
    query: str               # 系所名稱或描述（如 "適合喜歡設計的人"）
) -> list[DeptResult]       # 來自 ncu_departments 向量搜尋
```

**觸發情境：** 「電機系在學什麼」、「適合喜歡數學的人讀什麼系」

---

#### 工具 9：get_course_eligibility — 修課資格查詢

```python
def get_course_eligibility(
    course_query: str        # 課名或課號
) -> EligibilityInfo        # eligible_years, dept_include, open_to_minor, 等
```

**觸發情境：** 「CE3001 大幾才能修」、「這門課外系可以選嗎」

---

### 2.4 工具可並行執行的情境

GPT-4o function calling 支援一次回傳多個 tool_call，以下情境可並行：

```
問：「資工系大一上有哪些必修？這些課分別學什麼？」

並行執行：
  ├── get_dept_courses("資工系", "required")   → 必修清單
  └── search_courses("大一上 資工系", year=1, sem=1)  → 語意補充

問：「人工智慧學程的課裡，有沒有教 TensorFlow 的？」

串行執行（有依賴）：
  Step 1: get_program_courses("人工智慧")  → 課程清單
  Step 2: search_courses("TensorFlow", codes=上述清單)  → 交集篩選
```

---

## 三、具體查詢流程（NCU 實際情境）

### 情境 1：單一語意查詢（與現況相同，不需多步）

```
問：「有什麼和資料科學相關的課？」

Tool Call 1: search_courses("資料科學相關課程", n=8)
回答：整理前8筆相關課程
```

**工具呼叫次數：** 1 次

---

### 情境 2：系所 × 主題的複合查詢

```
問：「資工系有哪些 AI 相關的必選修課？」

Tool Call 1 (並行):
  ├── get_dept_courses("資工系", "all")          → 必+選修清單（圖）
  └── search_courses("人工智慧", dept="資工系")  → 語意匹配（向量）

LLM 整合兩組結果，取交集或標注哪些是必修/選修
```

**工具呼叫次數：** 1 輪（並行）

---

### 情境 3：先修鏈推理

```
問：「我想修機器學習，要先準備什麼？」

Tool Call 1: search_courses("機器學習")
  → 找到 "CE4041 機器學習"，prereq_codes = "MA1003,ST2001"

Tool Call 2 (並行，用 prereq_codes):
  ├── get_prereq_info("MA1003")  → 線性代數資訊
  └── get_prereq_info("ST2001")  → 機率統計資訊

LLM 組合：「要先修線性代數和機率統計，建議大二修完後再選」
```

**工具呼叫次數：** 2 輪

---

### 情境 4：年次課表規劃

```
問：「我是資工系大二學生，下學期有哪些必修要修？」

Tool Call 1 (並行):
  ├── get_dept_courses("資工系", "required")
  └── search_courses(dept="資工系", course_type="必修", year=2, sem=2)

LLM 交叉比對，回傳大二下的必修課，並標注建議修習時間
```

**工具呼叫次數：** 1 輪（並行）

---

### 情境 5：跨系查詢（外系學生）

```
問：「我是中文系大三，可以選資工系的哪些課？」

Tool Call 1: search_courses(
  "資工系課程",
  dept="資訊工程學系",
  eligible_year=3
)
Tool Call 1: get_course_eligibility 批次查詢（可用 dept_include 過濾）

LLM 整理「外系可選」的課程，說明是否有年級/系所限制
```

**工具呼叫次數：** 1-2 輪

---

### 情境 6：學程規劃複合查詢

```
問：「我想修人工智慧學程，現在大二，應該從哪些課開始？」

Tool Call 1 (並行):
  ├── get_program_courses("人工智慧")    → 學程必/選修清單
  └── search_courses(year=2, is_grad=False, query="人工智慧")

Tool Call 2: search_courses(
  prereq=None,    → 找「無先修」或「先修已在大一完成」的學程課
  year=2
)

LLM：整理大二可開始選的學程課，說明修完的建議順序
```

**工具呼叫次數：** 2 輪

---

### 情境 7：對話記憶的利用

```
輪 1：「資工系必修有哪些？」
  → Tool: get_dept_courses("資工系", "required")
  → 回答：列出 25 門必修

輪 2：「這些課裡面哪些是大二修的？」  ← 依賴上輪結果
  LLM 直接從上輪工具結果中過濾 when_year_start=2
  → 不需要再次呼叫工具

輪 3：「資料結構有哪些先修？」  ← 從上輪結果中的課程展開
  → Tool: get_prereq_info("資料結構")
```

---

## 四、系統提示詞設計

```
你是「中央大學選課助理」，協助學生了解 NCU 課程、系所、學分學程資訊。

## 你擁有的工具
- search_courses：語意搜尋課程，可加年級/系所/技術等條件
- get_dept_courses：查詢某系所的必修或選修課程（結構化資料）
- get_program_courses：查詢學分學程的必/選修課程
- get_teacher_info：查詢教師的開課與研究專長
- search_teachers：依研究領域找教師
- get_prereq_info：查詢課程的先修要求
- get_graduation_rules：查詢系所畢業學分與規定
- get_dept_info：查詢系所介紹與特色
- get_course_eligibility：查詢課程的修課資格限制

## 使用工具的原則
1. 複合問題請並行呼叫多個工具，不要等一個完成再呼叫下一個
2. 若工具結果已足夠回答，不要重複呼叫相同工具
3. 工具回傳的課號可用來串接下一次查詢（如先修展開）
4. 對話歷史中已有的工具結果不需重新查詢

## 回答原則
1. 使用繁體中文，語氣友善清楚
2. 根據工具結果回答，不捏造課號或學分數字
3. 涉及必修規劃時提醒「以學校最新公告為準」
4. 回答有結構性時用條列式，必要時標注資訊來源（如「依圖譜資料」）
5. 若 when 欄位標示 verified=false，提醒「修習學期資訊待學校確認」

## 資料覆蓋說明（讓你知道資料的限制）
- 建議修習學期（when）只有 28 個系所有資料，其他系所無此資訊
- 先修課號（prereq_codes）並非所有課程都有填寫
- 課程資料為 114 學年度，新開/停開課程可能有差異
```

---

## 五、實作對應：現有函式 → 工具包裝

### 需要新增的包裝函式（`services/tools.py`，新建）

```python
"""
tools.py - 將 retriever / graph_service 包裝成 Agent 工具

每個函式對應一個 OpenAI function schema，
同時作為 tool_call 的執行器。
"""

from app.services import retriever, graph_service


def tool_search_courses(query, dept=None, college=None, course_type=None,
                        year=None, sem=None, tech=None, is_grad=False,
                        eligible_year=None, n=8) -> list[dict]:
    """組裝 ChromaDB filters 後呼叫 retriever.search_courses"""
    filters = {}
    if dept:
        filters["dept"] = dept
    if college:
        filters["college"] = college
    if course_type:
        filters["type"] = course_type
    if tech:
        filters["$or"] = [
            {"tools": {"$contains": tech}},
            {"languages": {"$contains": tech}},
            {"concepts": {"$contains": tech}},
        ]
    if year is not None and sem is not None:
        filters["when_semesters"] = {"$contains": f"{year}_{sem}"}
    elif year is not None:
        filters["$or"] = [
            {"when_semesters": {"$contains": f"{year}_1"}},
            {"when_semesters": {"$contains": f"{year}_2"}},
        ]
    if eligible_year is not None:
        filters["eligible_years"] = {"$contains": str(eligible_year)}

    collection = "ncu_courses_grad" if is_grad else "ncu_courses_ug"
    return retriever.search_courses(
        query, filters=filters or None, n_results=n, collection=collection
    )


def tool_get_dept_courses(dept_name, course_type="required") -> dict:
    """圖查詢系所必修或選修，回傳結構化課程列表"""
    if course_type == "required":
        courses = graph_service.get_dept_required_courses(dept_name)
    elif course_type == "elective":
        courses = graph_service.get_dept_elective_courses(dept_name)
    else:
        courses = (
            graph_service.get_dept_required_courses(dept_name) +
            graph_service.get_dept_elective_courses(dept_name)
        )
    return {"dept_name": dept_name, "course_type": course_type, "courses": courses}


def tool_get_prereq_info(course_query) -> dict:
    """找到目標課程後展開先修課詳情"""
    results = retriever.search_courses(course_query, n_results=3)
    if not results:
        return {"found": False}
    target = results[0]
    meta = target.get("metadata", {})
    prereq_str = meta.get("prereq_codes", "")
    prereq_details = []
    if prereq_str:
        for code in prereq_str.split(","):
            code = code.strip()
            if code:
                prereq_details.extend(retriever.get_courses_by_code(code))
    return {
        "target_course": meta.get("name_zh"),
        "course_code": meta.get("course_code"),
        "prereq_codes": prereq_str,
        "prereq_details": prereq_details,
    }


def tool_get_teacher_info(teacher_name) -> dict:
    """教師基本資訊 + 開課清單"""
    profile = retriever.get_teacher_by_name(teacher_name)
    courses = graph_service.get_teacher_courses(teacher_name)
    return {"profile": profile, "courses": courses}
```

---

### 需要修改的檔案

| 檔案 | 變更 |
|-----|-----|
| `services/tools.py` | 新建：包裝函式 + OpenAI function schema 定義 |
| `services/llm_service.py` | 修改：加入 tool_use 模式的 `generate_answer_with_tools()` |
| `routes/chat.py` | 修改：新增 `/api/chat` 的 tool-use 路徑（可與舊路徑並存）|

---

## 六、工具 Schema 定義（OpenAI Function Calling 格式）

```python
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_courses",
            "description": "語意搜尋課程，支援依系所、技術、年級、選修別等條件過濾",
            "parameters": {
                "type": "object",
                "properties": {
                    "query":         {"type": "string", "description": "搜尋關鍵詞或自然語言描述"},
                    "dept":          {"type": "string", "description": "系所名稱，如「資訊工程學系」"},
                    "college":       {"type": "string", "description": "學院名稱，如「資訊電機學院」"},
                    "course_type":   {"type": "string", "enum": ["必修", "選修"], "description": "課程性質"},
                    "year":          {"type": "integer", "description": "建議修習年級（1-4）"},
                    "sem":           {"type": "integer", "enum": [1, 2], "description": "1=上學期, 2=下學期"},
                    "tech":          {"type": "string", "description": "技術或工具名稱，如「PyTorch」"},
                    "is_grad":       {"type": "boolean", "description": "是否搜尋研究所課程"},
                    "eligible_year": {"type": "integer", "description": "幾年級才可修（修課資格）"},
                    "n":             {"type": "integer", "description": "回傳筆數（預設8）"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dept_courses",
            "description": "查詢某系所的必修或選修課程（來自知識圖譜，結構化資料）",
            "parameters": {
                "type": "object",
                "properties": {
                    "dept_name":   {"type": "string", "description": "系所名稱，如「資訊工程學系」"},
                    "course_type": {"type": "string", "enum": ["required", "elective", "all"],
                                   "description": "required=必修, elective=選修, all=全部"},
                },
                "required": ["dept_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_program_courses",
            "description": "查詢學分學程的必修和選修課程",
            "parameters": {
                "type": "object",
                "properties": {
                    "program_name": {"type": "string", "description": "學程名稱，如「人工智慧技術應用」"},
                },
                "required": ["program_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_teacher_info",
            "description": "查詢特定教師的開課清單與研究專長",
            "parameters": {
                "type": "object",
                "properties": {
                    "teacher_name": {"type": "string", "description": "教師姓名"},
                },
                "required": ["teacher_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_teachers",
            "description": "依研究領域或專長關鍵詞搜尋教師",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "研究領域或專長描述"},
                    "n":     {"type": "integer", "description": "回傳筆數（預設5）"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_prereq_info",
            "description": "查詢課程的先修要求，並回傳先修課程的詳細資訊",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_query": {"type": "string", "description": "課程名稱或課號"},
                },
                "required": ["course_query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_graduation_rules",
            "description": "查詢某系所的畢業學分要求與畢業規定",
            "parameters": {
                "type": "object",
                "properties": {
                    "dept_name": {"type": "string", "description": "系所名稱"},
                },
                "required": ["dept_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dept_info",
            "description": "查詢系所介紹、學系特色、生涯進路（來自 Collego 資料）",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "系所名稱或描述（如「適合喜歡設計的人」）"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_course_eligibility",
            "description": "查詢某課程的修課資格（年級限制、系所限制、是否開放外系等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_query": {"type": "string", "description": "課程名稱或課號"},
                },
                "required": ["course_query"],
            },
        },
    },
]
```

---

## 七、延遲分析（基於 NCU 情境）

```
查詢類型                      工具呼叫數  估計延遲
─────────────────────────────────────────────────
單一語意搜尋                    1 次       1.5-3s
系所必修查詢（圖+向量並行）       1 輪×2     1.8-3.2s
先修鏈展開（2 輪）               2 輪       2.5-4.5s
年次規劃（並行）                 1 輪×2     1.8-3.2s
複合：系所×主題×年級             1 輪×3     2.0-3.5s

延遲上限估計：< 5s（含 GPT-4o 生成）
```

**重要：** LLM 生成才是瓶頸（占 70-80% 時間），工具呼叫本身（ChromaDB + 圖查詢）< 100ms。

**建議加入 Streaming：** 工具呼叫完成後立即開始 stream 回答，降低感知延遲。

---

## 八、實作優先順序

| 優先度 | 項目 | 預計工時 |
|--------|-----|---------|
| 🔴 P1 | `services/tools.py` — 包裝函式實作 | 2-3 hr |
| 🔴 P1 | `services/llm_service.py` — `generate_with_tools()` | 2-3 hr |
| 🔴 P1 | `routes/chat.py` — 新增 tool-use 路徑 | 1 hr |
| 🟡 P2 | 自動複雜度判斷（決定走哪條路徑） | 1 hr |
| 🟡 P2 | 對話記憶（message history 管理） | 1-2 hr |
| 🟢 P3 | Streaming 支援（`/api/chat/stream`） | 2 hr |
| 🟢 P3 | `get_learning_path()` — 基於 when 欄位的學習路徑建議 | 3-4 hr |
