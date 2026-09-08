# Fig 1 — NLP 多 Agent 知識萃取 Pipeline

## 論文定位

展示如何用 LLM 將非結構化課綱自動轉化為知識圖譜可用的結構化標籤。
這是本系統資料建構的核心獨特設計：以多個任務分工的 LLM Agent 串接，
取代人工標注或規則式解析，覆蓋全校數千門課程。

---

## 圖表類型建議

流程圖（Flowchart）或 Pipeline 泳道圖（Swimlane Diagram）。
重點呈現：輸入→前置過濾→各 Agent 分工→後處理→輸出的完整鏈條，
以及 Agent1 ‖ Agent3 可並行的結構。

---

## 輸入資料

| 資料來源 | 格式 | 關鍵欄位 |
|---|---|---|
| 原始課綱 JSON（`data/raw/courses/114_1/*.json`） | JSON | 課程名稱、開課系所、課程目標、授課內容、教科書 |
| 研究所課綱（`data/raw/graduate_courses/**/*.json`） | JSON | 同上 |
| 教師資料（`data/raw/114_ulistteacher.csv`） | CSV | 系所名稱、教師姓名、聘書職級、專兼任、教師專長 |

---

## 前置過濾器：course_classifier.py

所有 Agent 在處理前先呼叫此模組，決定課程進入哪個處理路徑。

### 四種分類（優先順序由高至低）

| 分類 | 觸發條件 | 後續處理 |
|---|---|---|
| `SKIP` | 已停開課程、三欄皆空、體育/軍訓等系所 | 完全跳過 |
| `SEQUENCE_ONLY` | 語言中心、服務學習、職涯發展類課程 | 僅序列處理（不走 LLM） |
| `TOPICS_ONLY` | 通識課程（GS/CC 開頭課號）、核心通識 | 走 Agent3 主題分類路徑 |
| `FULL` | 其他所有一般課程 | 走 Agent1 + Agent2 + Agent4 完整路徑 |

---

## Agent 1 — 技術節點萃取（run_agent1_tech.py）

**任務**：從課程目標、授課內容、教科書中萃取結構化技術資訊

**輸入**：課程 JSON（三欄各取前 2000 字元）

**LLM**：Qwen3-14B-AWQ via 本地 vLLM（localhost:8000，OpenAI 相容 API）
- Temperature: **0**（精確輸出，不要創意）

**輸出欄位（nlp_tech_nodes.json）**：
```json
{
  "課號": {
    "languages": ["Python", "C++", "R"],
    "tools":     ["PyTorch", "TensorFlow", "Pandas", "MATLAB"],
    "concepts":  ["資料結構", "機率論", "梯度下降", "卷積神經網路"]
  }
}
```

**三類標籤定義**：
- `languages`：程式語言（Python、C++、R、Java 等）
- `tools`：框架/工具/平台（PyTorch、MySQL、Docker 等）
- `concepts`：學術概念與理論（資料結構、傅立葉轉換、梯度下降 等）

**工程設計亮點**：
- 批次處理：每 50 筆存檔一次（斷點續跑，大規模處理不怕中斷）
- Qwen3 `<think>...</think>` 思考區塊後處理移除（LLM 特有輸出格式）
- Debug log 寫入 `logs/agent1_llm_debug.txt`（方便追蹤 LLM 輸出品質）

---

## Agent 3 — 通識課主題分類（run_agent3_topics.py）

**與 Agent1 可並行執行**（處理不同類型的課程）

**任務**：僅處理通識課程，分類主題標籤 + 萃取核心議題

**輸入**：TOPICS_ONLY 類型的課程（GS/CC 課號）

**LLM**：Qwen3-14B-AWQ
- Temperature: **0.6**（較高，鼓勵多樣化描述核心議題）

**輸出欄位（nlp_topic_tags.json）**：
```json
{
  "課號": {
    "topic_tags":     ["哲學", "倫理學"],
    "core_questions": ["什麼是幸福？", "道德判斷有客觀標準嗎？"]
  }
}
```

**合法主題標籤（25 個，prompt 硬性約束輸出範圍）**：

| 類別 | 標籤 |
|---|---|
| 人文 | 哲學、歷史、文學、語言學、藝術、音樂 |
| 社會 | 社會學、心理學、法律、政治、經濟、宗教 |
| 自然科學 | 物理、化學、生物、環境科學、數學 |
| 應用科技 | 資訊科技、工程、醫學 |
| 跨域 | 倫理學、性別研究、族群文化、全球化、永續發展 |

---

## Agent 2 — 研究領域匹配（run_agent2_domain.py）

**需要先完成**：normalize_teacher_specialties.py + Agent1

**任務**：將課程與系所教授研究領域做多對多匹配
→ 橋接「課程教了什麼」與「哪個教授專長這個領域」

**特色設計：受約束詞彙表（Constrained Vocabulary）**
- 以系所教授專長詞彙集作為 LLM 輸出的唯一可選詞彙
- 上限 80 詞（避免 context 爆炸）
- LLM 不能自由發明領域名稱，只能從詞彙表中選擇
- 這確保了課程-領域-教授三角關係的一致性

**LLM**：Qwen3-14B-AWQ
- Temperature: **0**
- Prompt 附帶 Agent1 的技術資訊作為 Chain-of-Thought 線索

**前置步驟（normalize_teacher_specialties.py）**：
- 從教師 CSV 整理出 `dept_professor_map.json`
- 每個系所 → 所有教授專長詞彙的並集（`specialty_vocab`）
- 格式：`{"系所名稱": {"specialty_vocab": [...], "professors": [...]}}`

**輸出**：
```json
{
  "課號": {
    "domain_tags": [
      {"field": "機器學習", "relevance": "high"},
      {"field": "電腦視覺", "relevance": "medium"}
    ]
  }
}
```
後處理同時產出 `nlp_professor_links.json`（反查哪位教授專長此領域）

---

## Agent 4 — 概念高中生友善化（run_agent4_simplify.py）

**需要先完成**：Agent1

**任務**：將大學技術概念改寫成高中生能理解的說法，作為課程介紹橋接

**學院自動分類（11 類）**：
先由課程系所偵測所屬學院，再選用該學院特定的 Prompt 示範

| 學院類型 | 代碼 | 典型概念範例 |
|---|---|---|
| 資訊/電機 | `eecs` | 演算法、資料結構、電路分析 |
| 工程 | `engineering` | 熱力學、材料力學、流體力學 |
| 數學/物理/統計 | `math_phys` | 微積分、線性代數、量子力學 |
| 化學 | `chemistry` | 原子結構、酸鹼、有機化學 |
| 生命科學 | `life_sci` | 細胞結構、演化、遺傳 |
| 生醫/神經科學 | `biomedical` | 基因表現、磁振造影、腦機介面 |
| 地球/太空科學 | `earth_space` | 板塊構造、大氣環流、黑體輻射 |
| 永續/綠能 | `sustain` | 永續發展目標、碳封存、燃料電池 |
| 管理/商學 | `management` | 財務報表、市場區隔、供應鏈 |
| 法律/社會 | `social_law` | 公司法、建構主義教學 |
| 人文/語言 | `liberal_arts` | 六書、音韻、田野調查 |

**LLM**：Qwen3-14B-AWQ
- Temperature: **0.3**（保守，確保與高中知識的對應準確）

**改寫規則**：
1. 優先與高中課程關聯，標注科目（如「（高中數學：最小值求法）」）
2. 無關聯則用淺白定義（20 字以內）
3. 工具名稱或已足夠淺顯者直接原文

**輸出**：
```json
{
  "課號": {
    "simplified_concepts": [
      {"original": "梯度下降", "display": "最佳化搜尋最小值的方法"},
      {"original": "CNN",     "display": "卷積神經網路，辨識影像的 AI 模型"}
    ],
    "college": "eecs"
  }
}
```

---

## 後處理雙層清理

### fix_tech_nodes.py（技術節點修復）

**時機**：可在 Agent1 完成後任意時間點執行

**兩步處理**：
1. **簡繁轉換**：opencc（s2tw 模式）全面轉換
2. **英文術語翻譯**（批次 30 詞/次）：
   - 縮寫（CNN/RNN/LSTM/GAN）→ 保留 + 加中文（`CNN（卷積神經網路）`）
   - 工具名稱（Python/PyTorch）→ 保持英文
   - 一般概念 → 翻成繁體中文
   - 備份原始檔 → 覆蓋

### postprocess_simplified.py（簡化概念清理）

**時機**：Agent4 完成後執行

**三步處理**：
1. 移除高中標籤：正規表達式 `[（(]\s*高中[^）)]*[）)]`
2. 簡繁修正：opencc + 62 個特殊詞字典（「数据」→「數據」等）
3. 標點/空白清理：多餘空白合一、結尾標點移除

---

## 完整依賴鏈（建議圖中標示執行順序）

```
[教師 CSV]
    │
    ▼
normalize_teacher_specialties.py
    │ dept_professor_map.json
    │
    ├──────────────────────────────────────────────┐
    │                                              │
[課綱 JSON] ──────────────────────────────────────┤
    │                                              │
    ▼                                              ▼
run_agent1_tech.py               run_agent3_topics.py
（FULL 類型課程）                （TOPICS_ONLY 類型課程）
Temperature=0                    Temperature=0.6
    │ nlp_tech_nodes.json             │ nlp_topic_tags.json
    │                                 │
    ├─────────────────┐               │
    │                 │               │
    ▼                 ▼               ▼
run_agent2_domain.py   run_agent4_simplify.py
（需要 agent_map +      Temperature=0.3
 tech_nodes）           11 學院分類 Prompt
Temperature=0               │
    │ nlp_domain_tags.json  │ nlp_simplified_concepts.json
    │ professor_links.json  │
    │                       ▼
    │               postprocess_simplified.py
    │               （清理高中標籤/簡繁）
    │
    └── fix_tech_nodes.py（任意時機，修復術語）
    
    ┌───────────────────────────────┐
    │     最終輸出（建圖輸入）      │
    │ nlp_tech_nodes.json           │
    │ nlp_topic_tags.json           │
    │ nlp_domain_tags.json          │
    │ nlp_simplified_concepts.json  │
    └───────────────────────────────┘
```

---

## 設計決策補充說明（論文 Discussion 可引用）

- **為何用本地 vLLM 而非 API**：離線批次處理數千門課程，本地部署避免 API 成本與速率限制
- **Temperature 差異化設計**：不同任務對輸出多樣性的需求不同；主題分類（0.6）需要創意描述，技術萃取（0）需要精確
- **受約束詞彙表（Agent2）**：解決 LLM 自由生成導致的領域名稱不一致問題，確保可與教授資料對齊
- **高中橋接設計（Agent4）**：面向高中生選系情境，降低大學課程的理解門檻，這是本系統的應用場景特色
