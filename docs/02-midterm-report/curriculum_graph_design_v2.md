# 知識圖譜設計 v2：三大資料源整合

> 建圖腳本：`scripts/graph/build_knowledge_graph.py`
> 輸出：`data/processed/graph/knowledge_graph.gpickle` / `.json`
> 最後更新：2026-04-05

---

## 一、三大資料源現況

| 資料源 | 路徑 | 課號數 | 主要資訊 |
|--------|------|--------|---------|
| **課程資料（大學部）** | `data/raw/courses/114_1/, 114_2/` | 2,567 | 課號、課名、學分、教師、領域、核心能力 |
| **課程資料（研究所）** | `data/raw/graduate_courses/114_1/, 114_2/` | 928 | 同上 |
| **補爬課程** | `data/raw/scraped_missing/courses.json` | 308 | 不在 114 raw 中，另行搜尋最新學期補齊 |
| **應修科目表** | `data/processed/curriculum_requirements_114.json` | 458 | 系所必修清單、畢業學分規定、選修群 |
| **學分學程** | `data/processed/credit_programs/*.json` | 998 | 學程必選修課程、最低學分、跨校資訊 |
| **raw 合計** | — | **3,803** | 去重後 |

---

## 二、節點類型（Nodes）

| 節點 | 關鍵屬性 | 來源 |
|------|---------|------|
| `University` | name, academic_year | curriculum |
| `College` | id, name | curriculum |
| `Department` | id, name, program_type, min_credits | curriculum |
| `DeptGroup` | id, name, group_label, min_credits | curriculum |
| `CollegeBachelorProgram` | id, name, min_credits | curriculum |
| `SpecializationTrack` | id, name, min_credits | curriculum |
| `CurriculumPlan` | id, name, required_credits | curriculum |
| `GraduationRule` | type, description, credits... | curriculum |
| `CreditProgram` | id, name, college, min_credits, cross_school | credit_programs |
| `ElectiveGroup` | id, name, select, select_credits, group_rule | curriculum + cp |
| `Slot` | id, slot_name, select, slot_rule | credit_programs |
| `Course` | code, name, credits, dept, college, level, semester, domain, **source** | raw / stub |
| `Instructor` | name | raw/courses |
| `Domain` | name | raw/courses |
| `Competency` | name | raw/courses |
| `Certification` | name | curriculum |

### Course 節點的 source 屬性

| source 值 | 意義 |
|-----------|------|
| `"raw"` | 課號在 raw/courses 或 scraped_missing 中找到，有完整資料 |
| `"cp_only"` | 課號只在 credit_programs 中出現，raw 無對應 → stub 節點 |
| `"curriculum_only"` | 課號只在 curriculum_requirements 中出現，raw 無對應 → stub 節點 |

> **課號不在 raw 時直接建 stub 節點，不做課名補救（無 MAPS_TO 邊）。**

---

## 三、邊類型（Edges）

### 3.1 系所結構邊（curriculum_requirements）

| 邊 | 方向 | 數量 |
|----|------|------|
| `HAS_COLLEGE` | University → College | 8 |
| `HAS_DEPARTMENT` | College → Department | 23 |
| `HAS_CBP` | College → CollegeBachelorProgram | 5 |
| `HAS_GROUP` | Department/CBP → DeptGroup | 9 |
| `HAS_TRACK` | Department/CBP → SpecializationTrack | 24 |
| `HAS_CURRICULUM` | 各節點 → CurriculumPlan | 67 |
| `GOVERNED_BY` | CurriculumPlan → GraduationRule | 228 |
| `REQUIRES` | CurriculumPlan → Course（系定必修） | 746 |
| `HAS_ELECTIVE_GROUP` | CurriculumPlan → ElectiveGroup | 57 |
| `OFFERS_ELECTIVE` | ElectiveGroup/Slot → Course | 1,668 |
| `REQUIRES_CERTIFICATION` | 節點 → Certification | 4 |

### 3.2 學分學程邊（credit_programs）

| 邊 | 方向 | 數量 | 說明 |
|----|------|------|------|
| `HAS_CREDIT_PROGRAM` | College → CreditProgram | — | 學院開設學程 |
| `PROGRAM_REQUIRES` | CreditProgram → Course | 44 | 學程一般必修 |
| `REQUIRES_SLOT` | CreditProgram → Slot | 13 | 學程必修但有等效選擇（原 same_as 必修） |
| `PROGRAM_OFFERS` | CreditProgram → ElectiveGroup | 167 | 學程選修群 |
| `HAS_SLOT` | ElectiveGroup → Slot | 116 | 等效課程群（原 same_as 選修） |
| `REQUIRES_PROGRAM` | Department/CBP → CreditProgram | 1 | 畢業強制完成學程（資電學士班 → 創意與創業） |
| `PROGRAM_CHOICE` | Department/CBP → CreditProgram | 4 | N 選一學程（地科系/地科院學士班三選一） |
| `PROGRAM_ELECTIVE` | Department → CreditProgram | 2 | 鼓勵選修之學程（企管系） |

### 3.3 課程語意邊（raw/courses）

| 邊 | 方向 | 數量 |
|----|------|------|
| `TAUGHT_BY` | Course → Instructor | 878 |
| `IN_DOMAIN` | Course → Domain | 597 |
| `DEVELOPS` | Course → Competency | 4,099 |

---

## 四、Slot 節點說明

Slot 是「從 N 個等效課程中選 1 門」的選課規則節點，用於：

1. **等效課程群**（原 `same_as` 欄位）：例如「地球系統科學概論」在大氣系/地科系/太空系各有一個課號，三者等效，用 Slot 包覆，學生選其中一門即可。

2. **統計學程 7選3 結構**：每個 slot 代表一個課程類別，類別內有多個等效課號可選。

```
ElectiveGroup(7選3)
  └─[HAS_SLOT]─> Slot(機率與統計, select=1)
                   ├─[OFFERS_ELECTIVE]─> Course(MA2011 統計學)
                   ├─[OFFERS_ELECTIVE]─> Course(MA2022 機率與統計)
                   └─[OFFERS_ELECTIVE]─> ... (共 20 個等效課號)
  └─[HAS_SLOT]─> Slot(線性代數, select=1)
                   └─...
```

對比一般 ElectiveGroup（無 Slot）：
```
ElectiveGroup(選修群)
  ├─[OFFERS_ELECTIVE]─> Course(CE3001)
  ├─[OFFERS_ELECTIVE]─> Course(CE3002)
  └─...
```

---

## 五、課號對齊策略

課號為唯一識別鍵（去除班別後綴 `-A`、`-*` 等）。

```
CE2002-A  →  CE2002
MA1003-*  →  MA1003
```

**對齊規則（唯一）：課號完全命中 raw → 使用完整 Course 節點；否則建 stub。**

不做課名補救，不建立 MAPS_TO 邊。

| 情況 | 處理方式 |
|------|---------|
| 課號在 raw | Course 節點含 dept/college/instructor/domain/competency |
| 課號在 scraped_missing | 同上（補爬資料視同 raw） |
| 課號不在 raw | stub Course 節點，`source=cp_only` 或 `curriculum_only` |

---

## 六、建圖步驟

腳本：`scripts/graph/build_knowledge_graph.py`

```
Phase 0: 載入 raw 課程
  ├── data/raw/courses/114_1/, 114_2/         → raw_by_code (ugrad)
  ├── data/raw/graduate_courses/114_1/, 114_2/ → raw_by_code (grad)
  └── data/raw/scraped_missing/courses.json   → raw_by_code (scraped)

Phase 1: curriculum_requirements 層
  ├── Step 1: University / College 節點
  ├── Step 2: Department / CollegeBachelorProgram 節點
  ├── Step 3: CurriculumPlan / GraduationRule 節點
  ├── Step 4: Course 節點 + REQUIRES 邊
  └── Step 5: ElectiveGroup + OFFERS_ELECTIVE 邊

Phase 2: 課程語意層（raw/courses）
  └── Step 6: Instructor / Domain / Competency 節點
              TAUGHT_BY / IN_DOMAIN / DEVELOPS 邊

Phase 3: credit_programs 層
  ├── Step 7: CreditProgram 節點 + HAS_CREDIT_PROGRAM 邊
  ├── Step 8: PROGRAM_REQUIRES 邊（一般必修）
  ├── Step 9: REQUIRES_SLOT 邊（等效必修 Slot）
  ├── Step 10: PROGRAM_OFFERS + ElectiveGroup 節點
  └── Step 11: HAS_SLOT + Slot 節點 + OFFERS_ELECTIVE 邊
```

---

## 七、建圖結果統計（2026-04-05）

| 指標 | 數值 |
|------|------|
| 總節點 | **3,070** |
| 總邊 | **8,760** |
| Course（有完整資料） | **1,340** |
| Course stub | **118** |
| Slot 節點 | **129** |
| CreditProgram | **42** |
| Instructor / Domain / Competency | 403 / 244 / 202 |

---

## 八、可回答的關鍵查詢（Cypher 範例）

```cypher
// 資工系大學四年必修清單
MATCH (d:Department {name:"資訊工程學系"})-[:HAS_CURRICULUM]->(cp:CurriculumPlan)
      -[:REQUIRES]->(c:Course)
RETURN c.code, c.name, c.credits ORDER BY c.code

// 某學分學程的選修課程（含等效群組）
MATCH (cp:CreditProgram {name:"「量子技術」學分學程"})
      -[:PROGRAM_OFFERS]->(eg:ElectiveGroup)
      -[:HAS_SLOT]->(slot:Slot)
      -[:OFFERS_ELECTIVE]->(c:Course)
RETURN slot.slot_name, c.code, c.name

// 某教師教哪些課
MATCH (c:Course)-[:TAUGHT_BY]->(i:Instructor {name:"某教授"})
RETURN c.code, c.name, c.credits

// 哪些課程同時是必修且在學分學程中
MATCH (c:Course)<-[:REQUIRES]-(:CurriculumPlan)
MATCH (c)<-[:OFFERS_ELECTIVE|PROGRAM_REQUIRES*1..2]-(:CreditProgram)
RETURN c.code, c.name

// stub 節點清單（課號不在 raw）
MATCH (c:Course) WHERE c.source <> "raw"
RETURN c.code, c.name, c.source
```

---

## 九、待處理事項

| 項目 | 狀態 |
|------|------|
| curriculum_requirements 建圖 | ✅ 完成 |
| raw/courses 語意層 | ✅ 完成 |
| credit_programs + Slot 層 | ✅ 完成 |
| same_as → Slot 轉換 | ✅ 完成（116筆） |
| 補爬缺失課程 | ✅ 完成（308筆） |
| REQUIRES_PROGRAM 邊（資電學士班→創意創業學程） | ✅ 完成 |
| PROGRAM_CHOICE 邊（地科系/地科院學士班三選一） | ✅ 完成 |
| PROGRAM_ELECTIVE 邊（企管系→ERP/BI學程） | ✅ 完成 |
| 前瞻半導體 2 門微課程（credits=0） | ✅ 建圖時略過 |
| TAICA 跨校課程（TC 前綴） | ✅ TC 課程在 NCU 選課系統以 TC 課號開設，爬蟲已抓到（15/16 有完整資料） |
