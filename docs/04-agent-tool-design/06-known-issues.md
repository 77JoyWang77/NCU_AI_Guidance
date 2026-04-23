## 資料問題 (目前已修正，不過實際操作可能還需測試)

### data\processed\course_eligibility.json

現在裡面對於每個課程的結構實在非常不正確

我認為應該要做成適合進行 filter 的樣式，類似在進行判斷時給予學生身分就可以進行過濾，例如: 理學院學士班三、四年級，機械系一年級，管理學院一年級，資管一~四年級 ...

這種的過濾法?

資管一~四年級，就讓有允許任何一個資管系的年級都可以通過?或是要選出允許所有年級資管系的學生都可以修的課程

加上判斷是否為 only 碩士班/博士班/在職專班課程

例如:

1. 這個就是只有英美語文學系 3, 4 年級的人 + 輔系/雙主修-英美語文學系 可修

"raw_conditions": [
      "P1: 系所:限英美語文學系。年級:限三年級、四年級。 | P2: 系所:限英美語文學系。 | P3: 系所:限輔系-英美語文學系、雙主修-英美語文學系。"
    ]

2. 這個就是只有電機工程學系碩士班、電機工程學系博士班可以修，我覺得有一點比較重要的就是我覺得可以把這個課程進行標記，說這就是碩士班的課程，我們在進行課程推薦時可以預設先過濾掉碩士班課程，因為我們是做給高中生探索大學課程的，如果是他真的想要知道碩士班課程時在省略掉這層過濾

"raw_conditions": [
      "P1: 學制:限碩士班、博士班。學院:限資訊電機學院。系所:限電機工程學系碩士班、電機工程學系博士班。"
    ]

3. 這個就是雖然 P1 限制在電機工程學系碩士班、電機工程學系博士班一年級，但是 P2 就有電機工程學系可以修，所以這也可以算作為大學部可修習課程

"raw_conditions": [
      "P1: 系所:限電機工程學系碩士班、電機工程學系博士班。年級:限一年級。 | P2: 系所:限電機工程學系、電機工程學系博士班。"
    ]

4. 這個就是土木工程學系二三四年級 + 工學院學士班(所有年級) 可以修


"raw_conditions": [
      "P1: 系所:限土木工程學系。年級:限非一年級。 | P2: 系所:限工學院學士班。"
    ]

5. 這個是所有科系三四年級都可以修，非常廣泛，因為 P3 有提到，當然還有碩士班、博士班，

"raw_conditions": [
      "P1: 學制:限碩士班、博士班。 | P2: 系所:限土木工程學系。年級:限三年級、四年級。 | P3: 學制:限學士班。年級:限三年級、四年級。"
    ]

6. 這個非常廣泛看起來學士班二三四年級都可以修 (P2, P3, P4)，但是一年級只有土木工程學系、機械工程學系、工學院學士班，我認為班別在這裡不重要，畢竟高中生可能還比較不需要考慮到分班問題，非僑生/交換生可能也不重要，因為僑生/交換生感覺很難遇到

"raw_conditions": [
      "P1: 學制:限學士班。系所:限土木工程學系。年級:限一年級。班別:限A。身份:限非僑生/交換生。 | P1: 學制:限學士班。系所:限機械工程學系、工學院學士班。年級:限一年級。身份:限非僑生/交換生。 | P2: 學制:限學士班。年級:限四年級。身份:限非僑生/交換生。 | P3: 學制:限學士班。年級:限三年級。身份:限非僑生/交換生。 | P4: 學制:限學士班。年級:限二年級。身份:限非僑生/交換生。"
    ]

> **✅ 分析與建議**
>
> v3 schema（`07-course-eligibility-schema.md`）已採用 per-access-rule 結構（OR 邏輯、空 list = 不限），設計正確，無需重做。
>
> **高中生探索情境下的預設過濾策略**：
> - `is_grad_only=True` → 預設隱藏（不推薦給高中生）
> - `is_undergrad_open=True` → 預設顯示（大學部可修）
> - 班別（section_include）、性別限制、學號奇偶可直接忽略
> - 「符合任一 access_rule 即可修」是 OR 邏輯，「資管一~四年級都可修」= 有任一 rule 允許資管系該年級
>
> **ChromaDB 現況（已正確）**：`build_vector_index.py` 偵測到 `access_rules` 欄位時走 v3 路徑，`eligible_years` 是從 access_rules 重新計算的大學部可修年級，`is_grad_only`/`is_undergrad_open` 也已寫入 metadata。`eligible_years` 以逗號分隔字串儲存（如 "2,3,4"）是 ChromaDB 不支援 list 型別的技術限制，內容本身正確。如果上次 rebuild（`9bc62a6`）時 course_eligibility.json 已是 v3 格式，就不需要重跑。
>
> **仍需確認**：`search_courses` 的 `eligible_year` 參數過濾邏輯是否已配合 v3 metadata 格式正確運作（見 tool 設計第 1 項）。

---

## agent 架構設計

### _verify_course_list 

> 什麼情況才需要 LLM？
> 
> 只有一種邊緣情況需要 LLM：LLM 回答時改寫了課程名稱，例如：
> 
> - 工具找到「資訊工程學系演算法」→ LLM 回答說「資工的演算法課」→ 字串比對失敗
> 
> 但實際上 LLM 幾乎都直接引用工具回傳的課名，這個情況極少發生。若要處理，可以在字串比對失敗時加一層 fuzzy match，仍不需要 API call。


但是我們 LLM 在輸出課程時經常會出現部完成或是錯誤的課名，或許我們應該要設計成兩階段的 agent 會比較好? 尤其是在我們目前 tool與範例 非常多的情況下，應該將 ReAct agent 和最終回覆 agent 兩者分開表現是不是會比較好?

兩者分開表現會有一種好處，我們對於最終回覆又可以有更多的調整 fewshot 讓他想辦法以適合高中生理解的方向來回答問題，我們也可以將 tool 回傳的課程給予更多資訊到最終回覆 agent 讓他更完整的回覆問題

或許可以讓她輸出課程時已<course>課名</course>這樣的格式說不定會比較好處理?

還是說有什麼有什麼方法可以處理 agent 因為 context window 太長而導致無法輸出正確格式? 還是說要對歷史對話優先用 summary 看什麼資訊可以留下? 

還是要分成更多種 agent 的組合會更好，但最好是在兩層以內，為了 latency

或是要進行功能分流，例如探索/推薦多項課程、明確介紹解釋課程、了解學分學程、了解科系應修科目、了解系所與教授

> **✅ 分析與建議：採用兩階段設計 + `<course>` 標籤**
>
> **_verify_course_list 的 LLM call 可以大幅削減**：
>
> 建議三層漸進式比對：
> 1. 精確 match（exact match pool_map）→ 命中直接用
> 2. fuzzy match（`difflib.SequenceMatcher` ratio ≥ 0.85）→ 處理「資工的演算法課」這種改寫
> 3. 僅在以上兩層都失敗時才呼叫 LLM
>
> **更根本的解法：兩階段設計 + `<course>` 標籤**
>
> ```
> Stage 1 — ReAct 探索 agent（現有 stream_with_tools）
>   - 職責：工具呼叫、資訊收集，輸出盡量簡短（不需要對使用者說話）
>   - context 只保留工具結果摘要，不含 assistant 長文回覆
>   - 輸出：tool results summary + course_pool
>
> Stage 2 — 最終回覆 agent（新增）
>   - 職責：依使用者問題、tool results summary、pool 清單，撰寫友善回答
>   - 以 <course>課名</course> 標籤輸出提到的課程
>   - 可注入針對高中生的 few-shot examples
>   - 不受 ReAct context 污染，格式輸出穩定
> ```
>
> `<course>` 標籤的好處：
> - 前端 regex 直接解析，不需要猜測哪些文字是課名
> - 後端驗證只需 exact match + fuzzy，完全省去 LLM verify call
> - system prompt 加一條：「提到課程時請以 `<course>課名</course>` 標記，課名須與工具回傳完全一致」
>
> **Context window 過長問題**：採兩階段後 Stage 2 的 context 僅有「使用者問題 + tool results summary」，大幅縮短。若不採兩階段，可對每個工具結果截斷至 1500 token，並在超過 3 輪後壓縮舊 tool messages 為摘要。
>
> **功能分流**：目前不建議在 Stage 1 之前再加 router（多一次 LLM call、增加 latency）。應透過精心設計的 SYSTEM_PROMPT 讓 Stage 1 自行判斷，等效果不理想時再考慮引入 router。若未來確實需要，分流方向如下：
>
> | 類型 | 適合工具集 |
> |------|-----------|
> | 探索/推薦 | search_courses, ppr_explore, find_similar_courses, get_depts_by_tech |
> | 指定課程介紹 | get_course_knowledge_map, get_prereq_info, get_course_eligibility |
> | 學程探索 | search_programs（待新增）, get_program_description, get_program_courses |
> | 系所課程規劃 | get_dept_courses, get_graduation_requirements（合併後） |
> | 教師/系所 | get_teacher_info, search_teachers, get_dept_info |

---

## tool 設計



### 1. `search_courses` — 語意搜尋課程

**參數表**

1. 這兩個可能比較沒有使用情境的感覺?他們有必要嗎?

| `year` | integer | | — | 建議修習年級（1-4） |
| `sem` | integer | | — | `1`=上學期，`2`=下學期 |

> **✅ 建議：保留，低優先**
>
> `year` 對應 ChromaDB 的 `when_year_start/when_year_end` metadata，`sem` 對應 `when_semesters`。適用情境：「大一上有哪些課可以修？」。這是「課程計畫建議修習時間」而非「課程現在開不開」，需在 system prompt 中說明。LLM 不必主動使用，僅在使用者明確詢問時帶入。

2. 這個現在經過格式大改了，或許需要用別的過濾方式，還有研究所課程的定義，應該要是指學制還是分發條件是否只有碩士以上?

| `eligible_year` | integer | | — | 修課資格年級過濾 |
| `is_grad` | boolean | | `false` | `true`=搜尋研究所課程 |

> **✅ 建議**
>
> - **`eligible_year`**：依賴 v2 舊格式的 `eligible_years` 欄位，在 v3 schema 更新後已失效。建議**移除**（或等 ChromaDB metadata 更新後重新設計）。
> - **`is_grad`**：定義清晰（切換至 `ncu_courses_grad` collection），保留。預設 `False`，高中生情境下不改此預設。
> - **建議新增 `exclude_grad_only` 參數**（預設 `True`）：對 `ncu_courses_ug` 結果額外過濾掉 `is_grad_only=True` 的課程，確保大學部 collection 裡混進的研究所課程不會推薦給高中生。

**回傳格式**

"when_raw": "大二上", 這個感覺不是很必要?還不如放分發條件的 raw 更能顯示出它適合什麼科系或年級的人修，

"eligible_years": "2,3,4", 現在格式不同了這個也不對我覺得放 raw 的分發條件就好?

"summary": "課程摘要前 200 字..." 只放 200 字會不會不夠完善，或許可以放 concept 或是 tool ?

> **✅ 建議**
>
> | 欄位 | 現況 | 建議 |
> |------|------|------|
> | `when_raw` | "大二上" | **保留**，對了解課程規劃有用 |
> | `eligible_years` | "2,3,4"（v2 舊格式） | **移除**，改為 `raw_conditions`（原始分發條件文字）|
> | `summary` | 前 200 字 | **保留但補充**：另加 `concepts`（top 5 概念）和 `technologies`（top 5 技術）欄位 |
>
> 新增欄位：
> - `concepts`: NLP 提取的核心概念（如 `["機器學習", "神經網路", "反向傳播"]`）
> - `technologies`: NLP 提取的技術工具（如 `["PyTorch", "Python", "NumPy"]`）
> - `raw_conditions`: 原始分發條件文字（如 `"P1: 系所:限資訊工程學系。年級:限二、三年級。"`）
>
> 這樣 LLM 可直接從 `concepts`/`technologies` 判斷課程性質，從 `raw_conditions` 判斷修課資格，比 200 字摘要更精確且 token 更省。

2. `get_dept_courses` — 查詢系所必/選修課程

實際上的節點應該更為複雜

參考 @docs\02-midterm-report\knowledge_graph_v3.md

### Phase 1 節點（結構化）

| 節點類型 | 說明 | 關鍵屬性 | 來源 |
|---------|------|---------|------|
| `Department` | 系所 | name, program_type, min_credits | curriculum |
| `DeptGroup` | 系內分組（如甲/乙組） | name, group_label, min_credits | curriculum |
| `CollegeBachelorProgram` | 學院學士班 | name, min_credits | curriculum |
| `SpecializationTrack` | 專長分流（學士班內方向） | name, min_credits | curriculum |
| `CurriculumPlan` | 課程計畫（規則容器） | name, required_credits | curriculum |
| `GraduationRule` | 畢業規定 | type, description, credits | curriculum |
| `CreditProgram` | 學分學程 | name, college, min_credits, cross_school | credit_programs |
| `ElectiveGroup` | 選修群（規定最低選課數） | name, select, select_credits, group_rule | curriculum + cp |
| `Slot` | 等效課程群（擇一即可） | name, select, slot_rule | credit_programs |
| `Certification` | 證照／認證要求 | name | curriculum |
| `Course` | 課程 | code, name, credits, dept, college, level, semester, domains, source | raw |

### 3.1 機構結構（Phase 1）

| 邊 | 方向 | 說明 |
|----|------|------|
| `HAS_COLLEGE` | University → College | 大學設有此學院 |
| `HAS_DEPARTMENT` | College → Department | 學院下設系所 |
| `HAS_CBP` | College → CollegeBachelorProgram | 學院學士班 |
| `HAS_GROUP` | Department/CBP → DeptGroup | 系內分組 |
| `HAS_TRACK` | Department/CBP → SpecializationTrack | 專長分流 |
| `HAS_CURRICULUM` | 各節點 → CurriculumPlan | 制定課程計畫 |
| `HAS_ELECTIVE_GROUP` | CurriculumPlan → ElectiveGroup | 包含選修群 |
| `HAS_SLOT` | ElectiveGroup → Slot | 包含等效課程群 |
| `HAS_CREDIT_PROGRAM` | College → CreditProgram | 開設學分學程 |
| `GOVERNED_BY` | CurriculumPlan → GraduationRule | 受畢業規定約束 |
| `REQUIRES_CERTIFICATION` | 節點 → Certification | 要求取得證照 |

### 3.2 課程要求（Phase 1）

| 邊 | 方向 | 說明 |
|----|------|------|
| `REQUIRES` | CurriculumPlan → Course | 系所必修 |
| `OFFERS_ELECTIVE` | ElectiveGroup/Slot → Course | 選修選項 |
| `PROGRAM_REQUIRES` | CreditProgram → Course | 學程必修 |
| `REQUIRES_SLOT` | CreditProgram → Slot | 學程必修（擇一） |
| `PROGRAM_OFFERS` | CreditProgram → ElectiveGroup | 學程選修群 |
| `REQUIRES_PROGRAM` | Department/CBP → CreditProgram | 畢業必須完成學程（強制） |
| `PROGRAM_CHOICE` | Department/CBP → CreditProgram | 畢業擇一完成學程 |
| `PROGRAM_ELECTIVE` | Department → CreditProgram | 建議修習學程（非強制） |

面對這些複雜的節點我們應該如何處理? 尤其是有的在學系內還有進行分組? 或許到時候可能需要設計單獨的 agent 進行深入探索這個複雜的結構? 尤其是要教會 agent 回答這個會不會太難?

> **✅ 分析與建議**
>
> `graph_service.py` 已透過三層遍歷（Department/DeptGroup/CollegeBachelorProgram → HAS_CURRICULUM → CurriculumPlan → 選修/必修路徑）正確處理這些複雜節點，並用 `seen` set 去重。**程式邏輯本身沒問題**。
>
> 主要挑戰是：**agent 可能不知道要用什麼名稱查詢**（例如「工學院學士班」vs「機械工程學系」）。
>
> 建議：
> - 工具 description 加一句：「`dept_name` 可以是系所（如「資訊工程學系」）、學院學士班（如「理學院學士班」）或系內組別（如「機械工程學系甲組」）」
> - 讓 agent 先用 `get_dept_info` 確認節點名稱，再用 `get_dept_courses` 查詢
> - 不需要獨立的 sub-agent，在 system prompt 說明即可；若未來發現 LLM 頻繁用錯名稱，再考慮增加「列出系所結構」工具


### 3. `get_program_courses` — 查詢學程課程

那有沒有辦法進行學分學程的推薦? 我記得學分學程也有向量化進入 chroma ，這是原始檔案 @data\processed\program_descriptions.json 但是沒有課程，但足夠有推薦作用

> **✅ 建議：新增 `search_programs` 工具**
>
> `ncu_credit_programs` ChromaDB collection 已存在（向量化約 100+ 個學程），現有工具只支援精確查詢。
>
> ```
> search_programs
>   功能：語意搜尋學分學程（by 描述/主題/學院）
>   資料源：ChromaDB ncu_credit_programs collection
>   參數：query (string), n (int, 預設 5)
>   回傳：list[dict]，每筆含 program_name, college, description_excerpt
>   用途：「有沒有和 AI 相關的學程？」「理工學院有哪些學程？」
> ```
>
> 使用流程：`search_programs`（發現）→ `get_program_description`（了解詳情）→ `get_program_courses`（查看課程清單）。

### 4. `get_teacher_info` — 查詢教師詳情

暫無想法

### 5. `search_teachers` — 語意搜尋教師

暫無想法

### 6. `get_prereq_info` — 查詢先修條件

目前應該有先修條件的很少的感覺

> **✅ 分析**
>
> 確認：`course_eligibility.json` 統計顯示共 142 個課號有先修要求，佔全部約 3765 個課號的 3.8%，資料量確實稀少。
>
> 工具本身設計無誤，保留。建議在 system prompt 補充：「先修條件資料只涵蓋有明確登記先修要求的課程，多數課程未顯示不代表真的沒有隱性前置知識」。

### 7. `get_graduation_rules` — 查詢畢業學分規定

`get_requirements_notes` 包含更完整的原文說明，那為什麼不直接就留這個就好?

但是我想知道如果我直接問有哪些科系需要考證照才能畢業，這樣 agent 能夠回答嗎?

> **✅ 建議：合併為 `get_graduation_requirements`**
>
> 兩者的差異：
> - `get_graduation_rules`：從 schedule_draft JSON 取結構化資料（`min_credits`, `required_credits`, `certifications` list）→ 可程式化查詢
> - `get_requirements_notes`：從 requirements_notes.json 取完整原文字串 → 自然語言理解更好
>
> **「哪些科系需要考證照才能畢業」**：必須依賴 `get_graduation_rules` 的 `certifications` list（唯一可程式化掃描的來源）。若只留 `get_requirements_notes`，agent 需要對每個系所各呼叫一次並自行解析原文，非常低效。
>
> **建議合併為一個工具** `get_graduation_requirements(dept_name)`，回傳：
> ```json
> {
>   "dept_name": "資訊工程學系",
>   "min_credits": 128,
>   "required_credits": 60,
>   "certifications": ["英語能力認證"],
>   "raw_notes": "一、畢業應修最低學分數為 128 學分...（完整原文）"
> }
> ```
> Agent 既能從 `certifications` 快速判斷，也能從 `raw_notes` 引用原文細節，只需一次呼叫。

### 8. `get_dept_info` — 查詢系所介紹

暫無想法

### 9. `get_course_eligibility` — 查詢修課資格

回傳有必要放這麼長的篩選 json 格式嗎? 感覺直接給 agent 去讀取分發條件的 raw 應該比較好理解吧

參考 @data\processed\course_eligibility.json

> **✅ 建議：簡化回傳格式，只給 LLM 看 raw_conditions**
>
> `raw_conditions` 是中文原文，LLM 直接讀比解析 boolean flag 更可靠；boolean flag 是從 raw 提取出來的，對 LLM 來說是冗餘資訊。`course_relations` 的裸課程代碼（如 `CS1001`）LLM 看不懂，先修資訊由 `get_prereq_info` 負責，不應混入這裡。
>
> 建議新格式：
> ```json
> {
>   "found": true,
>   "match_type": "exact",
>   "courses": [
>     {
>       "course_code": "CS2001",
>       "name_zh": "演算法",
>       "dept": "資訊工程學系",
>       "raw_conditions": "P1: 系所:限資訊工程學系。年級:限非一年級。 | P2: 系所:限資訊工程學系。輔系-資訊工程學系、雙主修-資訊工程學系。"
>     }
>   ]
> }
> ```
>
> - **移除（LLM 回傳）**：`access_rules[]`、所有 boolean flag（`is_grad_only` 等）、`course_relations`
> - **保留（後端內部）**：boolean flag 仍由後端計算，用於程式化過濾（如引導模式預設隱藏研究所課程）；先修關係由 `get_prereq_info` 負責
> - **核心原則**：LLM 只需要能讀懂的資訊，所有可從 raw 推導的結構化欄位都不需要傳出去

### 10. `get_program_description` — 查詢學程說明

和 3. `get_program_courses` — 查詢學程課程 有相同問題，是否可以跟推薦學分學程做結合?

> **✅ 建議**
>
> 見第 3 項：新增 `search_programs` 工具承擔「推薦/發現學程」的職責，`get_program_description` 和 `get_program_courses` 保持現有「精確查詢」用途。三者形成完整的學程探索流程。


### 11. `get_requirements_notes` — 查詢畢業規定原文

和 7. `get_graduation_rules` — 查詢畢業學分規定 有相同問題，為什麼不只留一個就好? 還是說有什麼實際範例可以區分這兩者間的優勢

> **✅ 建議**：見第 7 項，合併為 `get_graduation_requirements`，不再分兩個工具。


### 12. `find_similar_courses` — 找相似課程

我想知道這樣的算法合適嗎? 那會不會就變成沒有辦法推薦包含比較少 concept 的課程? 有沒有什麼更好的建議方式? 還是說這並不會成為問題? 那 SIMILAR_TO 會不會

def enrich_concept_synonymy(G: nx.DiGraph) -> dict:
    """Phase 2-f：字串相似度建立 Concept / Technology 同義邊 SIMILAR_TO（雙向）。

    演算法：
    1. 建立字元反向索引 {char → {node_id}} 作為 blocking，減少 O(n²) 比對
    2. 候選對：共享字元 ≥ 2 個（中文字元只計非 ASCII）
    3. 用 difflib.SequenceMatcher 計算字串相似度
    4. 條件：ratio ≥ 0.70 且較長名稱 ≤ 2.5 倍較短名稱長度
    5. 建立雙向 SIMILAR_TO 邊，weight = ratio
    """

之前有提到過如果找到多個課程同樣名稱都為演算法的問題，那 tool 可能會不知道是哪門課程 (哪個科系開的)，這個可能只能依靠課號才能進行比對，或者說我們在找相似時可以使用多個 (同樣名稱的課程) 進行查找可以更周全? (指的是當沒有進行指定要用哪個特定科系的這個課程)


提取概念少的課程或許我們可以修改評估分數的方式來補全? 例如他說不定是我目標課程的子集，這應該也算高度相關?

> **✅ 分析與建議**
>
> **同名課程問題（多個「演算法」）**：
> 當使用者沒有指定科系，`find_similar_courses(course_name="演算法")` 目前只取第一筆匹配課程作為 seed。建議改為：先查出所有名稱完全符合的課程，取其概念的**聯集**作為 seed concepts，再計算 shared_concepts。這樣做的效果等同於「問的是任何一門演算法課共同涵蓋的概念圈」，比單取一門更周全，且不需要用戶指定科系。
>
> **概念子集的評分補強**：
> 目前分數是絕對數量（`shared_concepts`），對概念少的課程吃虧。你的想法很對——「A 的概念完全包含在 B 裡」應該是高度相關。可以補充一個**覆蓋率分數**：
> ```
> coverage = shared / len(candidate_concepts)
> ```
> 若 candidate 的概念幾乎全被 seed 涵蓋（coverage ≥ 0.8），即使 shared 絕對數量小，也應排在前面。可以用加權排序：`score = shared + 0.5 * coverage`，讓子集課程浮上來。
>
> **SIMILAR_TO 邊目前未被使用**：`enrich_concept_synonymy` 已在圖建構時建立這些邊，但 `find_similar_courses` 只遍歷 COVERS/TEACHES 出向邊，沒有再擴展同義邊。建議在收集 seed concepts 後，再走一步 SIMILAR_TO 邊把同義概念加入，覆蓋更多潛在相關課程。
>
> **整體建議優先序**：
> 1. 同名多課程 → 聯集 seed（改動小，效果明顯）
> 2. 覆蓋率加權分數（改動小，解決子集問題）
> 3. SIMILAR_TO 邊擴展（中等改動）
> 4. 概念 < 3 個時降級向量搜尋（保底機制）
> 5. 對比 `ppr_explore`：PPR 自然利用所有邊，適合「廣泛探索」；`find_similar_courses` 適合「精確概念相似度排序」，兩者並存有意義。


### 13. `get_course_knowledge_map` — 知識地圖探索

之前有提到過如果找到多個課程同樣名稱都為演算法的問題，那 tool 可能會不知道是哪門課程 (哪個科系開的)，這個可能只能依靠課號才能進行比對，或者說我們在找圖時可以使用多個 (同樣名稱的課程) 進行查找可以更周全? (指的是當沒有進行指定要用哪個特定科系的這個課程)

這個工具和找 `find_similar_courses` — 找相似課程感覺很像是不是可以只留這個刪除掉上面的? 或者是都留下也可以不過 prompt 要多加引導該如何使用這兩個 tool

> **✅ 分析與建議**
>
> **同名課程問題**：與 `find_similar_courses` 同樣的問題，但 `get_course_knowledge_map` 的目的是「深入理解一門課」，此時同名多課程的問題更嚴重——使用者問「演算法在學什麼」，系統應該：
> 1. 先告知有多個科系都有演算法課，並列出（課號 + 科系）
> 2. 讓使用者選擇（或在兩階段設計的 Stage 2 由 agent 詢問）
>
> 技術上可以在工具回傳時加一個 `ambiguous` 旗標 + candidates list，Stage 2 agent 看到後在回答中提示使用者。
>
> **與 `find_similar_courses` 的區別**：兩者的定位不同，建議都保留，但在 system prompt 中明確說明使用時機：
>
> | 工具 | 適用情境 |
> |------|---------|
> | `get_course_knowledge_map` | 使用者問「X 課程在學什麼？」、「X 課的知識地圖是什麼？」→ 重點是**了解這門課本身** |
> | `find_similar_courses` | 使用者問「有沒有類似 X 的課？」、「X 的替代課程？」→ 重點是**找到其他課** |
>
> `get_course_knowledge_map` 回傳的相似課程（top 8）是附帶資訊，不是主要目的；`find_similar_courses` 的相似課程（top 15）才是主要目的。不建議刪掉 `find_similar_courses`，因為它的結果更多且排序更精確。

### 14. `get_depts_by_tech` — 查詢技術分布系所

暫無想法

> **✅ 分析**
>
> 工具設計合理，多跳圖查詢（tech → courses → depts）且回傳區分必修/選修系所，這是很有用的維度（「哪些系把 Python 列為必修」vs「哪些系選修有 Python」意義不同）。
>
> 需要注意：技術名稱的命名變體（如 "Python" vs "Python3" vs "Python 程式語言"）在圖裡是否有 SIMILAR_TO 邊連結？如果沒有，使用者問 "Python3" 可能查不到 "Python" 的結果。建議在工具 description 提示 LLM 用通用技術名稱（如「Python」而非「Python 3.x」）。
>
> 整體無需大改，是目前 15 個工具中設計最完整的之一。

### 15. `ppr_explore` — Personalized PageRank 廣泛探索

暫無想法

> **✅ 分析**
>
> PPR 是最強大但也最「黑箱」的工具，幾個值得注意的點：
>
> **適用情境**：使用者問題模糊、跨領域、或無法對應到單一明確工具時使用。例如：「我對資料科學有興趣，有什麼推薦？」→ `ppr_explore(seed="資料科學,機器學習", focus="course")`。
>
> **seed 不存在時的行為**：目前程式用 exact-first 查找，若 seed 在圖裡找不到節點，會 fallback 到 substring 匹配。若完全找不到，回傳空結果。建議工具回傳加一個 `seed_found` 旗標，讓 LLM 知道是否真的找到 seed 節點，以便決定是否換關鍵字重試。
>
> **分數解讀**：原始 PageRank ×1000，通常高度相關節點會在 5~50 範圍，可以在工具 description 補充這個參考值，幫助 LLM 判斷結果品質。
>
> **與 `find_similar_courses` 的比較**：兩者都能找相關課程，差異是：
> - `ppr_explore` 可以跨 Course/Instructor/Dept/Concept 混合回傳，適合「探索」
> - `find_similar_courses` 只回傳課程且按概念重疊精確排序，適合「找替代課程」
>
> 目前設計合理，暫不需要大改。

---

## 待新增工具

### 16. `get_course_syllabus`（待新增）— 查詢課程詳細大綱

目前沒有工具可以查詢「課程目標」「授課內容」「教科書/參考書」等官方課綱欄位。這些資料在 raw JSON 的 `課程綱要` 物件中，`build_vector_index.py` 有讀取但只塞進 document 文字，沒有另存為 metadata，且教科書被截斷為 200 字。

> **✅ 建議：新增 `get_course_syllabus` 工具，並同步更新 ChromaDB metadata**
>
> **消歧義邏輯（同名課程問題）**：
>
> ```
> 路徑一（Agent 已知 course_code）：
>   search_courses() → 取得 course_code
>   → get_course_syllabus(course_code="CS3001")  ← 唯一，直接回傳
>
> 路徑二（使用者直接問課名）：
>   get_course_syllabus(name_zh="演算法")
>   → ChromaDB metadata filter: {name_zh: "演算法"}
>   → 找到 3 個不同科系 → 回傳 ambiguous=True + candidates
>   → Agent 詢問使用者（引導模式觸發條件五）
>   get_course_syllabus(name_zh="演算法", dept="資訊工程學系")
>   → 精確回傳
> ```
>
> **建議回傳格式**：
> ```json
> {
>   "found": true,
>   "ambiguous": false,
>   "course_code": "CS3001",
>   "name_zh": "演算法",
>   "dept": "資訊工程學系",
>   "teacher": "王教授",
>   "credits": 3,
>   "objective": "培養學生分析演算法時間與空間複雜度的能力...",
>   "content": "第1-3週：排序演算法...\n第4-6週：圖論基礎...",
>   "textbook": "Introduction to Algorithms (CLRS), 4th ed.",
>   "core_abilities": ["演算法分析能力", "解決複雜問題能力"]
> }
> ```
>
> **需要同步修改 `build_vector_index.py`**：將 `objective`、`content`、`textbook` 加入 metadata dict，不做截斷，重建 index 後工具才能直接 `collection.get(where={...})` 取到這三個欄位。同時移除 document 文字中 `textbook[:200]` 的截斷限制。
>
> **與現有工具的分工**：
>
> | 工具 | 用途 |
> |------|------|
> | `get_course_knowledge_map` | NLP 提取的概念圖：學什麼概念、用什麼技術 |
> | `get_course_syllabus`（新） | 官方課綱文字：課程目標、授課內容、教科書 |
> | `get_course_eligibility` | 誰能修這門課（分發條件） |
> | `get_prereq_info` | 先修/共修/衝堂關係 |

