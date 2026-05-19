# get_depts_by_tech 工具分析與改善紀錄

> 撰寫日期：2026-05-18  
> 基於測試：`scripts/test_depts_by_tech.py`（37 題）

---

## 一、工具架構

### 查詢路徑（三層 Multi-hop）

```
輸入：tech_name（如「Python」）
  │
  ▼
【層 1】候選節點收集
  ├── 精確字串比對（name.lower() == tech_name.lower()，score=1.0）
  ├── ID 直查（tech::X / concept::X / field::X）
  └── Qdrant ncu_graph_nodes 向量搜尋（score ≥ 0.65，補充別名/縮寫）
  │
  ▼
【層 2】對每個候選節點，走反向邊找課程
  邊類型：TEACHES / COVERS / COVERS_FIELD / DEVELOPS
  過濾：node_type == "Course" AND name 不含 "[已停開]"
  │
  ▼
【層 3】對每門課程，走三層反向邊找系所
  Course ← REQUIRES / HAS_CURRICULUM ← CurriculumPlan ← Department
  is_required = (rel == "REQUIRES")  → 分必修 / 選修
  fallback：若無 CurriculumPlan，改用 course.dept 欄位（標為選修）
  │
  ▼
【輸出】
  {
    nodes: [
      {
        node_name, node_type, score,
        required_depts: [...],
        elective_depts: [...],
        courses: [{ name, dept, required_in, elective_in }]
      }
    ]
  }
```

### 工具函式格式化（tools.py:914–957，更新後）

```
■ 精確命中：Python（Technology）
  必修科系（3 個）：資訊工程學系、電機工程學系、機械工程學系
  選修科系（5 個）：化學工程與材料工程學系、地球科學學系...
  相關課程（8 門）：
    - 程式設計（資訊工程學系） → 必修：資訊工程學系
    - Python程式設計（機械工程學系） → 選修：機械工程學系

▲ 語意相近（0.82）：PYTHON（Technology）
  ...（語意擴展節點）
```

---

## 二、測試結果分析（37 題，2026-05-17）

### 命中率摘要

| 類別 | 題數 | 命中 | 說明 |
|------|------|------|------|
| 精確命中（熱門技術）| 8 | 8/8 | 全中 |
| 別名/英文縮寫 | 6 | 5/6 | Q12 MATLAB 改走 search_courses |
| 高中生反問型 | 6 | 4/6 | Q15 量子力學→search、Q20 財務工程→ppr |
| 必修 vs 選修 | 4 | 3/4 | Q22 線性代數→get_dept_courses×7（更精確） |
| 跨院廣泛概念 | 5 | 5/5 | 全中 |
| 冷門/稀疏技術 | 5 | 5/5 | 全中 |
| 多技術組合 | 3 | 3/3 | 全中 |
| **合計** | **37** | **33/37（89%）** | |

### Miss 分析

| 題號 | 問題 | 實際用工具 | 評估 |
|------|------|------------|------|
| Q12 MATLAB | Matlab 在哪些系有開課 | search_courses | 可接受，15 卡片結果好 |
| Q15 量子力學 | 讀哪個系接觸量子力學 | search_courses | 合理（課程清單比系所更有用） |
| Q20 財務工程 | 哪些系有財務工程課程 | ppr_explore（多 seed） | 合理，但 PPR 回傳 0 |
| Q22 線性代數 | 哪些系必修線性代數 | get_dept_courses × 7 | 結果更精確，7 張卡片 |

---

## 三、根因診斷

### 問題 1：0 cards 的根因（已修復）

**`llm_service._parse_courses_from_str`** 的 `get_depts_by_tech` 分支有邏輯缺陷：
```python
# 舊邏輯（有 bug）
in_courses = False
for line in text.splitlines():
    if '相關課程' in line:    # ← 從未觸發！工具輸出用「課程（X 門）：」
        in_courses = True
        continue
    if not in_courses:
        continue              # ← 所有課程行都被跳過
    ...
```

工具輸出的課程區段是 `課程（X 門）：`，而非 `相關課程`，導致 `in_courses` 永遠為 False，所有課程行都被略過 → 0 cards。

**修復**：移除 `in_courses` flag，直接用縮排+dash 的 regex 匹配課程行：
```python
for line in text.splitlines():
    m = re.match(r'\s{2,}-\s+(.+?)（(.+?)）', line)
    if m:
        name, dept = m.group(1).strip(), m.group(2).strip()
        ...
```

同時更新工具輸出格式，課程區段改用 `相關課程（X 門）：` 作標題（雙重保險）。

### 問題 2：節點大小寫重複（23 個衝突組，待處理）

`build_graph.py` 的 `enrich_nlp` 函式直接以 `item.strip()` 作節點 ID，不做大小寫正規化：
```python
tid = f"tech::{item.strip()}"  # "Python" 和 "PYTHON" 產生兩個獨立節點
```

結果：
- `tech::Python` 有 N 門課的 TEACHES 邊
- `tech::PYTHON` 有 M 門課的 TEACHES 邊
- 查詢時兩個節點都被找到，但邊集合分散，各自覆蓋率不完整

衝突清單（探索發現）：
```
Python/PYTHON, MATLAB/Matlab/MatLab/matlab, NumPy/Numpy/numpy,
Scikit-Learn/Scikit-learn/scikit-learn, Pandas/pandas, GitHub/Github,
Linux/LINUX, LabVIEW/LabView, SolidWorks/Solidworks/SOLIDWORKS,
LaTeX/LaTex, Simulink/SIMULINK, Stata/STATA 等 23 組
```

**待實作修復**：見「五、待辦事項」。

### 問題 3：LLM 模糊陳述（已修復）

原因：
1. 工具回傳「找不到」時 LLM 基於常識幻覺系所
2. 工具格式中 ⚠️ 警告置頂，使 LLM 對所有資料不確定 → 模糊表達
3. System prompt 未明確禁止「圖譜顯示有相關開課」類語句

修復：
1. 重組工具輸出格式：⚠️ 只出現在語意相近節點前
2. System prompt 新增明確規則：「必須直接引用必修/選修科系清單，嚴禁模糊語句」

### 問題 4：[已停開] 課程出現（已修復）

`graph_service.get_depts_by_tech` 遍歷反向 TEACHES/COVERS 邊時，未過濾已停開課程。

修復：在 `src_node` 確認為 Course 後立即加檢查：
```python
if "[已停開]" in src_node.get("name", ""):
    continue
```

---

## 四、本次修改清單

| 項目 | 檔案 | 說明 | 狀態 |
|------|------|------|------|
| C1 | tools.py:515-517 | Signal C [已停開] 過濾 | ✅ 已存在 |
| C2 | graph_service.py:721-722 | get_depts_by_tech [已停開] 過濾 | ✅ 已修 |
| D1 | tools.py:927-957 | 工具輸出格式重組（相關課程標題、分層顯示） | ✅ 已修 |
| D2 | llm_service.py:SYSTEM_PROMPT | 新增 get_depts_by_tech 回答規則 | ✅ 已修 |
| E | tools.py:257 | n=16 預設值 | ✅ 已存在 |
| F | tools.py:254,370,1426 | topic_tag 過濾參數與實作 | ✅ 已存在 |
| G1 | llm_service.py:stream_with_tools | 新增 tool_result SSE 事件 | ✅ 已修 |
| G2 | test_depts_by_tech.py | 捕捉 tool_result 事件並顯示於 MD 報告 | ✅ 已修 |
| H  | llm_service.py:_parse_courses_from_str | 修復 get_depts_by_tech regex bug（0 cards 根因） | ✅ 已修 |
| B1 | data/processed/nlp/nlp_tech_nodes.json | 正規化 23 組大小寫衝突（45 課 60 項） | ✅ 已修 |
| B2 | scripts/graph/build_graph.py:enrich_nlp | 加入 _tech_norm_map 防重複節點 | ✅ 已修 |
| B3 | — | 完整重建圖（Tech 節點 923→895） | ✅ 已執行 |
| B4 | — | Qdrant ncu_graph_nodes 刪除 28 孤立節點（25933→25905） | ✅ 已執行 |
| B5 | — | Qdrant ncu_courses_ug/grad 更新 48 筆 payload | ✅ 已執行 |
| I  | scripts/normalize_tech_names.py | 新建正規化腳本（可重複執行） | ✅ 新建 |

---

## 五、待辦事項

### B. 概念正規化（✅ 已完成，2026-05-18）

**目標**：將 `tech::Python` 與 `tech::PYTHON` 等 23 組重複節點合併。

**執行結果**：
1. ✅ 新建 `scripts/normalize_tech_names.py`：45 門課 60 項名稱已正規化並寫回 `nlp_tech_nodes.json`
2. ✅ 修改 `scripts/graph/build_graph.py` 的 `enrich_nlp()`：加入 `_tech_norm_map` 防止未來重複
3. ✅ 完整重建圖：Technology 節點從 923 → 895（少 28 個重複）
4. ✅ Qdrant `ncu_graph_nodes` 刪除 28 個孤立節點（25933 → 25905）
5. ✅ 更新 `ncu_courses_ug` / `ncu_courses_grad` 共 48 筆 course payload 的 languages/tools 欄位

**實際效果**：
- `tech::Python` 保留，`tech::PYTHON` 已消除 → Python 相關 TEACHES 邊全部集中到單一節點
- MATLAB、NumPy、scikit-learn、pandas 等 23 組衝突全數解決
- `get_depts_by_tech("Python")` 回傳更完整的系所清單（不再遺漏 PYTHON 節點的課程）

---

## 六、驗證方法

```bash
# 快速驗證 0 cards 修復（Q1 Python 應出現課程卡片）
python scripts/test_depts_by_tech.py --nos 1

# 驗證 [已停開] 過濾（Q26 IoT 不應出現 [已停開] 課程）
python scripts/test_depts_by_tech.py --nos 26

# 全量測試（確認整體命中率未下降）
python scripts/test_depts_by_tech.py
```

回答品質確認：
- Q1 Python 回答應列出「必修科系：XX、YY；選修科系：ZZ、WW」格式
- 不應出現「圖譜顯示有 Python 相關開課」等模糊陳述
- 工具回傳區塊（test report）應顯示「■ 精確命中：Python」格式文字
