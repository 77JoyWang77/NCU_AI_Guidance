# 知識圖譜建構報告

> 對應腳本：`scripts/graph/build_graph.py`  
> 輸出：`data/processed/graph/knowledge_graph.gpickle` / `.json` / `_stats.json`  
> 更新時間：2026-04-21（含 SIMILAR_TO 邊）

---

## 一、整體架構

圖譜分兩個建置階段：

```
Phase 1  基礎圖（結構化資料直接對應）
  ├─ curriculum_requirements_114.json     → 系所結構、必修課
  ├─ credit_programs/*.json               → 學分學程
  ├─ data/raw/courses/, graduate_courses/ → Course 節點（raw）
  └─ data/raw/scraped_missing/courses.json → 補爬課程

Phase 2  語意豐富化（NLP 萃取結果 + 補充資料）
  ├─ 2-a enrich_teacher_csv   ← 先建立全量 1,021 位 Instructor 節點
  ├─ 2-b enrich_nlp           ← NLP 六支檔案 → Field/Technology/Concept 節點
  ├─ 2-c enrich_professor_links ← COURSE_EXPERT 邊
  ├─ 2-d enrich_eligibility   ← PREREQUISITE_OF / COREQUISITE / eligible_years
  ├─ 2-e enrich_schedule      ← suggested_year / suggested_semester
  └─ 2-f enrich_concept_synonymy ← SIMILAR_TO 邊（字串相似度）
```

### 執行方式

```bash
# 完整流程（Phase 1 + Phase 2）
python scripts/graph/build_graph.py

# 只建基礎圖（快速，跳過豐富化）
python scripts/graph/build_graph.py --build-only

# 只執行豐富化（已有圖，補充 NLP 資料）
python scripts/graph/build_graph.py --enrich-only

# 只補 SIMILAR_TO 邊（最快）
python scripts/graph/build_graph.py --synonymy-only
```

---

## 二、節點類型

### Phase 1 節點（結構化）

| 節點類型 | 說明 | 關鍵屬性 | 來源 |
|---------|------|---------|------|
| `University` | 大學（根節點） | name, academic_year | curriculum |
| `College` | 學院 | name | curriculum |
| `Department` | 系所 | name, program_type, min_credits | curriculum |
| `DeptGroup` | 系內分組（甲/乙組） | name, group_label, min_credits | curriculum |
| `CollegeBachelorProgram` | 學院學士班 | name, min_credits | curriculum |
| `SpecializationTrack` | 專長分流（學士班內方向） | name, min_credits | curriculum |
| `CurriculumPlan` | 課程計畫（規則容器） | name, required_credits | curriculum |
| `GraduationRule` | 畢業規定 | type, description, credits | curriculum |
| `CreditProgram` | 學分學程 | name, college, min_credits, cross_school | credit_programs |
| `ElectiveGroup` | 選修群（規定最低選課數） | name, select, select_credits, group_rule | curriculum + cp |
| `Slot` | 等效課程群（擇一即可） | name, select, slot_rule | credit_programs |
| `Certification` | 證照／認證要求 | name | curriculum |
| `Course` | 課程 | code, name, credits, dept, college, level, semester, source | raw |
| `Instructor` | 授課教師（課程授課欄反推） | name | raw/courses |
| `Domain` | 課程領域 | name | raw/courses |
| `Competency` | 核心能力 | name | raw/courses |

### Phase 2 節點（NLP 豐富化）

| 節點類型 | 說明 | 關鍵屬性 | 來源 |
|---------|------|---------|------|
| `Field` | 學術研究領域（教師專長細分） | name, source | nlp_domain_tags / teacher_csv |
| `Technology` | 程式語言 / 框架 / 工具 | name, source | nlp_tech_nodes |
| `Concept` | 學術概念 | name, source | nlp_tech_nodes |

> **Instructor 節點補充說明**  
> Phase 1 只建立在課程授課欄出現過的教師節點（411 位）。  
> Phase 2-a 從 `114_ulistteacher.csv` 補充建立所有 **1,021 位**教師節點，  
> 並補上 `dept`、`rank`、`employment` 屬性。

---

## 三、邊類型

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

### 3.3 課程基本語意（Phase 1）

| 邊 | 方向 | 說明 |
|----|------|------|
| `TAUGHT_BY` | Course → Instructor | 由此教師授課 |
| `IN_DOMAIN` | Course → Domain | 屬於此課程領域 |
| `DEVELOPS` | Course → Competency | 培養此核心能力 |

### 3.4 NLP 語意豐富化（Phase 2）

| 邊 | 方向 | 說明 | 來源 |
|----|------|------|------|
| `COVERS_FIELD` | Course → Field | 課程涵蓋此研究領域（帶 `relevance`: high/medium/low） | nlp_domain_tags |
| `RELEVANT_EXPERT` | Instructor → Field | 教師為此領域研究專家（NLP 分析） | dept_professor_map |
| `EXPERT_IN` | Instructor → Field | 教師官方申報專長（教育部 CSV） | 114_ulistteacher.csv |
| `COURSE_EXPERT` | Instructor → Course | 教師專長與此課程領域直接相關（帶 `field`、`relevance`） | nlp_professor_links |
| `TAGGED_AS` | Course → Domain | 通識課主題標籤 | nlp_topic_tags |
| `TEACHES` | Course → Technology | 課程使用此程式語言/工具 | nlp_tech_nodes |
| `COVERS` | Course → Concept | 課程涵蓋此學術概念 | nlp_tech_nodes |
| `PREREQUISITE_OF` | Course → Course | 為另一門課的先修課 | course_eligibility |
| `COREQUISITE` | Course → Course | 須同學期一起修 | course_eligibility |
| `SIMILAR_TO` | Concept/Technology ↔ | 語意相近（字串相似度 ≥ 0.70） | enrich_concept_synonymy |

> **`COURSE_EXPERT` vs `RELEVANT_EXPERT` 的差異**  
> `RELEVANT_EXPERT`：Instructor → Field（教師的研究方向屬於某領域）  
> `COURSE_EXPERT`：Instructor → Course（NLP 分析認定此教師的專長與特定課程內容高度相關）  
> 後者可用於回答「誰應該是這門課的推薦顧問」或「哪位老師的研究最接近這門課」。

---

## 四、節點屬性補充（Phase 2）

Phase 2 在既有節點上**新增屬性**，不另建新節點：

| 節點 | 新增屬性 | 說明 | 來源 |
|------|---------|------|------|
| `Course` | `eligible_years` | 可修課的年級 list，如 `[1, 2]` | course_eligibility |
| `Course` | `open_to_minor` | 輔系學生可修 (bool) | course_eligibility |
| `Course` | `open_to_double_major` | 雙主修學生可修 (bool) | course_eligibility |
| `Course` | `suggested_year` | 建議修課年級（1-4） | schedule_draft |
| `Course` | `suggested_semester` | 建議修課學期（1=上/2=下） | schedule_draft |
| `Course` | `schedule_verified` | 學期資訊是否已人工驗證 (bool) | schedule_draft |
| `Course` | `core_questions` | 通識課核心議題問句 list | nlp_topic_tags |
| `Instructor` | `official_specialties` | 教育部申報的官方專長 list | 114_ulistteacher.csv |
| `Instructor` | `dept` | 所屬系所名稱 | 114_ulistteacher.csv |
| `Instructor` | `rank` | 職級（教授 / 副教授 / 助理教授 / 講師） | 114_ulistteacher.csv |
| `Instructor` | `employment` | 專任 / 兼任 | 114_ulistteacher.csv |

---

## 五、Course 節點的 source 屬性

| source 值 | 意義 |
|-----------|------|
| `"raw"` | 課號在 raw/courses 或 scraped_missing 中，有完整資料 |
| `"cp_only"` | 課號只在 credit_programs 中，無 raw 對應 → stub 節點 |
| `"curriculum_only"` | 課號只在 curriculum_requirements 中，無 raw 對應 → stub 節點 |

---

## 六、特殊節點：Slot

Slot 節點代表「從 N 個等效課程中選 1 門」的選課規則。

**情境 A：等效課程群**（原 `same_as` 欄位）  
「地球系統科學概論」在大氣系/地科系/太空系各有不同課號，三者等效：

```
ElectiveGroup
  └─[HAS_SLOT]─> Slot（地球系統科學概論）
                   ├─[OFFERS_ELECTIVE]─> Course(GP2004)
                   ├─[OFFERS_ELECTIVE]─> Course(AP2001)
                   └─[OFFERS_ELECTIVE]─> Course(ES2003)
```

**情境 B：學程 N 選 M 結構**  
每個 Slot 代表一個課程類別，類別內有多個可選課號。

---

## 七、Field / Domain / Concept 三者區別

| 節點 | 粒度 | 範例 | 建立方式 |
|------|------|------|---------|
| `Domain` | 粗（課程領域分類） | 「人工智慧」、「資料科學」 | 從課程綱要「課程領域」欄位直接建立 |
| `Field` | 細（教師/課程研究領域） | 「強化學習」、「衛星遙測」 | NLP 從教師專長詞彙萃取 |
| `Concept` | 細（課程涵蓋概念） | 「梯度下降」、「記憶體管理」 | NLP 從授課內容萃取 |
| `Technology` | 工具層 | 「PyTorch」、「Docker」 | NLP 從授課內容萃取 |

---

## 八、SIMILAR_TO 邊（Phase 2-f）

**目的**：將語意相近的 Concept / Technology 節點連結，支援跨詞彙的圖探索（例如「機器學習」和「機械學習」應視為同義）。

**演算法**：
1. 建立字元反向索引 `{char → {node_id}}`（中文字元）作為 blocking
2. 候選對：共享字元 ≥ 2 個
3. 計算 `difflib.SequenceMatcher` 字串相似度
4. 條件：ratio ≥ 0.70 且較長名稱 ≤ 2.5 倍較短名稱長度
5. 建立雙向 SIMILAR_TO 邊，帶 `weight = ratio`

**範例配對**：
- `機器學習` ↔ `機械學習`（ratio 0.75）
- `深度學習` ↔ `深層學習`（ratio 0.75）
- `Python` ↔ `Python3`（ratio 0.92）
- `資料結構` ↔ `資料結構與演算法`（ratio 0.73）

**規模**：2,532 配對，5,064 條邊（雙向計）

---

## 九、課號識別規則

- 課號去除班別後綴（`-A`、`-*` 等）作為節點 ID
  - 例：`CE2002-A` → `CE2002`、`MA1003-*` → `MA1003`
- 不同學期的同一課號合併為同一 Course 節點（`semester = "both"`）
- 課號不在 raw 時直接建 stub 節點，不做課名補救

---

## 十、統計（2026-04-21 含 SIMILAR_TO）

| 類型 | Phase 1（基礎圖） | Phase 2 後（實際值） |
|------|-----------------|-------------------|
| Course 節點（raw） | 1,348 | 1,348（新增屬性） |
| Course stub 節點 | 127 | 127 |
| Instructor 節點 | 411（課程授課欄） | **1,021**（全量 CSV 補建） |
| Domain 節點 | 209 | 209 |
| **Field 節點** | 0 | **3,594** |
| **Technology 節點** | 0 | **390** |
| **Concept 節點** | 0 | **6,938** |
| **TEACHES 邊** | 0 | **633** |
| **COVERS 邊** | 0 | **9,049** |
| **COVERS_FIELD 邊** | 0 | **3,720** |
| **EXPERT_IN 邊** | 0 | **2,629** |
| **COURSE_EXPERT 邊** | 0 | **3,522** |
| **PREREQUISITE_OF 邊** | 0 | **160** |
| **SIMILAR_TO 邊** | 0 | **5,064** |
| TAUGHT_BY 邊 | 897 | 897 |
| DEVELOPS 邊 | 4,209 | 4,209 |
| **總節點** | — | **14,602** |
| **總邊（含 SIMILAR_TO）** | — | **34,631** |

> Phase 1 Course 節點說明：1,348 門有完整 raw 資料，127 門為 stub（只在課程計畫 JSON 中出現）。

---

## 十一、igraph 格式輸出

`_save_igraph_format()` 將 NetworkX 圖轉換為 igraph 格式並儲存，預計算邊權重供 PPR 使用：

| 邊類型 | 預設權重 |
|--------|---------|
| `TEACHES` | 1.2 |
| `COVERS` | 1.0 |
| `COVERS_FIELD` (high) | 1.5 |
| `COVERS_FIELD` (medium) | 1.0 |
| `COVERS_FIELD` (low) | 0.5 |
| `PREREQUISITE_OF` | 0.8 |
| `EXPERT_IN` | 1.0 |
| `RELEVANT_EXPERT` | 1.0 |
| `COURSE_EXPERT` | 0.8 |
| `TAGGED_AS` | 0.5 |
| `IN_DOMAIN` | 0.5 |
| `DEVELOPS` | 0.3 |
| 其他 | 0.3 |

輸出：`data/processed/graph/knowledge_graph.pkl`（igraph pickle 格式）
