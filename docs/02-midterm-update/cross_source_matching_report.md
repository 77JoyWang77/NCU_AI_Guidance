# 三資料源課程比對報告

> 分析腳本：`scripts/analysis/analyze_cross_source_matching.py`
> 輸出 JSON：`data/processed/validation/cross_source_matching.json`
> 最後更新：2026-04-05

---

## 一、資料源概況

| 資料源 | 課號數 | 說明 |
|--------|--------|------|
| `raw/courses`（114_1 + 114_2） | **2,567** | 大學部實際開設課程 |
| `raw/graduate_courses`（114_1 + 114_2） | **928** | 研究所實際開設課程 |
| `raw/scraped_missing/courses.json` | **308**（大學 173 + 研 135） | 補爬課程（原不在 114 raw 中，另行搜尋最新學期） |
| `raw 合計` | **3,803** | 上三者合計，去重後 |
| `curriculum_requirements_114.json` | **458** | 各系所應修科目表列出的課程 |
| `credit_programs/*.json` | **998** | 全校學分學程課程清單 |

---

## 二、如何閱讀 cross_source_matching.json

JSON 共有以下頂層欄位：

### `summary`（統計摘要）

```json
{
  "raw_courses_total": 3803,
  "curriculum_total": 458,
  "credit_programs_total": 998,
  "curriculum_vs_raw": { ... },
  "credit_programs_vs_raw": { ... }
}
```

| `curriculum_vs_raw` 欄位 | 意義 |
|--------------------------|------|
| `code_match` / `code_match_pct` | 課號直接命中 raw 的數量與百分比 |
| `code_only_in_curriculum` | curriculum 有、raw 沒有的課號數 |
| `name_diff_count` | 課號吻合但課名有差的筆數（多為格式差異） |

| `credit_programs_vs_raw` 欄位 | 意義 |
|-------------------------------|------|
| `code_match` / `code_match_pct` | 課號直接命中 raw |
| `code_only_in_cp` | cp 有、raw 沒有的課號數（66 筆） |
| `cp_only_name_match_same_prefix` | 66 筆中：課名補救成功（同系所前綴） |
| `cp_only_name_match_any_prefix` | 66 筆中：課名補救成功（跨前綴） |
| `cp_only_non_standard_code` | 66 筆中：非標準課號（跨校，無對應） |
| `cp_only_name_no_match_grad` | 66 筆中：研究所標準課號仍找不到 |
| `cp_only_name_no_match_undergrad` | 66 筆中：大學部標準課號仍找不到 |
| `total_matchable` / `total_matchable_pct` | 課號比對 + 課名補救合計可對應數 |

---

### 各 list 欄位說明

#### `curriculum_name_diff`（課號吻合但課名有差）

每筆格式：
```json
{
  "code": "MA1003",
  "curriculum_name": "微積分上",
  "raw_name": "微積分",
  "source_dept": "資訊工程學系",
  "source_college": "資訊電機學院"
}
```
→ 來自哪個系所的應修科目表（`source_dept` / `source_college`）

#### `cp_name_diff`（credit_programs 課號吻合但課名有差）

```json
{
  "code": "BA3001",
  "cp_name": "管理學",
  "raw_name": "管理學概論",
  "source_program": "「企業管理」學分學程",
  "source_college": "管理學院"
}
```
→ 來自哪個學程（`source_program` / `source_college`）

#### `curriculum_only`（curriculum 有、raw 無）

```json
{
  "code": "EI3104",
  "name": "社會實踐專題下",
  "level": "undergrad",
  "name_match": "none",
  "name_match_codes": [],
  "source_dept": "資訊工程學系",
  "source_college": "資訊電機學院"
}
```

| `name_match` 值 | 意義 |
|----------------|------|
| `"same_prefix"` | 同系所前綴找到課名相同的課號 → `name_match_codes` 列出對應課號 |
| `"any_prefix"` | 跨前綴找到課名相同的課號 |
| `"none"` | 完全找不到 |

#### `cp_only_*` 系列（credit_programs 有、raw 無）

```json
{
  "code": "AC6001",
  "name": "ERP-管理控制系統",
  "level": "grad",
  "name_match": "none",
  "name_match_codes": [],
  "source_program": "「企業資源規劃」學分學程",
  "source_college": "管理學院",
  "source_group": "選修課程"
}
```

多了 `source_program`（學程名）和 `source_group`（選修群名），可追溯到是哪個學程的哪個選修群。

---

## 三、比對結果

### 3.1 curriculum_requirements vs raw

| 指標 | 數值 |
|------|------|
| 課號完全吻合 | **455 / 458（99.3%）** |
| curriculum 有、raw 無 | **3 筆** |
| 課號吻合但課名有差 | **11 筆**（全為上/下學期後綴或小幅修訂） |

**curriculum 有、raw 無的 3 筆**（課號不在 raw，但均有課名補救）：

| 課號 | curriculum 課名 | 課名補救結果 |
|------|----------------|------------|
| BA4002 | 策略管理 | ✅ 同前綴課名吻合 → BA5035（課號更新） |
| EE4044 | 畢業專題 | ✅ 跨前綴課名吻合 → EI4301 / ME4075 |
| EI3104 | 社會實踐專題下 | ✅ 同前綴課名吻合 → EI3103 |

---

### 3.2 credit_programs vs raw

| 指標 | 數值 |
|------|------|
| 課號直接匹配 | **932 / 998（93.4%）** |
| cp 有、raw 無 | **66 筆** |
| 合計可匹配（含課名補救） | **950 / 998（95.2%）** |

**66 筆缺失分類**：

| 類型 | 數量 | 說明 |
|------|------|------|
| 非標準格式課號（跨校） | **27** | DME/ICN/ICV/IEO/IME/IPT/PME 等聯大課號，本即不在 NCU 系統 |
| 課名補救成功（同前綴） | **11** | 課號不同但同系所同名，建圖走 MAPS_TO 邊 |
| 課名補救成功（跨前綴） | **7** | 跨系開課或通識，建圖走 MAPS_TO 邊 |
| 研究所仍缺失 | **9** | 補爬亦查無（LG0003~15 法律課、EE3510 等已刪課） |
| 大學部仍缺失 | **12** | 補爬亦查無（MT4011~18 實習課、BA4002、EI3104 等） |

---

## 四、課名補救說明

課號不在 raw 時，嘗試以正規化課名比對：

**正規化規則**：NFKC Unicode + 移除空格/括號/符號 + 移除上下學期後綴（上、下、Ⅰ、Ⅱ、I、II、(一)...）

| 補救方式 | 優先順序 | 範例 |
|---------|---------|------|
| 同系所前綴課名吻合 | 第一 | `BA4002 策略管理` → `BA5035 策略管理`（同 BA 前綴） |
| 跨前綴課名完全吻合 | 第二 | `CO2014 演算法` → `CE3005 演算法` |

---

## 五、建圖策略結論

| 情況 | 筆數 | 建圖處理 |
|------|------|---------|
| 課號直接命中 | 932 | 直接連結 Course 節點 |
| 課名補救成功 | 18 | `CurriculumCourse/CreditProgramCourse -[MAPS_TO]-> Course` |
| 非標準跨校課號 | 27 | 建立 Course stub，`source=special_program`（前瞻半導體/聯大等） |
| 研究所仍缺失 | 9 | 建立 Course stub，`source=cp_only`，`level=grad` |
| 大學部仍缺失 | 12 | 建立 Course stub，`source=cp_only`，`needs_review=true` |
| curriculum 仍缺失 | 3 | 建立 Course stub，`source=curriculum_only` |

> **結論：資料品質足以支撐知識圖譜建構。**
> curriculum 99.3%、credit_programs 95.2% 可對應至 raw 課程資料。
> 剩餘 5% 仍可建立 Course stub 節點，僅缺少 raw/courses 的詳細屬性（教師、領域、核心能力）。
