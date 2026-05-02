# RAG 系統設計

> 腳本：`scripts/rag/build_vector_index.py`  
> 向量資料庫：Qdrant（本地 file-mode，`data/processed/qdrant_data/`）  
> 嵌入模型：Azure OpenAI `text-embedding-3-large`（3,072 維）

---

## 一、概述

系統採用**五個 Qdrant Collection** 分別索引不同類型的資料，搭配**知識圖譜（igraph）**形成 GraphRAG 架構。這種設計讓 Agent 可以根據問題類型選擇最適合的資料源。

```
使用者問題
    ↓
ReAct Agent（決定呼叫哪些工具）
    ├─ 語意搜尋 → Qdrant（ncu_courses_ug/grad/teachers/departments/programs）
    ├─ 圖結構查詢 → igraph（knowledge_graph.pkl）
    └─ 規定查詢 → JSON（curriculum/credit_programs/schedule_draft）
```

---

## 二、五個 Qdrant Collection

| Collection | 內容 | 筆數 | 嵌入文字 |
|-----------|------|------|---------|
| `ncu_courses_ug` | 大學部課程 | ~1,400 | 課名 + 系所 + 教師專長 + 目標 + 內容 + NLP 萃取結果 |
| `ncu_courses_grad` | 研究所課程 | ~900 | 同上 |
| `ncu_teachers` | 教師資料 | 1,009 | 教師名 + 系所 + 職稱 + 專長清單 |
| `ncu_departments` | 系所介紹（Collego） | ~40 | 系名 + 學系特色 + 學科意涵 + 生涯進路 + 能力特質 |
| `ncu_credit_programs` | 學分學程 | 42 | 學程名 + 學院 + 最低學分 + 說明 + 課程清單 |

---

## 三、課程文件組裝（ncu_courses_ug/grad）

每門課程的嵌入文字由多個資料源整合而成：

```
課程名稱（英文名稱）
開課系所：{dept}
授課教師：{teacher}
教師專長：{teacher_specialties}         ← 來自 114_ulistteacher.csv
修課性質：{type_}
建議修習：{when_raw}                    ← 來自 schedule_draft
課程目標：{objective}
授課內容：{content}
相關概念：{simplified_text}             ← 來自 nlp_simplified_concepts.json
使用技術：{languages + tools}           ← 來自 nlp_tech_nodes.json
課程領域：{domain_tags}                 ← 來自 nlp_domain_tags.json
主題：{topic_tags}                      ← 來自 nlp_topic_tags.json（通識課）
核心議題：{core_questions}              ← 來自 nlp_topic_tags.json
相關研究領域：{prof_fields}             ← 來自 nlp_professor_links.json
核心能力：{ability_names}
參考書目：{textbook}
```

### Payload 欄位（Qdrant）

除嵌入文字外，每筆課程還儲存豐富的 payload 供過濾使用：

| 欄位 | 型別 | 用途 |
|------|------|------|
| `course_code` | string | 精確查詢 |
| `name_zh`, `name_en` | string | 顯示 |
| `dept`, `college` | string | 系所過濾 |
| `credits` | int | 學分過濾 |
| `type` | string | 必修/選修過濾 |
| `semester` | int | 1=上學期, 2=下學期 |
| `teacher` | string | 教師名稱 |
| `is_grad` | bool | 研究所課程識別 |
| `languages`, `tools`, `concepts` | list | 技術過濾（MatchAny） |
| `domain_tags`, `topic_tags` | list | 領域過濾 |
| `eligible_years` | list[int] | 年級過濾 |
| `dept_include`, `college_include` | list | 修課限制 |
| `prereq_codes`, `coreq_codes` | list | 先修/同修課 |
| `when_semesters` | list[str] | 建議修課學期（e.g. `["1_1","2_2"]`） |
| `open_to_minor`, `open_to_double_major` | bool | 輔系/雙主修開放 |
| `is_unrestricted` | bool | 無限制（全校可修） |
| `teacher_specialties` | string | 教師官方專長 |
| `objective`, `content`, `textbook` | string | 課綱原文 |

---

## 四、修課資格 v3（course_eligibility.json）

修課資格採用**多優先序 OR 邏輯**，語意為「符合任一 access_rule 即可修課」。

### 4.1 頂層結構

```json
{
  "course_code": "EE6012",
  "is_unrestricted": false,
  "is_grad_only": true,
  "is_undergrad_open": false,
  "has_special_condition": false,
  "access_rules": [
    {
      "program_types": ["master", "phd"],
      "dept_include": ["電機工程學系碩士班"],
      "years": []
    },
    {
      "program_types": [],
      "dept_include": ["電機工程學系"],
      "years": [4]
    }
  ],
  "course_relations": {
    "prereq_codes": ["EE3001"],
    "coreq_codes": [],
    "conflict_codes": [],
    "forbidden_codes": []
  }
}
```

### 4.2 頂層旗標

| 旗標 | 說明 |
|------|------|
| `is_unrestricted` | 無任何限制，全校皆可修 |
| `is_grad_only` | 所有 rule 都僅允許研究所 |
| `is_undergrad_open` | 至少一條 rule 允許大學部 |
| `has_special_condition` | 含無法完全結構化的複雜條件 |
| `has_conditional_prereq` | 先修只在部分優先序存在 |

### 4.3 access_rule 欄位

| 欄位 | 型別 | 說明 |
|------|------|------|
| `program_types` | list | `bachelor` / `master` / `phd` / `master_inservice` |
| `dept_include` | list | 允許修課的系所 |
| `dept_exclude` | list | 禁止修課的系所 |
| `college_include` | list | 允許修課的學院 |
| `years` | list[int] | 允許修課的年級（空 = 不限） |
| `open_to_minor` | bool | 輔系學生可修 |
| `open_to_double_major` | bool | 雙主修學生可修 |
| `open_to_credit_prog` | bool | 學分學程學生可修 |
| `open_to_cross_school` | bool | 跨校學生可修 |

### 4.4 統計（114 學年，3,765 個課號）

| 指標 | 數值 |
|------|------|
| access_rules 總數 | 7,282 條 |
| 無分發條件（全校可修） | 1,220 |
| 純研究所課程 | 1,116 |
| 大學部可修 | 2,649 |
| 有年級限制 | 1,748 |
| 有學制限制 | 1,035 |
| 有先修課程要求 | 142 |

---

## 五、三層 Hybrid 搜尋架構

`search_courses` 工具採用三層搜尋策略：

```
[有 tech 參數]
  → graph_service.search_courses_by_tech(tech)
    ← 知識圖譜 TEACHES/COVERS 邊精確查詢，優先走圖

[無 tech 參數] — 三層 Hybrid 流程

  Layer 1：Query Expansion（查詢擴展）
    → _search_concept_nodes(query, top_k=3)
      ← 在 Qdrant ncu_graph_nodes 中找語意相近的概念節點
    → 提取節點名稱，拼接 expanded_query
      例：「電腦看圖片」→ expanded =「電腦視覺 影像辨識 深度學習 電腦看圖片」

  Layer 2：Multi-signal Retrieval（多信號檢索）
    Signal A：retriever.search_courses(expanded_query, n_results=n×2)
    Signal B：retriever.search_courses(original_query, n_results=n×2)
    （兩個信號分別各自排名，互不干擾）

  Layer 3：RRF Fusion（倒數排名融合）
    → 按 course_code 合併排名分數
    → RRF(d) = Σ 1/(60 + rank_i(d))，取前 n 筆
```

---

## 六、四種分數說明

### 6.1 Qdrant `distance`（餘弦距離）

**公式**：`distance = 1 − cosine_similarity`（越小越好）

| distance 範圍 | 語意相似度 |
|-------------|-----------|
| 0.0 ~ 0.25 | 非常相似 |
| 0.25 ~ 0.5 | 相關 |
| 0.5 ~ 0.75 | 弱相關 |
| > 0.75 | 不相關 |

**使用工具**：`search_courses`, `search_teachers`, `get_dept_info`, `search_programs`

### 6.2 RRF Score（Reciprocal Rank Fusion）

**公式**：`RRF_score(d) = Σ_i 1/(60 + rank_i(d))`（k=60，越大越好）

| 特性 | 說明 |
|------|------|
| 越大越好 | 出現在多路信號且排名高 |
| 無需正規化 | 不同信號分數不需可比 |
| 穩健性 | 對異常排名不敏感（k=60 平滑效果） |

**使用工具**：`search_courses`, `find_similar_courses`, `get_course_knowledge_map`

### 6.3 知識圖譜 `shared_concepts`（共享概念數）

**計算**：`shared_concepts(A, B) = |concepts(A) ∩ concepts(B)|`

| shared_concepts | 相似程度 |
|----------------|---------|
| 0 | 無共享 |
| 1-2 | 弱相關 |
| 3-5 | 相關 |
| 6-10 | 高度相關 |
| 10+ | 同主題 |

**使用工具**：`find_similar_courses`, `get_course_knowledge_map`

### 6.4 PPR `score`（Personalized PageRank）

**公式**：`PPR(v) = α × Σ[PPR(u) × w(u,v)/degree(u)] + (1-α) × personalization(v)`

參數：
- α = 0.85（阻尼係數）
- 邊權重：TEACHES=1.2, COVERS=1.0, PREREQUISITE_OF=0.8, 其餘 0.3~0.5
- 輸出：`score = raw_PPR × 1000`

**Gap Truncation**：自動移除 score < mean − 0.5σ 的尾部噪音（< 4 筆時不截斷）

| score 範圍 | 相關程度 |
|-----------|---------|
| 100 ~ 1000 | 強相關 |
| 10 ~ 100 | 相關 |
| 1 ~ 10 | 弱相關 |

**使用工具**：`ppr_explore`

---

## 七、建立流程

```bash
# 建立所有 5 個 collection（需要 Azure OpenAI Embedding API）
python scripts/rag/build_vector_index.py

# 強制重建（清空舊資料）
python scripts/rag/build_vector_index.py --reset
```

**執行前提**：
- 已安裝 `qdrant-client`, `openai`, `tqdm`, `python-dotenv`
- `.env` 已設定 `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`
- `data/processed/courses_deduped/undergrad.json` 和 `grad.json` 已存在
- `data/raw/collego_ncu.json` 已存在

---

## 八、課程綱要 Payload 獨立更新

課程綱要（目標、內容、教科書）可透過 `update_syllabus_metadata.py` 獨立更新 Qdrant payload，**不需要重新嵌入**（嵌入只更新有語意需求的欄位）。

這讓系統可以：
1. 初始嵌入時使用較精簡的文字（減少 API 費用）
2. 後續用原文補充 payload 供 Agent 顯示

---

## 九、快取機制

`retriever.py` 使用 `@lru_cache(maxsize=512)` 快取 embedding 呼叫：

```
首次查詢（冷啟動）：~20-30s
　├─ Qdrant 初始化
　└─ Azure OpenAI Embedding API 呼叫

後續相同查詢（快取命中）：~2.6s
　└─ 直接使用快取向量，跳過 API 呼叫
```
