# 知識圖譜設計 v3

> 對應腳本：`scripts/graph/build_graph.py`  
> 輸出：`data/processed/graph/knowledge_graph.gpickle` / `.json` / `_stats.json`  
> 更新時間：2026-04-19

---

## 一、整體架構

圖譜分兩個建置階段：

```
Phase 1  基礎圖（結構化資料直接對應）
         curriculum_requirements_114.json
         credit_programs/*.json
         data/raw/courses/, graduate_courses/, scraped_missing/

Phase 2  語意豐富化（NLP 萃取結果 + 補充資料）
         data/processed/nlp/
           ├─ nlp_domain_tags.json      → COVERS_FIELD 邊
           ├─ nlp_tech_nodes.json       → TEACHES / COVERS 邊
           ├─ nlp_topic_tags.json       → TAGGED_AS 邊
           ├─ dept_professor_map.json   → RELEVANT_EXPERT 邊
           └─ nlp_professor_links.json  → COURSE_EXPERT 邊（新）
         data/processed/course_eligibility.json
         data/processed/schedule_draft/
         data/raw/114_ulistteacher.csv  → 全量 Instructor 節點 + EXPERT_IN 邊

Phase 2 執行順序（有依賴關係）：
  2-a  enrich_teacher_csv     ← 先建立全量 1009 位 Instructor 節點
  2-b  enrich_nlp             ← RELEVANT_EXPERT 需要 Instructor 節點先存在
  2-c  enrich_professor_links ← COURSE_EXPERT 需要 Instructor 節點先存在
  2-d  enrich_eligibility
  2-e  enrich_schedule
```

---

## 二、節點類型

### Phase 1 節點（結構化）

| 節點類型 | 說明 | 關鍵屬性 | 來源 |
|---------|------|---------|------|
| `University` | 大學（根節點） | name, academic_year | curriculum |
| `College` | 學院 | name | curriculum |
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
| `Instructor` | 授課教師（課程授課欄反推） | name | raw/courses |
| `Domain` | 課程領域 | name | raw/courses |
| `Competency` | 核心能力 | name | raw/courses |

### Phase 2 節點（NLP 豐富化）

| 節點類型 | 說明 | 關鍵屬性 | 來源 |
|---------|------|---------|------|
| `Field` | 學術研究領域（教師專長細分） | name, source | nlp_domain_tags / teacher_csv |
| `Technology` | 程式語言 / 框架 / 工具 | name, source | nlp_tech_nodes |
| `Concept` | 學術概念 | name, source | nlp_tech_nodes |

> **Instructor 節點擴充說明**：Phase 1 只建立在課程授課欄出現過的教師節點（約 411 位）。  
> Phase 2-a（`enrich_teacher_csv`）從 `114_ulistteacher.csv` 補充建立所有 1009 位教師節點，  
> 同時為新增節點補上 `dept`、`rank`、`employment` 屬性。

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
| `COURSE_EXPERT` | Instructor → Course | 教師專長與此課程領域直接相關（NLP 分析，帶 `field`、`relevance`） | nlp_professor_links |
| `TAGGED_AS` | Course → Domain | 通識課主題標籤 | nlp_topic_tags |
| `TEACHES` | Course → Technology | 課程使用此程式語言/工具 | nlp_tech_nodes |
| `COVERS` | Course → Concept | 課程涵蓋此學術概念 | nlp_tech_nodes |
| `PREREQUISITE_OF` | Course → Course | 為另一門課的先修課 | course_eligibility |
| `COREQUISITE` | Course → Course | 須同學期一起修 | course_eligibility |

> **`COURSE_EXPERT` 與 `RELEVANT_EXPERT` 的差異**  
> `RELEVANT_EXPERT`：Instructor → Field（教師的研究方向屬於某領域）  
> `COURSE_EXPERT`：Instructor → Course（NLP 分析認定此教師的專長與特定課程的教學內容高度相關）  
> 後者可用於回答「誰應該是這門課的推薦顧問」或「這門課和哪位老師的研究最接近」。

---

## 四、節點屬性補充（Phase 2）

Phase 2 會在既有節點上**新增屬性**，不建立新節點：

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

Slot 是「從 N 個等效課程中選 1 門」的選課規則節點。用於兩種情境：

**情境 A：等效課程群**（原 `same_as` 欄位）  
例如「地球系統科學概論」在大氣系/地科系/太空系各有不同課號，三者等效，擇一即可。

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

## 七、課號識別規則

- 課號去除班別後綴（`-A`、`-*` 等）作為節點 ID
- 例：`CE2002-A` → `CE2002`、`MA1003-*` → `MA1003`
- 不同學期的同一課號合併為同一 Course 節點（`semester = "both"`）
- 課號不在 raw 時直接建 stub 節點，不做課名補救

---

## 八、Field vs Domain vs Concept 的區別

三種語意節點容易混淆，說明如下：

| 節點 | 粒度 | 範例 | 建立方式 |
|------|------|------|---------|
| `Domain` | 粗（課程領域分類） | 「人工智慧」、「資料科學」 | 直接從課程綱要「課程領域」欄位建立 |
| `Field` | 細（教師專長領域） | 「強化學習」、「衛星遙測」 | NLP 從教師專長詞彙萃取 |
| `Concept` | 細（課程涵蓋概念） | 「梯度下降」、「記憶體管理」 | NLP 從授課內容萃取 |
| `Technology` | 工具層 | 「PyTorch」、「Docker」 | NLP 從授課內容萃取 |

---

## 九、執行方式

```bash
# 完整流程（建基礎圖 + NLP 豐富化）
python scripts/graph/build_graph.py

# 只建基礎圖（快速，跳過豐富化）
python scripts/graph/build_graph.py --build-only

# 只執行豐富化（已有圖，補充 NLP 資料）
python scripts/graph/build_graph.py --enrich-only
```

---

## 十、實際統計（2026-04-19 重建後）

| 類型 | Phase 1（基礎圖） | Phase 2 後（實際值） |
|------|-----------------|-------------------|
| Course 節點 | 1,475 | 1,475（新增屬性） |
| Instructor 節點 | 411（課程授課欄反推） | **1,021**（全量 CSV 補建） |
| Domain 節點 | 209 | 209（通識主題補充後） |
| **Field 節點** | 0 | **3,594** |
| **Technology 節點** | 0 | **390** |
| **Concept 節點** | 0 | **6,938** |
| **TEACHES 邊** | 0 | **633** |
| **COVERS_FIELD 邊** | 0 | **3,720** |
| **EXPERT_IN 邊** | 0 | **2,629** |
| **COURSE_EXPERT 邊** | 0 | **3,522**（新） |
| **PREREQUISITE_OF 邊** | 0 | **160** |
| TAUGHT_BY 邊 | 897 | 897 |
| DEVELOPS 邊 | 4,209 | 4,209 |
| 總節點 | — | **14,602** |
| 總邊 | — | **29,567** |

> **Phase 1 Course 節點說明**：1,348 門有完整 raw 資料，127 門為 stub（只在課程計畫 JSON 中出現，無對應原始課程 JSON）。
