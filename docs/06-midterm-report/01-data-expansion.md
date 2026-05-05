# 資料擴充報告

> 更新時間：2026-05-02

---

## 一、概述

期初報告的資料層僅使用中央大學選課系統的課程 JSON（3,630 門）。期中期間整合了四大新資料源，大幅豐富系統的語意深度：

| 資料源 | 機構 | 檔案 | 規模 |
|--------|------|------|------|
| 教師領域專長 | 大專校院校務資訊公開平臺（教育部） | `114_ulistteacher.csv` | 1,009 位教師，2,469 個專長詞彙 |
| 科系介紹 | Collego 大學選才與高中育才輔助系統 | `collego_ncu.json` | ~40 個系所，含學系特色、生涯進路 |
| 應修科目表 | 中央大學教務處 | `curriculum_requirements_114.json` | 28 個系所，458 門必修課 |
| 學分學程 | 中央大學課務資訊網 | `credit_programs/*.json` | 42 個學程，998 門課 |

---

## 二、教師領域專長（大專校院一覽表）

### 2.1 資料來源

- **機構**：教育部大專校院校務資訊公開平臺暨大專校院一覽表
- **網址**：https://udb.moe.edu.tw/
- **檔案**：`data/raw/114_ulistteacher.csv`

### 2.2 資料結構

| 欄位 | 範例 | 說明 |
|------|------|------|
| `系所名稱` | 資訊工程學系 | 開課系所（含研究所） |
| `教師名稱` | 陳○○ | 教師姓名 |
| `聘書職級` | 教授 / 副教授 / 助理教授 / 講師 | 職稱 |
| `專兼任` | 專任 / 兼任 | 聘用類型 |
| `教師專長` | 機器學習、深度學習、自然語言處理 | 逗號/頓號/分號分隔 |

### 2.3 前處理（normalize_teacher_specialties.py）

```python
SEP = re.compile(r"[,，、；;/]+")
specs = [s.strip() for s in SEP.split(spec_str) if s.strip()]
```

- 多種分隔符統一切割
- 輸出：`dept_professor_map.json`（300 KB）
  - 54 個系所
  - 1,009 位教師
  - 2,469 個獨立專長詞彙

### 2.4 用途

| 用途 | 說明 |
|------|------|
| **知識圖譜 Phase 2-a** | 全量 Instructor 節點建立 + `EXPERT_IN` 邊（2,629 條） |
| **NLP Agent 2** | 提供各系所教授領域詞彙表，用於課程→教授領域匹配 |
| **Qdrant ncu_teachers** | 教師文字嵌入（「教師名稱 + 系所 + 職稱 + 專長」） |
| **Agent 工具** | `search_teachers()`、`get_teacher_info()` |

---

## 三、科系介紹（Collego）

### 3.1 資料來源

- **機構**：Collego 大學選才與高中育才輔助系統
- **網址**：https://collego.edu.tw/
- **檔案**：`data/raw/collego_ncu.json`

### 3.2 資料結構

每個系所含以下欄位：

| 欄位 | 說明 |
|------|------|
| `dept_id` | 系所 ID |
| `dept_name` | 系所名稱 |
| `學系特色` | 簡述學系研究方向 |
| `學科意涵` | 學習內容與核心知識領域 |
| `生涯進路` | 畢業後就業/升學方向 |
| `能力特質` | 適合具備哪些特質的學生 |
| `學習方法` | 主要課程學習模式（list 或 str） |
| `課程資訊` | 代表性課程清單 |

### 3.3 文件組裝（Qdrant 索引）

組裝為語意搜尋文字：

```
資訊工程學系
學系特色：培養學生具備...(以下省略)
學科意涵：電腦科學、演算法...
生涯進路：軟體工程師、AI 研究員...
能力特質：邏輯思維、喜愛解題...
學習方法：程式設計；專題研究
課程資訊：資料結構、作業系統、機器學習...
```

### 3.4 用途

| 用途 | 說明 |
|------|------|
| **Qdrant ncu_departments** | 系所語意搜尋（高中生詢問「適合我的科系」） |
| **Agent 工具** | `get_dept_info()` |

---

## 四、應修科目表（中央大學教務處）

### 4.1 資料來源

- **機構**：中央大學教務處
- **網址**：https://pdc.adm.ncu.edu.tw/p/426-1019-7.php?Lang=zh-tw
- **主要輸出**：`data/processed/curriculum_requirements_114.json`
- **補充資料**：`data/processed/schedule_draft/`（建議修課學期）

### 4.2 擷取工具

使用 **Claude `Read` 工具**直接解析各系所 PDF（相比傳統 OCR 有顯著優勢）：

| 面向 | Claude Read | 傳統 OCR |
|------|------------|---------|
| 語意理解 | ✅ 完整理解表格結構 | ❌ 僅字元辨識 |
| 中文準確度 | ✅ 幾乎無誤 | ⚠️ 繁體易誤判 |
| 複雜表格 | ✅ 理解合併欄格 | ❌ 容易失敗 |
| 費用 | 💰 無額外 API 費 | 🆓 免費 |
| 結構化輸出 | ✅ 直接輸出 JSON schema | ❌ 需後處理 |

**處理過程遭遇的技術問題與解法**：

| 問題 | 解法 |
|------|------|
| Python `\b` 在中文失效 | 改用 ASCII lookbehind/lookahead |
| Windows CJK 相容字形 vs JSON 標準字形不吻合 | NFKC Unicode 正規化 |
| TAICA 4 個學程共用同一 PDF | 備用策略：學院子目錄只有一份 PDF 則直接使用 |
| 學分偵測錯誤（滑動視窗抓到鄰近課程） | 5 層策略，只搜尋課號位置之後的文字 |
| 地科系 PDF 使用 CID-keyed 字型 | pymupdf + CID 字型逆向解碼（偏移 +0x101） |

### 4.3 JSON Schema

**頂層結構**：
```json
{
  "metadata": {
    "university": "國立中央大學",
    "academic_year": "114",
    "source": "...",
    "generated": "..."
  },
  "colleges": [
    {
      "id": "college_electrical_engineering",
      "name": "資訊電機學院",
      "departments": [...],
      "college_bachelor_programs": [...]
    }
  ]
}
```

**系所（Department）物件關鍵欄位**：

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | string | 系所唯一識別碼 |
| `name` | string | 系所名稱 |
| `program_type` | string | `traditional_dept` / `dept_with_groups` / `college_bachelor` |
| `min_credits` | int | 最低畢業學分 |
| `required_courses` | list | 必修課程（含課號、課名、學分） |
| `elective_groups` | list | 選修群（含 select 門數、課程） |
| `graduation_rules` | list | 畢業規定（學分下限、CPE 認證等） |
| `groups` | list | 系內分組（e.g. 甲/乙組） |
| `tracks` | list | 專長分流（e.g. 各學士班方向） |

**GraduationRule 類別**：
- `credit_minimum`：最低學分數
- `general_education`：通識學分
- `foreign_language`：外語要求
- `cpe_certification`：CPE 程式能力認證
- `special_requirement`：特殊規定（如完成學程）
- `program_choice`：畢業擇一完成學程

### 4.4 建議修課學期（schedule_draft）

`data/processed/schedule_draft/{college}/{dept}.json` — 補充每門必修課的建議修課年級與學期：

```json
{
  "id": "dept_cs",
  "required_courses": [
    {"code": "CS1001", "when": "大一上", "verified": true},
    {"code": "CS2001", "when": "大二上~大二下", "verified": true}
  ]
}
```

`when` 解析為 `when_year_start`, `when_year_end`, `when_semesters` 供 Qdrant payload 儲存。

### 4.5 資料品質驗證

| 指標 | 數值 |
|------|------|
| 驗證系所數 | 28 |
| 完整吻合 | **26**（92.9%） |
| curriculum 課號直接命中 raw | **455 / 458**（99.3%） |
| curriculum 有、raw 無 | 3 筆（均有課名補救） |

---

## 五、學分學程（中央大學課務資訊網）

### 5.1 資料來源

- **機構**：中央大學課務資訊網
- **網址**：https://course.ncu.edu.tw/p/412-1014-2059.php?Lang=zh-tw
- **主要輸出**：`data/processed/credit_programs/*.json`（42 個學程）
- **補充說明**：`data/processed/program_descriptions.json`

### 5.2 資料結構

每個學程 JSON：

```json
{
  "id": "erp",
  "name": "企業資源規劃學分學程",
  "college": "管理學院",
  "min_credits": 15,
  "cross_school": false,
  "required_courses": [
    {"code": "BA3001", "name": "企業資源規劃", "credits": 3}
  ],
  "required_slots": [
    {
      "slot_id": "erp_module_1",
      "slot_name": "系統模組",
      "select": 1,
      "courses": [...]
    }
  ],
  "elective_groups": [
    {
      "name": "選修群A",
      "select": 2,
      "select_credits": 6,
      "courses": [...]
    }
  ]
}
```

### 5.3 資料品質驗證

| 指標 | 數值 |
|------|------|
| 驗證學程數 | 42 |
| 完整吻合 | **41**（97.6%） |
| credit_programs 課號直接命中 raw | **932 / 998**（93.4%） |
| 課名補救成功 | 18 筆 |
| 非標準跨校課號（DME/ICN 等） | 27 筆 |
| 最終可匹配率 | **950 / 998**（95.2%） |

### 5.4 66 筆缺失分類

| 類型 | 數量 | 知識圖譜處理 |
|------|------|------------|
| 非標準格式課號（跨校） | 27 | stub 節點，`source=special_program` |
| 課名補救成功（同前綴） | 11 | `MAPS_TO` 邊 |
| 課名補救成功（跨前綴） | 7 | `MAPS_TO` 邊 |
| 研究所仍缺失 | 9 | stub 節點，`source=cp_only` |
| 大學部仍缺失 | 12 | stub 節點，`source=cp_only`，`needs_review=true` |

---

## 六、三資料源課程比對總結

| 資料源 | 課號數 | 說明 |
|--------|--------|------|
| raw 大學部（114_1 + 114_2） | 2,567 | 實際開設，去重後 |
| raw 研究所（114_1 + 114_2） | 928 | 實際開設，去重後 |
| 補爬課程（scraped_missing） | 308 | 不在 raw 中的補爬 |
| **raw 合計** | **3,803** | 去重後 |
| curriculum（應修科目表） | 458 | 各系應修科目表列出 |
| credit_programs（學分學程） | 998 | 全校學分學程課程 |

### 建圖策略

| 情況 | 筆數 | 處理 |
|------|------|------|
| 課號直接命中 raw | 932 | 直接連結 Course 節點 |
| 課名補救成功 | 18 | `MAPS_TO` 邊 |
| 非標準跨校課號 | 27 | stub 節點 |
| 研究所仍缺失 | 9 | stub 節點 |
| 大學部仍缺失 | 12 | stub 節點，`needs_review=true` |

**結論**：資料品質足以支撐知識圖譜建構，95%+ 課程可直接對應。
