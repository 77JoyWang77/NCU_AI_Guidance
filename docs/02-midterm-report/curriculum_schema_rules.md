# NCU 114 Curriculum JSON Schema Rules

Source file: `data/processed/curriculum_requirements_114.json`

---

## 1. Top-level Structure

```json
{
  "metadata": { ... },
  "colleges": [ ... ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `metadata.university` | string | 學校名稱，e.g. `"國立中央大學"` |
| `metadata.academic_year` | string | 學年度，e.g. `"114"` |
| `metadata.source` | string | 資料來源說明 |
| `metadata.generated` | string | 產生日期 |
| `colleges` | array | 各學院物件陣列 |

---

## 2. College（學院）物件

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✓ | 學院代碼，e.g. `"CLAS"` |
| `name` | string | ✓ | 學院名稱，e.g. `"文學院"` |
| `departments` | array | ✓ | 所屬學系陣列（可為空） |
| `college_bachelor_programs` | array | — | 學士班（書院制 / 跨域學士班）陣列 |
| `college_required_courses` | array | — | 院訂必修課程（Course 物件陣列） |
| `college_required_elective_groups` | array | — | 院訂必選選修群（ElectiveGroup 物件陣列） |
| `college_elective_courses` | array | — | 院訂必選課程（Course 物件陣列） |

---

## 3. Department（學系）物件

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✓ | 系所代碼，e.g. `"CHIN"` |
| `name` | string | ✓ | 系所名稱 |
| `program_type` | string | ✓ | 見下方 §4 |
| `min_credits` | number | ✓ | 最低畢業學分（通常 128） |
| `required_credits` | number | — | 系定必修學分小計 |
| `elective_credits` | number | — | 系定選修學分要求 |
| `total_structured_credits` | number | — | 結構化課程學分總計（驗算用） |
| `graduation_rules` | array | ✓ | GraduationRule 物件陣列 |
| `required_courses` | array | ✓ | 必修課程（Course 物件陣列） |
| `required_electives` | array | — | 必選課程（Course 物件陣列，算在必修） |
| `elective_groups` | array | — | 選修群（ElectiveGroup 物件陣列） |
| `core_elective_groups` | array | — | 核心選修群（ElectiveGroup 物件陣列） |
| `college_required_courses` | array | — | 院訂必修（掛在系層而非院層時） |
| `first_domain_electives` | array | — | 第一領域選修課程 |
| `groups` | array | — | 子群組（`dept_with_groups` 時使用，DeptGroup 物件陣列） |
| `tracks` | array | — | 組別/學程（DeptGroup 物件陣列，以 `HAS_TRACK` 關係連結） |
| `certifications` | array | — | 證照要求（字串陣列） |

---

## 4. program_type 值

| 值 | 說明 |
|----|------|
| `"traditional_dept"` | 一般學系（預設） |
| `"dept_with_groups"` | 系內分組，e.g. 生醫 A/B 組；子結構放在 `groups[]` |
| `"college_bachelor"` | 學士班（書院制），結構改放 `college_bachelor_programs[]` |

---

## 5. Course（課程）物件

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | string | ✓ | 課號，e.g. `"CL1003"` |
| `name` | string | ✓ | 課程名稱 |
| `credits` | number | ✓ | 學分數 |
| `alias` | string | — | 同等課號；單一：`"CE2003"`；多重以 `/` 分隔：`"CE2002/EE2007"` |
| `category` | string | — | 課程類別標籤，e.g. `"語言訓練類"`, `"專業學科類"` |
| `mandatory` | boolean | — | `true` 表示在選修群中為**必選**（不計入 select 名額）|

---

## 6. GraduationRule（修業規定）物件

每筆規定包含 `type`（必填）和 `description`（選填），其餘欄位依 type 而定。

### 6a. 學分類規定

| type | 額外欄位 | 說明 |
|------|---------|------|
| `credit_minimum` | `credits` | 最低畢業總學分 |
| `total_required` | `credits` | 必修（含通識）總學分 |
| `dept_required` | `credits` | 系定必修學分 |
| `common_required` | `credits` | 共同必修學分（跨院或全校） |
| `elective_minimum` | `credits` | 最低選修學分 |
| `dept_elective_min` | `credits` | 系選修最低學分 |
| `outside_elective_min` | `credits` | 系外選修最低學分 |
| `outside_elective_max` | `credits_max` | 系外選修可計入上限 |
| `dept_courses_min` | `credits` | 系所開課最低學分 |
| `star_elective_min` | `credits` | ★ 標記課程選修最低學分 |
| `triangle_elective_min` | `credits` | ▲ 標記課程選修最低學分 |
| `language_training_minimum` | `credits` | 語言訓練最低學分 |
| `professional_minimum` | `credits` | 專業學科最低學分 |
| `free_elective` | `credits` | 自由選修學分 |

### 6b. 課程類規定

| type | 額外欄位 | 說明 |
|------|---------|------|
| `general_education` | `domains_min` | 通識教育：最少需修領域數 |
| `foreign_language` | `credits` | 外語要求學分數 |
| `required_elective` | — | 特定必選課說明（無額外欄位，用 description） |
| `prerequisite` | — | 先修課程說明 |
| `substitution` | — | 課程替代說明 |
| `course_substitution` | — | 同上，另一種命名 |
| `classics_reading` | `books`, `double_major_books` | 經典閱讀：一般 / 雙主修本數要求 |
| `early_graduation` | — | 提前畢業條件說明 |

### 6c. 程式 / 證照類規定

| type | 額外欄位 | 說明 |
|------|---------|------|
| `cpe_certification` | — | CPE 程式能力認證要求 |
| `certification_required` | — | 其他證照要求 |

### 6d. 學程選擇類規定

| type | 額外欄位 | 說明 |
|------|---------|------|
| `program_choice` | `select` (number), `options` (string[]) | 三選一 / 二選一學程，`options` 列出可選學程名稱 |

### 6e. 備註類規定（僅 description）

| type | 說明 |
|------|------|
| `elective_note` | 選修一般備註 |
| `elective_fail_note` | 不及格選修學分處理政策 |
| `prerequisite_note` | 先修備註 |

---

## 7. ElectiveGroup（選修群）物件

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | 選修群名稱 / 說明 |
| `select` | number | 從群中選修**課程門數** |
| `select_credits` | number | 從群中選修**學分數**（與 `select` 擇一使用） |
| `category` | string | 類別標籤（可對應 course.category） |
| `description` | string | 補充說明（選修規則細節） |
| `select_type` | string | 特殊選法，e.g. `"programs"` 表示選的是學程而非個別課程 |
| `mandatory` | boolean | `true` 表示整群為必選（不計入選擇名額），罕見用法 |
| `courses` | array | Course 物件陣列（標準選法） |
| `option_a` | array | 選項 A 的 Course 物件陣列（二選一 / 三選一用） |
| `option_b` | array | 選項 B 的 Course 物件陣列 |
| `option_c` | array | 選項 C 的 Course 物件陣列 |

> **注意**：`option_a/b/c` 支援最多 3 個互斥選項。超過 3 個選項時，拆成多個 ElectiveGroup，各自帶 `category` 標籤區分。

---

## 8. DeptGroup（系內組別）物件

用於 `program_type: "dept_with_groups"` 的 `groups[]` 及 `tracks[]`。結構幾乎與 Department 相同，額外欄位：

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | 組別代碼 |
| `name` | string | 組別名稱 |
| `group_label` | string | 短標籤，e.g. `"A 組"` |
| `min_credits` | number | 組別最低學分 |
| `group_required_credits` | number | 組別必修學分小計（優先於 `required_credits`） |
| `required_courses` | array | 組內必修課程 |
| `cross_group_required` | array | 跨組必修課程 |
| `college_required_courses` | array | 院訂必修課程 |
| `common_required_courses` | array | 共同必修課程 |
| `first_domain_electives` | array | 第一領域選修課程 |
| `elective_groups` | array | 選修群 |
| `graduation_rules` | array | 修業規定 |
| `certifications` | array | 證照要求 |
| `groups` | array | 巢狀子群（DeptGroup 遞迴） |

---

## 9. CollegeBachelorProgram（學士班）物件

放在 `college.college_bachelor_programs[]`，代表書院制 / 跨域學士班。

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | 學士班代碼 |
| `name` | string | 學士班名稱 |
| `min_credits` | number | 最低畢業學分 |
| `graduation_rules` | array | 修業規定 |
| `required_courses` | array | 必修課程 |
| `foundation_courses` | array | 基礎課程 |
| `application_courses` | array | 應用課程 |
| `earth_system_courses` | array | 地球系統課程（地科院用） |
| `cross_domain_required` | array | 跨域必修課程 |
| `elective_groups` | array | 選修群 |
| `college_required_elective_groups` | array | 院訂必選群（跨院選修等） |
| `specialization_tracks` | array | 專業學程（SpecializationTrack 物件陣列） |
| `tracks` | array | 組別學程（DeptGroup 格式） |

---

## 10. SpecializationTrack（專業學程）物件

放在 `CollegeBachelorProgram.specialization_tracks[]`。

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | 學程代碼 |
| `name` | string | 學程名稱 |
| `min_credits` | number | 最低學分 |
| `domain_required` | number | 領域必修學分 |
| `first_domain_required` | number | 第一領域必修學分 |
| `first_domain_min` | number | 第一領域最低學分 |
| `required_courses` | array | 必修課程 |
| `elective_courses` | array | 選修課程 |
| `elective_groups` | array | 選修群 |
| `groups` | array | 子學程（SpecializationTrack 遞迴） |

---

## 11. Knowledge Graph 對應（build_knowledge_graph.py）

| JSON 物件 | 圖節點型別 | 關係 |
|-----------|-----------|------|
| 根 | `University` | — |
| College | `College` | `University → HAS_COLLEGE` |
| Department | `Department` | `College → HAS_DEPARTMENT` |
| DeptGroup (groups) | `DeptGroup` | `Department/DeptGroup → HAS_GROUP` |
| DeptGroup (tracks) | `DeptGroup` | `Department → HAS_TRACK` |
| CollegeBachelorProgram | `CollegeBachelorProgram` | `College → HAS_CBP` |
| SpecializationTrack | `SpecializationTrack` | `CBP → HAS_TRACK` |
| CurriculumPlan（每個 dept/group 各一） | `CurriculumPlan` | `→ HAS_CURRICULUM` |
| ElectiveGroup | `ElectiveGroup` | `CurriculumPlan → HAS_ELECTIVE_GROUP` |
| GraduationRule | `GraduationRule` | `→ GOVERNED_BY` |
| Course | `Course` | `→ REQUIRES` 或 `OFFERS_ELECTIVE` |
| Certification | `Certification` | `→ REQUIRES_CERTIFICATION` |
