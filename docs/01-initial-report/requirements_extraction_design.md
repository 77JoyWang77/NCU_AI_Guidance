# 應修科目表解析設計文件

> 記錄如何從 17 份 PDF 提取課程資料，整合進 Knowledge Graph 與 Vector DB。

---

## 一、現況分析

### PDF 文字可提取性

| 系所類型 | PyMuPDF 文字提取 | 備註 |
|---------|----------------|------|
| 一般系所（資管、光電等）| ✅ 課名+課號都有 | 表格欄位位置亂，但內容在 |
| 學士班（文學院、地科院等）| ✅ 有 | 多軌結構，課群混在一起 |
| 掃描圖片 PDF（資電學院學士班等）| ❌ 空輸出 | 需要 Vision API fallback |

**核心問題**：PDF 使用合併儲存格，PyMuPDF 抓到課名但失去欄位位置（學期欄的數字和課名是分開的兩塊文字）。

**解法：不用 pdfplumber/Vision，改用 PyMuPDF 抓文字 → GPT-4o text mode 整理**
- 比 Vision API 便宜 90%+
- 課名和課號都在文字中，LLM 能正確識別結構

---

## 二、提取流程

```
PDF
 │
 ▼ PyMuPDF (fitz) → 全頁 raw text（亂序但完整）
 │
 ├─ 有文字 ──▶ GPT-4o text mode → structured JSON
 │
 └─ 空輸出（掃描圖）──▶ Vision API fallback → structured JSON
                                   │
                                   ▼
                         data/processed/requirements_structured.json
```

---

## 三、輸出 JSON 格式

### 單軌型（e.g. 資訊管理學系）

```json
{
  "department": "資訊管理學系",
  "academic_year": 114,
  "table_type": "single_track",
  "graduation_requirements": {
    "total_credits": 128,
    "required_credits": 100,
    "notes": "選修只認定外系12學分（通識至多4學分）"
  },
  "courses": [
    {
      "name": "微積分",
      "code": "MA1005",
      "credits": 3,
      "category": "系訂必修",
      "year_level": 1,
      "semester": 1,
      "track": null
    }
  ],
  "rules_text": "必選課：初階程式設計、網頁程式設計、微積分。雙主修依本校辦理。"
}
```

`category` 可能值：`"共同必修"` / `"院訂必修"` / `"系訂必修"` / `"選修"`

### 多軌型（e.g. 文學院學士班）

```json
{
  "department": "文學院學士班",
  "academic_year": 114,
  "table_type": "multi_track",
  "graduation_requirements": {
    "total_credits": 128,
    "notes": "至少一主修課群修滿27學分（畢業證書加註專長領域）"
  },
  "track_rule": {
    "type": "choose_at_least_one",
    "min_credits_per_track": 27,
    "description": "至少有一主修課群修滿27學分"
  },
  "tracks": [
    "哲學思維與經典詮釋",
    "知識傳統與歷史應用",
    "藝術與視覺文化",
    "影像與敘事"
  ],
  "courses": [
    {
      "name": "哲學概論",
      "code": "PD1101",
      "credits": 3,
      "category": "基礎課程",
      "year_level": null,
      "semester": null,
      "track": null
    },
    {
      "name": "哲思方法",
      "code": "PD2203",
      "credits": 3,
      "category": "專業課程",
      "year_level": null,
      "semester": null,
      "track": "哲學思維與經典詮釋"
    }
  ],
  "rules_text": "至少一主修課群修滿27學分；跨課群科目名稱相同不得重複採計..."
}
```

**注意**：多軌型的 `year_level` / `semester` 通常為 null（PDF 未標示，學生自由選修）。

---

## 四、Knowledge Graph 設計

### 單軌型 → 簡單對應

```
Department ──REQUIRES──▶ Course
  邊屬性: category, year_level, semester, credits
```

### 多軌型 → 加入 Track 節點

```
Department ──HAS_TRACK──▶ Track ──TRACK_INCLUDES──▶ Course

Department 節點屬性：
  track_rule: "choose_at_least_one"
  track_min_credits: 27
```

共同必修/基礎課程（所有學生都要修）仍用 `REQUIRES` 邊（`track: null`）。

### 新增節點與邊類型

| 類型 | 說明 | 屬性 |
|------|------|------|
| `Track` 節點 | 主修課群 | `name`, `department`, `min_credits` |
| `HAS_TRACK` 邊 | Department → Track | - |
| `TRACK_INCLUDES` 邊 | Track → Course | `credits` |
| `REQUIRES` 邊（更新）| Department → Course | 加入 `category` 屬性 |

`rules_text` → **Vector DB**（不進 Graph，供語意搜尋）

---

## 五、可支援的查詢

整合後可新增回答：

| 問題 | 查詢方式 |
|------|---------|
| 資管系大一要修哪些課？ | REQUIRES + year_level=1 |
| 資管系畢業需要幾學分？ | Department 節點屬性 |
| 文學院學士班有哪些主修方向？ | HAS_TRACK |
| 哲學思維課群要修哪些課？ | HAS_TRACK + TRACK_INCLUDES |
| 資工系和資管系有哪些共同必修？ | REQUIRES 交集 |

---

## 六、Script 修改摘要

### `scripts/parse_requirements_table.py`

- 移除 `extract_with_pdfplumber()`
- 新增 `extract_text_with_pymupdf()`：用 fitz 逐頁抓文字
- 新增 `parse_with_llm(raw_text, dept_name)`：送 GPT-4o text mode 輸出 JSON
- Vision API 只用在空輸出的掃描圖 PDF

### `scripts/build_knowledge_graph.py`

- 加入 `Track` 節點
- 加入 `HAS_TRACK`、`TRACK_INCLUDES` 邊
- `REQUIRES` 邊加 `category` 屬性
- `rules_text` 寫入 Vector DB

---

## 七、缺失系所（13 個）

這些系所沒有應修科目表 PDF，目前只能從課程地圖間接推斷：

工學院（4）、生醫理工學院（1）、地球科學學院（2）、理學院（2）、資訊電機學院（3）、管理學院（1）

> 詳見 `data_integration_guide.md` § 3.3
