# NLP 萃取 Pipeline 完成報告

> 完成時間：2026-04-13
> 模型：Qwen3-14B-AWQ via vLLM (`http://localhost:8000/v1`)
> 資料來源：`data/raw/courses/114_1/`（44 個系所 JSON，~1,700 門課）

---

## 一、執行結果摘要

| 腳本 | 輸出檔案 | 大小 | 說明 |
|------|---------|------|------|
| `normalize_teacher_specialties.py` | `dept_professor_map.json` | 300 KB | 54 系所，1009 位教師，2469 個專長詞彙 |
| `run_agent1_tech.py` | `nlp_tech_nodes.json` | 857 KB | 技術節點（languages / tools / concepts） |
| `fix_tech_nodes.py` | `nlp_tech_nodes.json`（覆寫） | 857 KB | 英文概念翻繁中、繁體化後處理 |
| `run_agent2_domain.py` | `nlp_domain_tags.json` | 1.1 MB | 課程 → 研究領域標籤（high/medium/low） |
| `run_agent2_domain.py` | `nlp_professor_links.json` | 1.4 MB | 課程 → 相關教授（規則反查） |
| `run_agent3_topics.py` | `nlp_topic_tags.json` | 38 KB | 通識課主題標籤 + 核心議題問句 |
| `run_agent4_simplify.py` | `nlp_simplified_concepts.json` | 2.6 MB | 概念高中生友善化（含高中科目連結） |
| `postprocess_simplified.py` | `nlp_simplified_concepts.json`（覆寫） | 2.6 MB | 去除標籤、繁體化後處理 |

所有輸出位於 `data/processed/`。

---

## 二、Pipeline 執行順序

```
normalize_teacher_specialties.py
  └─→ dept_professor_map.json

run_agent1_tech.py
  └─→ nlp_tech_nodes.json
       ├─ fix_tech_nodes.py（後處理，覆寫）
       └─→ run_agent2_domain.py（依賴此檔）
             └─→ nlp_domain_tags.json
                  └─→ nlp_professor_links.json（規則反查，同腳本產出）

run_agent3_topics.py（無依賴，獨立跑）
  └─→ nlp_topic_tags.json

run_agent4_simplify.py（依賴 nlp_tech_nodes.json）
  └─→ nlp_simplified_concepts.json
       └─ postprocess_simplified.py（後處理，覆寫）
```

---

## 三、輸出格式範例

### nlp_tech_nodes.json
```json
{
  "CS1001": {
    "languages": ["C", "Python"],
    "tools": ["GDB", "Makefile"],
    "concepts": ["系統程式設計", "記憶體管理", "行程排程"]
  }
}
```

### nlp_domain_tags.json
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

### nlp_professor_links.json
```json
{
  "CS1001": [
    {"field": "系統程式設計", "professors": ["王○○", "李○○"], "relevance": "high"}
  ]
}
```

### nlp_topic_tags.json（通識課）
```json
{
  "GE1001": {
    "topic_tags": ["哲學", "倫理學"],
    "core_questions": ["什麼是幸福？", "道德判斷有客觀標準嗎？"]
  }
}
```

### nlp_simplified_concepts.json
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

---

## 四、課程分類器

`scripts/nlp/course_classifier.py` 決定每門課進入哪個 pipeline 分支：

| 分類 | 條件 | 處理 |
|------|------|------|
| `SKIP` | 體育、軍訓、已停開、三欄全空 | 不做任何萃取 |
| `SEQUENCE_ONLY` | 語言中心、服務學習、職涯 | 只做序列先修（規則式） |
| `TOPICS_ONLY` | 通識、核心通識 | Agent 3 主題分類 |
| `FULL` | 其餘（工程、理科、管理、文學等） | Agent 1 + Agent 2 + Agent 4 |

---

## 五、後續整合

- **圖譜整合**：`scripts/graph/merge_nlp_to_graph.py`（已完成）
  - 新增節點類型：`Field`（研究領域，來自教師專長）
  - 新增邊：`COVERS_FIELD`（Course→Field）、`RELEVANT_EXPERT`（Instructor→Field）、`TAGGED_AS`（Course→Domain，通識）
- **下一步**：`docs/03-next-steps/` 中的應修科目表年級/學期萃取
