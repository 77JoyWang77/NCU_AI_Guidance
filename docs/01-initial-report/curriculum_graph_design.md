# 應修科目表知識圖譜設計文件
# Curriculum Requirement Knowledge Graph Design

> 基於 `應修科目表_114/` 目錄下 PDF 資料所設計的知識圖譜擴充方案
> 本文件是 `knowledge_graph_design.md` 的補充，聚焦於**畢業路徑規劃層**

---

## 一、資料全貌

### 1.1 檔案結構

```
應修科目表_114/
├── 資訊電機學院/
│   ├── 資訊工程學系_114.pdf          ← 傳統科系
│   ├── 電機工程學系_114.pdf          ← 傳統科系
│   ├── 通訊工程學系_114.pdf          ← 傳統科系
│   ├── 資訊電機學院學士班_114.pdf    ← 學院學士班（主檔）
│   ├── 資訊電機學院學士班_通訊工程專長_114.pdf  ← 專長分流
│   ├── 資訊電機學院學士班_資訊工程專長_114.pdf  ← 專長分流
│   ├── 資訊電機學院學士班_電機工程專長_114.pdf  ← 專長分流
│   ├── 資訊電機學院學士班_網路工程專長_114.pdf  ← 專長分流
│   └── 資電學院各系等同課程對照表_114.pdf       ← 跨系等同課程
│
├── 地球科學學院/
│   ├── 地球科學學系_114.pdf
│   ├── 大氣科學學系_114.pdf
│   ├── 太空科學與工程學系_114.pdf
│   └── 地科院學士班_114.pdf
│
├── 文學院/
│   ├── 中國文學系_114.pdf
│   ├── 英美語文學系_114.pdf
│   ├── 法國語文學系_114.pdf
│   └── 文學院學士班_114.pdf
│
├── 理學院/
│   ├── 物理學系_114.pdf
│   ├── 化學學系_114.pdf
│   ├── 光電科學與工程學系_114.pdf
│   ├── 數學系_計算與資料科學組_114.pdf   ← 系內分組
│   ├── 數學系_數學科學組_114.pdf         ← 系內分組
│   ├── 理學院學士班_114.pdf
│   └── 理學院學士班_[六個領域專長]_114.pdf
│
├── 工學院/
│   ├── 土木工程學系_114.pdf
│   ├── 化學工程與材料工程學系_114.pdf
│   ├── 機械工程學系_先進材料與精密製造組_114.pdf  ← 系內分組
│   ├── 機械工程學系_光機電工程組_114.pdf
│   ├── 機械工程學系_設計與分析組_114.pdf
│   ├── 工學院學士班_114.pdf
│   └── 工學院學士班_[四個專長]_114.pdf
│
├── 管理學院/
│   ├── 企業管理學系_114.pdf
│   ├── 財務金融學系_114.pdf
│   ├── 經濟學系_114.pdf
│   └── 資訊管理學系_114.pdf
│
├── 生醫理工學院/
│   ├── 生命科學系_114.pdf
│   └── 生醫科學與工程學系_114.pdf
│
└── 客家學院/
    ├── 客家語文暨社會科學學系_社政組_114.pdf  ← 系內分組
    └── 客家語文暨社會科學學系_語文組_114.pdf
```

### 1.2 三種課程方案類型

| 類型 | 例子 | 特點 |
|------|------|------|
| **傳統科系** | 資訊工程學系、電機工程學系 | 單一必選修規定 |
| **學院學士班** | 資電院學士班、地科院學士班 | 共同核心 + 多個專長分流選一 |
| **系內分組** | 機械工程學系(3組)、數學系(2組)、客家學系(2組) | 系內按興趣分流 |

### 1.3 各學院應修科目表結構欄位

所有表格都包含：

```
科目（類別）| 課名及課號 | 學分數 | 第一學年 上/下 | 第二學年 上/下 | 第三學年 上/下 | 第四學年 上/下
```

---

## 二、新增節點類型

> 以下節點類型從 `knowledge_graph_design.md` 的現有設計**擴充**

### 2.1 節點總覽

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  [University]                                                               │
│       │ HAS_COLLEGE                                                         │
│  [College]──────────────────────────────────────────────────────────────── │
│       │ HAS_DEPT              │ HAS_BACHELOR_PROGRAM                        │
│  [Department]            [CollegeBachelorProgram]                           │
│       │ HAS_GROUP                  │ HAS_TRACK                              │
│  [DeptGroup]              [SpecializationTrack]                             │
│       │                           │                                         │
│       └───────────────────────────┘                                         │
│                        │ HAS_CURRICULUM                                      │
│                  [CurriculumPlan]                                            │
│                        │                                                     │
│          ┌─────────────┼─────────────────────┐                             │
│          ▼             ▼                     ▼                              │
│  [CourseRequirement] [ElectiveGroup]  [GraduationRule]                      │
│          │             │                                                     │
│          ▼             ▼                                                     │
│       [Course]       [Course]                                                │
│                                                                             │
│  跨系關係：                                                                  │
│  [Course]──[EQUIVALENT_TO]──[Course]                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 新增節點定義

#### `CollegeBachelorProgram`（學院學士班）
學院層級的跨系整合學士班（如資電院學士班、地科院學士班）

```json
{
  "id": "EECS_BS_114",
  "name": "資訊電機學院學士班",
  "college": "資訊電機學院",
  "academic_year": "114",
  "min_total_credits": 128,
  "description": "資電院跨系整合學士班，提供四個專長分流"
}
```

#### `DeptGroup`（系內分組）
同一科系內的課程組別（如機械工程學系下的三個組別）

```json
{
  "id": "ME_ADV_MAT_114",
  "name": "先進材料與精密製造組",
  "department": "機械工程學系",
  "academic_year": "114"
}
```

#### `CurriculumPlan`（課程方案）
某一科系/學程的完整畢業課程規劃

```json
{
  "id": "CSIE_CURRICULUM_114",
  "belongs_to": "資訊工程學系",
  "academic_year": "114",
  "entry_year": "114",
  "min_total_credits": 128,
  "version": "114學年度入學適用"
}
```

#### `SpecializationTrack`（專長分流）
學院學士班內的專長方向

```json
{
  "id": "EECS_CE_TRACK_114",
  "name": "通訊工程專長",
  "program": "資訊電機學院學士班",
  "college": "資訊電機學院"
}
```

#### `ElectiveGroup`（選修群組）
一組可選課程，學生需從中選 N 門或 N 學分

```json
{
  "id": "CS_SPECIALIZATION_GROUP_A",
  "name": "資訊工程系選修A群",
  "min_courses": 3,
  "min_credits": 9,
  "note": "從以下課程中選修至少3門"
}
```

#### `GraduationRule`（畢業規定）
科系的畢業學分與資格要求

```json
{
  "id": "CSIE_GRAD_RULE_114",
  "min_total_credits": 128,
  "min_common_required": 25,
  "min_college_required": 0,
  "min_dept_required": 58,
  "min_dept_elective": 9,
  "max_external_credits": 21,
  "special_requirements": [
    "程式能力檢定（須通過或修習指定課程）",
    "完成專題實驗 I/II"
  ]
}
```

---

## 三、新增關係類型（Edges）

### 3.1 機構結構關係

```cypher
// 學院 → 學院學士班
(College)-[:HAS_BACHELOR_PROGRAM]->(CollegeBachelorProgram)

// 科系 → 系內分組（僅系內分組型態）
(Department)-[:HAS_GROUP]->(DeptGroup)

// 學院學士班 → 專長分流
(CollegeBachelorProgram)-[:HAS_TRACK]->(SpecializationTrack)
```

### 3.2 課程方案關係

```cypher
// 科系 → 課程方案（傳統科系）
(Department)-[:HAS_CURRICULUM {entry_year: "114"}]->(CurriculumPlan)

// 系內分組 → 課程方案
(DeptGroup)-[:HAS_CURRICULUM {entry_year: "114"}]->(CurriculumPlan)

// 學院學士班 → 課程方案（基底）
(CollegeBachelorProgram)-[:HAS_CURRICULUM {type: "base"}]->(CurriculumPlan)

// 專長分流 → 課程方案（分流部分）
(SpecializationTrack)-[:HAS_CURRICULUM {type: "track"}]->(CurriculumPlan)

// 課程方案 → 畢業規定
(CurriculumPlan)-[:GOVERNED_BY]->(GraduationRule)
```

### 3.3 課程要求關係（核心）

#### `REQUIRES`（必修）
課程方案 → 課程，表示「此方案規定學生必須修習本課」

```cypher
(CurriculumPlan)-[:REQUIRES {
  category: "系訂必修",      // 共同必修 | 院訂必修 | 系訂必修
  recommended_year: 1,       // 建議修習年級 1-4
  recommended_semester: "上", // 上 | 下 | null（全年或不限）
  credits: 3,                 // 學分數
  is_core: true               // 是否為核心必修（vs 類別必修中任選）
}]->(Course)
```

**詳細屬性說明：**

| 屬性 | 型態 | 說明 | 範例 |
|------|------|------|------|
| `category` | string | 科目類別 | `"系訂必修"`, `"院訂必修"`, `"共同必修"` |
| `recommended_year` | int | 建議修習年級 | `1`, `2`, `3`, `4` |
| `recommended_semester` | string | 建議學期 | `"上"`, `"下"`, `null` |
| `credits` | int | 學分數 | `3` |
| `is_core` | bool | 是否絕對必修（vs 群組選一） | `true` |
| `sequence_in_year` | int | 同年級同學期內的排序建議 | `1`, `2` |
| `note` | string | 備註（如「需達50分以上才可修進階」） | |

#### `OFFERS_ELECTIVE`（選修提供）
課程方案 → 課程，表示「此方案將本課列為可選修課程」

```cypher
(CurriculumPlan)-[:OFFERS_ELECTIVE {
  category: "系訂選修",
  group_id: "GROUP_A",       // 選修群組 ID（若為分群選修）
  credits: 3
}]->(Course)
```

#### `CHOOSE_FROM`（選修群組 → 課程）
```cypher
(ElectiveGroup)-[:CHOOSE_FROM]->(Course)
```

#### `HAS_ELECTIVE_GROUP`（課程方案 → 選修群組）
```cypher
(CurriculumPlan)-[:HAS_ELECTIVE_GROUP {
  min_courses: 3,     // 至少選幾門
  min_credits: 9      // 至少選幾學分
}]->(ElectiveGroup)
```

### 3.4 跨系等同課程關係

```cypher
// 跨系等同課程（單向：A系認定B系的課等同A系的課）
(Course_A)-[:EQUIVALENT_TO {
  context_dept: "資訊工程學系",  // 在哪個系的脈絡下等同
  note: "資電院各系認定互抵"
}]->(Course_B)

// 雙向等同（如資電院各系相互認定）
(Course_A)-[:MUTUALLY_EQUIVALENT {
  scope: "資訊電機學院",          // 有效範圍
  academic_year: "114"
}]->(Course_B)
```

### 3.5 先後修關係（從應修表推斷）

```cypher
// 從「建議年級/學期」推斷先後順序
(Course_A)-[:SHOULD_PRECEDE {
  source: "curriculum_order",   // 來源：課程表排序推斷
  reason: "Year2Sem1 before Year2Sem2",
  confidence: 0.7
}]->(Course_B)

// 明確先修（從備註文字解析）
(Course_A)-[:PREREQUISITE_OF {
  source: "explicit_note",      // 來源：明確文字
  note: "需先修計算機概論",
  confidence: 0.95
}]->(Course_B)
```

### 3.6 畢業要求特殊關係

```cypher
// 特殊畢業資格要求（如語言認證、能力檢定）
(CurriculumPlan)-[:REQUIRES_CERTIFICATION {
  name: "法語鑑定文憑 DELF B1",
  type: "外部認證",
  mandatory: true
}]->(ExternalCertification)

// 通識課程類別要求（必選足夠學分）
(CurriculumPlan)-[:REQUIRES_CATEGORY_CREDITS {
  category: "通識核心",
  min_credits: 8,
  note: "需涵蓋指定領域"
}]->(GeneralEducationCategory)
```

---

## 四、各類型科系的圖譜建模詳解

### 4.1 資電院學士班（學院學士班型）

**特點：**
- 一個學院共同基底 + 四個專長分流，學生入學後選定一個
- 有跨系等同課程對照表
- 每個專長對應一個獨立的 CurriculumPlan

**圖譜結構：**
```
(資訊電機學院:College)
    ├──[HAS_DEPT]──>(資訊工程學系:Department)──[HAS_CURRICULUM]──>(CSIE_Curriculum:CurriculumPlan)
    ├──[HAS_DEPT]──>(電機工程學系:Department)──[HAS_CURRICULUM]──>(EE_Curriculum:CurriculumPlan)
    ├──[HAS_DEPT]──>(通訊工程學系:Department)──[HAS_CURRICULUM]──>(CE_Curriculum:CurriculumPlan)
    └──[HAS_BACHELOR_PROGRAM]──>(資電院學士班:CollegeBachelorProgram)
            ├──[HAS_CURRICULUM]──>(EECS_Base_Curriculum:CurriculumPlan)  // 共同必修部分
            └──[HAS_TRACK]──>(資訊工程專長:SpecializationTrack)──[HAS_CURRICULUM]──>(EECS_CS_Curriculum)
            └──[HAS_TRACK]──>(電機工程專長:SpecializationTrack)──[HAS_CURRICULUM]──>(EECS_EE_Curriculum)
            └──[HAS_TRACK]──>(通訊工程專長:SpecializationTrack)──[HAS_CURRICULUM]──>(EECS_CE_Curriculum)
            └──[HAS_TRACK]──>(網路工程專長:SpecializationTrack)──[HAS_CURRICULUM]──>(EECS_NE_Curriculum)
```

**關係屬性範例：**
```cypher
// 資電院學士班共同必修：微積分（大一上）
(EECS_Base_Curriculum)-[:REQUIRES {
  category: "院訂必修",
  recommended_year: 1,
  recommended_semester: "上",
  credits: 3,
  is_core: true
}]->(Course {code: "MA1003", name: "微積分"})

// 資訊工程專長：資料結構（大二上）
(EECS_CS_Curriculum)-[:REQUIRES {
  category: "專長必修",
  recommended_year: 2,
  recommended_semester: "上",
  credits: 3,
  is_core: true
}]->(Course {code: "CE2002", name: "資料結構"})

// 跨系等同課程
(Course {code: "CE2002", name: "資料結構"})-[:EQUIVALENT_TO {
  context_dept: "電機工程學系",
  scope: "資訊電機學院",
  academic_year: "114"
}]->(Course {code: "EE2301", name: "資料結構（電機系版）"})
```

**特殊規定節點：**
```cypher
(CSIE_GradRule:GraduationRule {
  min_total_credits: 128,
  min_dept_required: 58,
  min_dept_elective: 9,
  max_external_credits: 21,
  special_requirements: ["程式能力檢定：須通過或修習程式設計課程"]
})
```

---

### 4.2 地科院學士班（地科院型）

**特點：**
- 三個科系（地球科學、大氣科學、太空科學與工程）各有獨立課程規劃
- 地科院學士班是入學後不分系，後期分流
- 有明確的先修限制（如「應用數學需達微積分50分以上」）

**特殊先修限制建模：**
```cypher
// 明確分數限制型先修
(Course {code: "AP2007", name: "應用數學（一）"})-[:REQUIRES_PREREQUISITE {
  prerequisite_course: "MA1003",
  min_score: 50,
  note: "微積分（一）達50分以上",
  source: "explicit_curriculum_note",
  confidence: 1.0
}]->(Course {code: "MA1003", name: "微積分（一）"})
```

**大氣科學系應修科目方案（完整屬性）：**
```cypher
// 院訂必修：向量分析（大一下）
(AP_Curriculum)-[:REQUIRES {
  category: "院訂必修",
  recommended_year: 1,
  recommended_semester: "下",
  credits: 2,
  is_core: true,
  note: null
}]->(Course {code: "AP1006", name: "向量分析"})

// 跨領域選修群組（從四個領域擇一）
(AP_Curriculum)-[:HAS_ELECTIVE_GROUP {
  min_courses: 4,
  min_credits: 12,
  note: "從分析數學、地質、地資、水文與海洋四個領域中擇一"
}]->(AP_Domain_Group:ElectiveGroup {
  name: "大氣科學跨領域選修",
  choose_type: "domain",
  sub_groups: ["分析數學領域", "地質(七擇一)", "地資(四擇一)", "水文與海洋(四擇一)"]
})
```

---

### 4.3 文學院學士班（人文型）

**特點：**
- 外語認證要求（如法文系 DELF B1）
- 重視古籍、語言技能的分層培養
- 選修分「語言訓練類」和「專業學科類」兩個維度

**外語認證要求建模：**
```cypher
// 外部認證節點
(DELF_B1:ExternalCertification {
  name: "DELF B1",
  full_name: "法語鑑定文憑 Diplôme d'études en langue française B1",
  issuing_body: "法國教育部",
  level: "B1",
  language: "法語"
})

// 法文系畢業規定
(FR_GradRule:GraduationRule)-[:REQUIRES_CERTIFICATION {
  mandatory: true,
  note: "未取得者不得畢業，可在學期間多次考試",
  alternative: null
}]->(DELF_B1)
```

**英文系雙維度選修建模：**
```cypher
// 語言訓練類選修群組
(EL_LangGroup:ElectiveGroup {
  name: "語言訓練類",
  min_credits: 21,
  note: "以下課程全部必選"
})

// 專業學科類選修群組
(EL_ProfGroup:ElectiveGroup {
  name: "專業學科類",
  min_credits: 24,
  note: "以下課程全部必選"
})

// 英文系課程方案同時有兩個必選群組
(EL_Curriculum)-[:HAS_ELECTIVE_GROUP {type: "language_training"}]->(EL_LangGroup)
(EL_Curriculum)-[:HAS_ELECTIVE_GROUP {type: "professional_subject"}]->(EL_ProfGroup)
```

---

### 4.4 理學院學士班（科學多領域型）

**特點：**
- 六個領域專長可選：物理、化學、光電、生命科學、生醫、數學（含計算資料科學）
- 物理系有甲類（應用/實驗型）和乙類（研究/論文型）兩個分軌
- 跨領域學分要求（必須選非物理、非通識的課）

**物理系雙軌建模：**
```cypher
// 甲類（應用實驗型）
(PHY_Track_A:SpecializationTrack {
  name: "甲類",
  description: "應用與實驗導向",
  focus: "experimental_applied",
  thesis_required: false,
  competency_exam_required: true
})

// 乙類（研究論文型）
(PHY_Track_B:SpecializationTrack {
  name: "乙類",
  description: "研究與論文導向",
  focus: "research_thesis",
  thesis_required: true,
  oral_defense_required: true,
  committee_members_required: 2
})

(PHY_Curriculum)-[:HAS_TRACK]->(PHY_Track_A)
(PHY_Curriculum)-[:HAS_TRACK]->(PHY_Track_B)
```

**跨領域必修建模：**
```cypher
// 跨領域課程（不得來自物理系或通識）
(PHY_GradRule)-[:REQUIRES_CROSSFIELD {
  min_credits: 6,
  excluded_categories: ["物理系課程", "通識課程"],
  note: "培養跨領域視野，選修其他系所課程"
}]->()
```

---

### 4.5 工學院學士班（工程實務型）

**特點：**
- 四個專長：永續防災、能源材料、智慧機械、綠色科技
- 機械系有三個系內組別（先進材料、光機電、設計與分析）
- 強調實驗/實習課程

**工學院學士班建模：**
```cypher
(工學院學士班:CollegeBachelorProgram {
  id: "ENG_BS_114",
  name: "工學院學士班",
  college: "工學院",
  tracks: ["永續防災專長", "能源材料專長", "智慧機械專長", "綠色科技專長"]
})

// 機械系系內分組（非學院學士班，是傳統科系內的分組）
(機械工程學系:Department)-[:HAS_GROUP]->(先進材料與精密製造組:DeptGroup)
(機械工程學系:Department)-[:HAS_GROUP]->(光機電工程組:DeptGroup)
(機械工程學系:Department)-[:HAS_GROUP]->(設計與分析組:DeptGroup)
```

---

### 4.6 管理學院（選修學程型）

**特點：**
- 選修需來自特定「學習學程」（企業資源規劃 或 商業智慧與分析）
- 雙主修規定嚴格（需維持前20%）

**學習學程建模：**
```cypher
// 學習學程節點（跨多系的主題課程組合）
(ERP_Program:LearningProgram {
  name: "企業資源規劃學習學程",
  type: "designated_program",
  college: "管理學院",
  min_credits: 6
})

(BI_Program:LearningProgram {
  name: "商業智慧與分析學習學程",
  type: "designated_program",
  college: "管理學院",
  min_credits: 6
})

// 企管系畢業規定：選修中必有部分來自學習學程
(BA_GradRule)-[:REQUIRES_PROGRAM_ELECTIVE {
  min_credits: 6,
  choose_one_of: ["ERP_Program", "BI_Program"],
  note: "自選修中需至少6學分來自指定學習學程"
}]->()
```

---

### 4.7 客家學院（系內組別型）

**特點：**
- 同一科系（客家語文暨社會科學學系）分兩組：語文組、社政組
- 兩組的必修課程完全不同

```cypher
(客家語文暨社會科學學系:Department)-[:HAS_GROUP]->(語文組:DeptGroup)
(客家語文暨社會科學學系:Department)-[:HAS_GROUP]->(社政組:DeptGroup)

(語文組)-[:HAS_CURRICULUM]->(HKK_LIT_Curriculum:CurriculumPlan)
(社政組)-[:HAS_CURRICULUM]->(HKK_SOC_Curriculum:CurriculumPlan)
```

---

## 五、完整關係屬性規格

### 5.1 `REQUIRES` 關係屬性完整規格

```typescript
interface RequiresRelationship {
  // 分類
  category: "共同必修" | "院訂必修" | "系訂必修" | "專長必修" | "分組必修";

  // 建議修習時間
  recommended_year: 1 | 2 | 3 | 4;
  recommended_semester: "上" | "下" | null;

  // 學分
  credits: number;

  // 是否絕對必修（false = 從群組中選）
  is_core: boolean;

  // 若非絕對必修，所屬選修群組
  group_id?: string;

  // 備註
  note?: string;

  // 來源
  source: "curriculum_pdf";
  entry_year: "114";
}
```

### 5.2 `OFFERS_ELECTIVE` 關係屬性完整規格

```typescript
interface OffersElectiveRelationship {
  category: "系訂選修" | "跨領域選修" | "自由選修";

  // 若屬於某選修群組
  group_id?: string;
  credits: number;

  // 是否計入特定類別選修
  counts_toward?: string; // e.g., "語言訓練類"
}
```

### 5.3 `EQUIVALENT_TO` 關係屬性完整規格

```typescript
interface EquivalentToRelationship {
  // 等同的脈絡（在哪個科系認定）
  context_dept: string;

  // 有效範圍
  scope: "學院內" | "跨學院" | "全校";

  // 是否雙向
  bidirectional: boolean;

  // 有效學年
  academic_year: string;

  // 備註
  note?: string;
}
```

### 5.4 `HAS_ELECTIVE_GROUP` 關係屬性完整規格

```typescript
interface HasElectiveGroupRelationship {
  // 最低選修數量要求
  min_courses?: number;
  min_credits: number;

  // 選修類型
  type: "free_choice" | "choose_n_from_group" | "domain_choose_one" | "mandatory_list";

  // 備註
  note?: string;
}
```

---

## 六、GraduationRule 詳細設計

### 6.1 標準畢業規定屬性

```typescript
interface GraduationRule {
  id: string;

  // 學分要求
  min_total_credits: 128; // 全校統一
  min_common_required_credits: number;   // 共同必修（~25）
  min_college_required_credits: number;  // 院訂必修
  min_dept_required_credits: number;     // 系訂必修
  min_dept_elective_credits: number;     // 系訂選修

  // 外系課程限制
  max_external_credits: number;         // 外系課程上限（通常12-21）
  min_internal_credits: number;         // 必須在本系修的最低學分

  // 進階修業規定
  min_credits_per_semester?: number;    // 每學期最低修習學分（防止被退學）
  max_credits_per_semester?: number;    // 每學期最高修習學分

  // 特殊資格要求（array of string descriptions）
  special_requirements: string[];

  // 雙主修/輔系申請條件
  dual_major_requirement?: {
    min_gpa?: number;
    min_rank_percentile?: number;        // 如「前20%」= 0.20
    note?: string;
  };

  // 提前畢業條件
  early_graduation?: {
    min_score: number;                   // 通常75分以上
    note?: string;
  };
}
```

### 6.2 各學院典型畢業規定比較

| 學院/科系 | 總學分 | 系訂必修 | 系訂選修 | 外系上限 | 特殊要求 |
|-----------|--------|---------|---------|---------|---------|
| 資訊工程學系 | 128 | 58 | 9 | 21 | 程式能力檢定 |
| 電機工程學系 | 128 | ~60 | 12 | 21 | 實驗課程 |
| 地球科學學系 | 128 | ~70 | 9 | 12 | 跨域選修 |
| 大氣科學學系 | 128 | 79 | 0 | 12 | 無 |
| 太空科學與工程 | 128 | 75 | 16 | 12 | 無 |
| 物理學系 | 128 | 58+26 | 15/9 | 6（跨域必修） | 甲/乙分軌，乙類須論文口試 |
| 中國文學系 | 128 | 73 | 32 | 無特別限制 | 點書2本 |
| 英美語文學系 | 128 | 78+ | 25+ | 無特別限制 | 無外部認證 |
| 法國語文學系 | 128 | 56+47 | 35 | 無特別限制 | DELF B1 認證 |
| 企業管理學系 | 128 | 97 | 14 | 無特別限制 | 雙主修需前20% |

---

## 七、整合既有課程資料與應修科目表

### 7.1 資料連結策略

既有課程資料（3316門課程）與應修科目表的連結關鍵：

```
應修科目表中的「課名及課號」 → 對應至既有課程資料的「課號」欄位
```

**注意事項：**
- 應修科目表的課號格式：`CE1001`
- 既有課程資料的課號格式：`CE1001-*`（含班別）
- 連結時需忽略班別後綴

```cypher
// 連結範例
MATCH (curriculum:CurriculumPlan)-[r:REQUIRES {code: "CE1001"}]->(c:Course)
WHERE c.course_code STARTS WITH "CE1001"
```

### 7.2 資料豐富化

應修科目表可豐富既有課程節點的屬性：

```cypher
// 更新課程節點：新增「是否為某系必修」屬性
MATCH (c:Course {code: "CE2002"})
SET c.is_csie_required = true,
    c.csie_recommended_year = 2,
    c.csie_recommended_semester = "上"
```

更好的做法是保留在**關係屬性**上，而非修改節點：
```cypher
// 通過關係查詢課程的必修狀態
MATCH (plan:CurriculumPlan {dept: "資訊工程學系"})-[r:REQUIRES]->(c:Course)
RETURN c.name, r.recommended_year, r.recommended_semester, r.category
```

---

## 八、可以新增回答的查詢

### 8.1 畢業路徑規劃

```cypher
// Q: 資工系大一必修課是什麼？按學期排列
MATCH (plan:CurriculumPlan {dept: "資訊工程學系", entry_year: "114"})
MATCH (plan)-[r:REQUIRES]->(c:Course)
WHERE r.recommended_year = 1
RETURN r.recommended_semester, c.name, c.code, r.credits
ORDER BY r.recommended_semester, r.is_core DESC

// Q: 資電院學士班選資訊工程專長，大二要修哪些課？
MATCH (track:SpecializationTrack {name: "資訊工程專長"})
MATCH (base:CurriculumPlan)<-[:HAS_CURRICULUM]-(CollegeBachelorProgram)-[:HAS_TRACK]->(track)
MATCH (trackPlan:CurriculumPlan)<-[:HAS_CURRICULUM]-(track)
MATCH (base)-[r1:REQUIRES]->(c1:Course) WHERE r1.recommended_year = 2
MATCH (trackPlan)-[r2:REQUIRES]->(c2:Course) WHERE r2.recommended_year = 2
RETURN collect(distinct c1.name) + collect(distinct c2.name) as year2_courses

// Q: 我想讀物理系，乙類（研究型）需要完成哪些論文相關要求？
MATCH (track:SpecializationTrack {name: "乙類", dept: "物理學系"})
MATCH (track)-[:REQUIRES_CERTIFICATION|HAS_GRADUATION_RULE]->(rule)
MATCH (plan:CurriculumPlan)<-[:HAS_CURRICULUM]-(track)
MATCH (plan)-[r:REQUIRES]->(c:Course)
WHERE c.name CONTAINS "專題" OR c.name CONTAINS "論文"
RETURN c.name, c.code, r.recommended_year, r.recommended_semester
```

### 8.2 跨系課程認抵

```cypher
// Q: 電機系的「資料結構」能抵資工系的哪門課？
MATCH (c:Course {code: "EE2301"})-[r:EQUIVALENT_TO]->(c2:Course)
WHERE r.context_dept = "資訊工程學系"
RETURN c2.name, c2.code, r.note

// Q: 資電院學士班各系之間有哪些課互相認定？
MATCH (c1:Course)-[r:MUTUALLY_EQUIVALENT {scope: "資訊電機學院"}]->(c2:Course)
RETURN c1.code, c1.name, c2.code, c2.name, r.note
```

### 8.3 學習路徑推薦

```cypher
// Q: 資工系從大一到大四，建議的修課順序（按年級/學期）
MATCH (plan:CurriculumPlan {dept: "資訊工程學系"})-[r:REQUIRES]->(c:Course)
RETURN r.recommended_year as year,
       r.recommended_semester as semester,
       collect(c.name + "(" + toString(r.credits) + "學分)") as courses
ORDER BY year, semester

// Q: 要同時培養「AI 領域知識」又滿足資工系畢業要求，哪些課一舉兩得？
MATCH (plan:CurriculumPlan {dept: "資訊工程學系"})-[:REQUIRES]->(c:Course)
MATCH (c)-[:IN_DOMAIN]->(d:Domain)
WHERE d.name CONTAINS "人工智慧"
RETURN c.name, c.code, d.name
```

### 8.4 畢業要求檢查

```cypher
// Q: 法文系有哪些特殊畢業要求（非學分）？
MATCH (plan:CurriculumPlan {dept: "法國語文學系"})-[:GOVERNED_BY]->(rule:GraduationRule)
RETURN rule.special_requirements, rule.min_total_credits

MATCH (plan:CurriculumPlan {dept: "法國語文學系"})-[r:REQUIRES_CERTIFICATION]->(cert:ExternalCertification)
RETURN cert.name, r.mandatory, r.note
```

---

## 九、實作建議

### 9.1 解析 PDF 的策略

```python
# 使用 pdfplumber 或 camelot 解析表格
import pdfplumber

def parse_curriculum_pdf(pdf_path):
    """
    解析應修科目表 PDF，回傳結構化資料
    """
    with pdfplumber.open(pdf_path) as pdf:
        tables = []
        for page in pdf.pages:
            page_tables = page.extract_tables()
            tables.extend(page_tables)

    courses = []
    for table in tables:
        for row in table:
            if is_course_row(row):
                courses.append({
                    "category": extract_category(row),
                    "name": row[1],
                    "code": extract_code(row[1]),
                    "credits": int(row[2]) if row[2] else None,
                    "y1_sem1": row[3],
                    "y1_sem2": row[4],
                    "y2_sem1": row[5],
                    "y2_sem2": row[6],
                    "y3_sem1": row[7],
                    "y3_sem2": row[8],
                    "y4_sem1": row[9],
                    "y4_sem2": row[10],
                })
    return courses

def infer_recommended_year_semester(row_data):
    """
    從哪個年級/學期的格子有值，推斷建議修習時間
    返回 (year, semester)
    """
    semester_cols = [
        (1, "上"), (1, "下"),
        (2, "上"), (2, "下"),
        (3, "上"), (3, "下"),
        (4, "上"), (4, "下")
    ]
    for (year, sem), value in zip(semester_cols, row_data[3:11]):
        if value and value.strip():
            return year, sem
    return None, None
```

### 9.2 建圖優先順序

```
Phase 1（立刻可做）：
  1. 解析所有 PDF，建立結構化 JSON
  2. 建立 CurriculumPlan 節點（每個系一個或多個）
  3. 建立 REQUIRES 關係（含 recommended_year, recommended_semester）
  4. 建立 GraduationRule 節點

Phase 2（需要交叉比對）：
  5. 解析等同課程對照表，建立 EQUIVALENT_TO 關係
  6. 從備註文字解析先修關係
  7. 建立 SpecializationTrack 和學院學士班節點
  8. 建立 ElectiveGroup 和選修群組關係

Phase 3（豐富化）：
  9. 連結既有 3316 門課程資料與 CurriculumPlan
  10. 計算建議修課路徑（Learning Path）
  11. 建立跨學期版本關係
```

### 9.3 資料品質注意事項

| 問題 | 說明 | 處理方式 |
|------|------|---------|
| PDF 表格解析錯位 | pdfplumber 偶爾會合併錯誤 | 人工抽樣驗證 10% |
| 課號不一致 | 應修表用 CE1001，課程資料用 CE1001-A | 使用前綴匹配 |
| 學分格式多樣 | "3"、"3.0"、"3+0"（含實習） | 正規化為整數 |
| 同課名不同課號 | 不同系的同名課但課號不同 | 透過 EQUIVALENT_TO 連結 |
| 選修「擇一」的解析 | "下列選修一門"難以自動解析 | 建立 ElectiveGroup，手動驗證 |

---

## 十、最終知識圖譜架構總覽

```
University
    └── College (8個)
             ├── Department (傳統科系，各自 CurriculumPlan)
             │        └── DeptGroup (系內分組，各自 CurriculumPlan)
             └── CollegeBachelorProgram (學院學士班)
                      ├── CurriculumPlan (共同基底)
                      └── SpecializationTrack (專長分流)
                               └── CurriculumPlan (分流課程方案)

CurriculumPlan
    ├──[REQUIRES]──────> Course (必修，附年級/學期/類別)
    ├──[OFFERS_ELECTIVE]> Course (選修)
    ├──[HAS_ELECTIVE_GROUP]> ElectiveGroup ──> Course
    └──[GOVERNED_BY]──> GraduationRule
                              └──[REQUIRES_CERTIFICATION]> ExternalCertification

Course (既有3316門，連結至應修表)
    ├──[EQUIVALENT_TO]──> Course
    ├──[PREREQUISITE_OF]> Course
    ├──[TAUGHT_BY]──────> Instructor
    ├──[IN_DOMAIN]──────> Domain
    └──[DEVELOPS]───────> Competency
```

**新增節點數量估計：**

| 節點類型 | 預估數量 |
|---------|---------|
| `CurriculumPlan` | ~60（含分組、分流） |
| `CollegeBachelorProgram` | ~5（各院學士班） |
| `SpecializationTrack` | ~20（各院專長） |
| `DeptGroup` | ~8（系內分組） |
| `GraduationRule` | ~60 |
| `ElectiveGroup` | ~100-150 |
| `ExternalCertification` | ~5（DELF等） |
| `REQUIRES` 關係 | ~2000-3000 |
| `OFFERS_ELECTIVE` 關係 | ~3000-5000 |
| `EQUIVALENT_TO` 關係 | ~100-200 |
