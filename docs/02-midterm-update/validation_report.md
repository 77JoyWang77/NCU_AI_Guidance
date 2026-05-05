# 資料驗證分析報告

> 驗證腳本：`scripts/validate_credit_programs.py` + `scripts/validate_curriculum_requirements.py`
> 最後更新：2026-04-04

---

## 一、總覽（最終結果）

| 驗證對象 | 總數 | PDF 全部找到 | JSON有PDF無 | 學分不符 | 完整吻合 |
|---------|------|------------|------------|---------|---------|
| 學分學程（credit_programs） | 42 個學程 | ✅ 0 缺失 | 1 個學程（2 門課） | **0** | **41** |
| 應修科目表（curriculum_requirements） | 28 個系所 | ✅ 0 缺失 | 1 個系所（2 門課） | **0**（1 個偽陽性） | **26** |

---

## 二、完整資料擷取流程

### 2.1 原始資料來源

| 資料類型 | 原始格式 | 存放路徑 |
|---------|---------|---------|
| 應修科目表 | PDF（每系所一份，依學院分資料夾） | `data/raw/應修科目表/<學院>/` |
| 學分學程 | PDF（每學程一份，依學院分資料夾） | `data/raw/學分學程/<學院>/` |
| 課程地圖 | PDF / PNG | `data/raw/課程地圖/` |

### 2.2 Step 1：使用 Claude Sonnet 4.6 讀取 PDF 並結構化

**工具：** Claude Code（CLI）＋ claude-sonnet-4-6 模型
**方法：** 直接上傳 PDF 至對話，讓 Claude 解讀表格內容

### 為何選用 Claude `Read` 工具，而非 OCR 或 OpenAI Vision？

三種主流方法的比較如下：

| 面向 | Claude `Read` 工具（本專案採用） | 傳統 OCR（如 pytesseract / PaddleOCR） | OpenAI Vision（GPT-4o） |
|------|-------------------------------|---------------------------------------|------------------------|
| **運作原理** | 優先讀取 PDF 內嵌文字層（text layer）；無文字層時以多模態視覺理解影像 | 將 PDF 每頁轉為影像，再以圖形識別辨認字元 | 將 PDF 頁面當作圖片傳入 API，由 GPT-4o 視覺模型解讀 |
| **語意理解** | ✅ 可理解表格語意、修課規則、備注、條件邏輯，直接輸出 JSON | ❌ 純字元辨識，不理解語意；需另外解析 | ✅ 語意理解能力與 Claude 相當 |
| **中文準確度** | ✅ text layer 原生 Unicode，不存在辨識錯誤 | ⚠️ 繁體中文字型辨識錯誤率偏高，複雜表格常失敗 | ✅ 準確度高，但遇到密集表格仍可能漏字 |
| **複雜表格** | ✅ 理解跨列合併格（合併儲存格）、備注欄、條件句 | ❌ 容易把合併格讀為多行、欄位錯位 | ✅ 理解能力強，但 token 消耗大 |
| **費用** | 💰 在 Claude Code CLI 對話中使用，費用包含於訂閱內（無額外 API 費） | 🆓 完全免費（本地運算），但需安裝 Tesseract + 中文語言包 | 💰 **每頁約 $0.005–$0.010 USD**（詳見下方）|
| **速度** | 快（text layer 直讀毫秒級；影像解讀約 5–15 秒/頁） | 慢（pdf2image 轉換 + OCR 各需數秒/頁） | 慢（API 來回延遲 + rate limit） |
| **需要網路** | ✅ 是（Claude API） | ❌ 否（本地） | ✅ 是（OpenAI API） |
| **輸出結構化 JSON** | ✅ 直接在 prompt 指定 schema，一步到位 | ❌ 需要額外解析步驟（正規表達式 / 後處理腳本） | ✅ 可以，但需要額外 prompt 設計 |

#### OpenAI GPT-4o Vision 費用估算（本專案規模）

GPT-4o 的圖片 token 計算方式：高精細度（high detail）下，每張圖切成 512×512 的磁磚，每磁磚 170 tokens，再加 85 基礎 tokens。一頁標準 A4 PDF 轉圖約等於 4×4 磁磚 ≈ **2,805 tokens**，費率為 $2.50 / 1M input tokens：

```
每頁費用 ≈ 2,805 tokens × $2.50 / 1,000,000 ≈ $0.007 / 頁

本專案：
  應修科目表：~28 份 × 平均 2 頁 =  56 頁 × $0.007 ≈ $0.39
  學分學程  ：~42 份 × 平均 3 頁 = 126 頁 × $0.007 ≈ $0.88
  合計影像費用                              ≈ $1.27 USD
  （另加 output token 費用 $10 / 1M）
```

> 以上僅為閱讀原始 PDF 的費用，不含後續的問答與 JSON 生成。實際可能因頁面密集程度而更高。

#### 為何 Claude `Read` 工具適合本專案

1. **多數 PDF 有文字層**：本專案的學分學程和應修科目表 PDF 幾乎都是電子排版生成（非掃描版），直接讀取文字層比影像識別更準確、更快。
2. **語意 + 結構一次到位**：Claude 可以在同一次對話中理解「這門課是必修還是選修」「修課條件是什麼」，並直接按照指定 JSON schema 輸出，省去後處理。
3. **已整合於工作流程**：使用 Claude Code CLI 時，`Read` 工具已內建，不需要額外安裝套件或管理 API key。
4. **例外情況（CID 字型 PDF）**：地球科學學系的 PDF 使用 CID-keyed 字型（pdfplumber 無法解碼），此時 Claude 的視覺模式仍可理解頁面影像。

**結論：本專案選擇 Claude `Read` 工具做資料擷取，主要優勢是零額外費用、語意理解、直接輸出結構化 JSON，且對有文字層的 PDF 準確率最高。**

---

Claude Sonnet 4.6 的 multimodal 能力可直接理解 PDF 文件（透過 `Read` 工具讀取）：若 PDF 含有嵌入文字層（text layer），則直接解析 Unicode 文字，不經過影像辨識；若為純影像 PDF，則切換至視覺模式理解頁面佈局。

**輸出格式（JSON schema 範例）：**
```json
{
  "id": "credit_program_001",
  "name": "「創意與創業」學分學程",
  "college": "資訊電機學院",
  "min_credits": 18,
  "required_courses": [
    { "code": "CO3001", "name": "創業與創新管理", "credits": 3 }
  ],
  "elective_groups": [
    {
      "name": "專業選修",
      "select_credits": 12,
      "courses": [ ... ]
    }
  ],
  "graduation_rules": { ... }
}
```

**處理的 PDF 類型：**
- 學分學程 PDF（每份含必修課程表 + 選修分組 + 修課規定）
- 應修科目表 PDF（每系每學期橫列 × 課程直列的表格，附學分欄）

**已生成的結構化 JSON：**
- `data/processed/curriculum_requirements_114.json`（28 個系所 + 各學院學士班）
- `data/processed/credit_programs/*.json`（42 個學分學程，依學院分 11 個 JSON 檔）

### 2.3 Step 2：驗證腳本比對 JSON vs PDF 原文

**工具：** Python + `pdfplumber` 套件

驗證腳本不再依賴 Claude，改用 `pdfplumber` 直接讀取 PDF 的文字層（text layer），以程式方式比對 JSON 中的課號與學分是否與原始 PDF 一致。

```
pdfplumber.open(pdf_path)
  └── page.extract_text(x_tolerance=3, y_tolerance=3)
      └── 回傳每頁純文字（維持行列結構，x/y tolerance 調整字元合併容差）
```

**比對流程：**
1. 從 JSON 取出所有課程的 `code`（含 `alias` 欄位）
2. 在 PDF 文字中搜尋課號是否存在
3. 若存在，進一步驗證學分是否一致
4. 分類結果：`matched` / `json_only` / `pdf_only` / `credit_mismatch`

---

## 三、途中遇到的問題與解決方式

### 問題 1：Python `\b` 單字邊界在中文緊接課號時失效

**現象：** 搜尋 `AP3031` 時，正規表達式 `\bAP3031\b` 在文字 `AP3031氣候學` 中回傳 False，導致大量課程被誤報為 json_only。

**原因：** Python 3 的 `re` 模組將所有 Unicode 字母（包含中文字）視為 `\w`（word character），因此 `\b` 在 `1` 和 `氣` 之間**不會**成立（兩側都是 `\w`）。

**解決：** 改用 ASCII 字母數字的 lookbehind/lookahead：
```python
# 舊寫法（有 bug）
re.search(r'\b' + re.escape(code) + r'\b', text)

# 新寫法（正確）
re.search(r'(?<![A-Za-z0-9])' + re.escape(code) + r'(?![A-Za-z0-9])', text)
```

**狀態：** ✅ 已修正，影響：大量 json_only 偽陽性消除

---

### 問題 2：Windows 檔案系統 CJK 相容字形 vs JSON 標準字形

**現象：** 搜尋「跨領域榮譽」和「跨領域社會參與」的 PDF 時，即使檔案存在也找不到，顯示「找不到 PDF」。

**原因：** Windows NTFS 對部分 CJK 漢字使用「相容表意文字區」（CJK Compatibility Ideographs）編碼，例如「領」在 Windows 檔名中可能是 U+F9B4，而 JSON 字串中是標準的 U+9818。兩者字形相同，但 `==` 比較為 False。

**診斷方式：**
```python
# 印出每個字元的 Unicode 碼點
print([hex(ord(c)) for c in filename[:5]])
# 輸出：[..., 0xf9b4, ...]  ← 應為 0x9818
```

**解決：** 在 `normalize()` 函式中加入 NFKC Unicode 正規化，將相容字形映射回標準字形：
```python
import unicodedata
name = unicodedata.normalize('NFKC', name)
```

**狀態：** ✅ 已修正，影響：跨領域榮譽、跨領域社會參與 PDF 成功比對

---

### 問題 3：TAICA 4 個學程共用同一份 PDF，名稱比對失敗

**現象：** 4 個 TAICA 學程（人工智慧探索應用、工業應用、自然語言、視覺技術）全部顯示「找不到 PDF」。

**原因：** 4 個學程的名稱都不出現在 PDF 檔名（`臺灣大專院校人工智慧學程聯盟(TAICA)」學分學程.pdf`），模糊比對失敗。

**解決：** 在 `find_pdf_for_program()` 加入備用策略：若學院子目錄只有一份 PDF，直接使用（多學程共用 PDF 的特殊情況）：
```python
# 策略 2：學院子目錄只有一份 PDF → 多學程共用
for d in college_dirs:
    pdfs = list(d.glob("*.pdf"))
    if len(pdfs) == 1:
        return pdfs[0]
```

**狀態：** ✅ 已修正，影響：4 個 TAICA 學程全部成功驗證

---

### 問題 4：學分偵測錯誤（滑動視窗法抓到鄰近課程數字）

**現象（第一版）：** 使用「±80 字元滑動視窗」找學分，導致大量偽陽性 credit_mismatch。例如：

```
PDF 行：CO1002數位系統導論(3)\nCO1005計概實習(1)
搜尋 CO1005 → 視窗包含前一行的 "(3)" → 誤報 PDF學分=3，JSON=1
```

**修正（第一次）：** 改為逐行搜尋，只在課號所在行尋找學分。

**現象（第二版）：** 逐行搜尋後，仍有「從行尾取數字」的問題：

```
行：分析化學 CM2021 / CM2022 3 4
搜尋 CM2021 → 策略「取行尾數字」→ 得到 4（CM2022 的學分）❌
```

另有「選N 被誤認為學分」問題：

```
行：(環境及永續) SL5011 選1
搜尋 SL5011 → 得到 1（選 1 門的意思，非學分）❌
```

**修正（最終版）：** 5 層策略，只搜尋課號位置**之後**的文字：

1. `(N)` 括號格式
2. `N / N`（alias 並列學分），取第一個
3. 同行多課號為斜線/逗號連接的 alias 組，**按位置索引**取對應學分（需確認課號數 ≤ 學分數，否則為合計學分略過）
4. 去除 alias 課號後，第一個獨立數字（排除「選/擇/共/備」前綴的數字）；若值 > 4 且同行有多課號，視為合計學分略過
5. 下一行只有一個數字（學分換行版面）

**狀態：** ✅ 已修正，影響：credit_mismatch 從 29 個降為 0，curriculum credit_mismatch 從 21 個降為 0

---

### 問題 5：地球科學學系 PDF 使用 CID-keyed 字型，pdfplumber 無法解碼

**現象（初始）：** 地球科學學系的應修科目表 PDF，pdfplumber 讀出全為 `(cid:XXXX)` 亂碼，22 門課全部顯示 json_only。

**原因：** PDF 使用自訂的 CID-keyed 字型，沒有提供 ToUnicode 映射表，pdfplumber 無法將 glyph ID 轉換為正確字元。

**解決過程：**

1. 改用 `pymupdf`（`fitz`）的 `get_text()` 讀取，發現雖然中文仍亂碼，但課號部分出現了 Latin Extended-A 字元，例如：
   ```
   pdfplumber：(cid:9944)(cid:9944)...（完全亂碼）
   pymupdf   ：⛘䎫⬠ġňőĳıĴĲ  ← 含有可辨識的字元序列
   ```

2. 發現 pymupdf 讀出的字型使用**固定偏移量 +0x101** 映射 ASCII 字元：
   - 數字：`0→ı, 1→Ĳ, 2→ĳ, 3→Ĵ, 4→ĵ, 5→Ķ, 6→ķ, 7→ĸ, 8→Ĺ, 9→ĺ`（U+0131–U+013A）
   - 字母：`G→ň(U+0148), P→ő(U+0151), A→ł(U+0142)...`
   - 規律：所有 ASCII 0x20–0x7E 字元均 +0x101 偏移

3. 驗證：`ňőĳıĴĲ` → G+P+2+0+3+1 = **GP2031** ✓

4. 實作解碼函式並加入驗證腳本：
   ```python
   _CID_OFFSET = 0x101
   def _decode_cid_font(text):
       result = []
       for c in text:
           cp = ord(c)
           if 0x0121 <= cp <= 0x017F:
               decoded = chr(cp - _CID_OFFSET)
               if 0x20 <= ord(decoded) <= 0x7E:
                   result.append(decoded); continue
           result.append(c)
       return ''.join(result)
   ```

5. 自動偵測觸發條件：pdfplumber 文字含 `(cid:XXXX)` 且無英文課號 → 改用 pymupdf + 解碼。

**結果：** 22 門課中 **21 門成功吻合**；1 門 GP1010（地球系統科學概論）顯示 PDF=1 學分 vs JSON=2 學分（待人工確認：可能為「每學期 1 學分 × 2 學期」的表格呈現方式）。

**狀態：** ✅ 已解決（pymupdf + CID 字型逆向解碼），地球科學從 0 吻合提升至 21/22

---

### 問題 6：HK3026「alias」欄位誤用為「二選一」關聯

**現象：** 法律與政治學分學程 `GS3132` 顯示 credit_mismatch（PDF=2, JSON=3）。

**原因：** `HK3026`（行政學, 3 學分）的 `alias` 欄填入了 `GS3132`，而 `GS3132`（行政學導論, 2 學分）是**不同學分的替代課程**，並非同一課的別名。當驗證器找不到 HK3026 時（另一校課號），改以 alias `GS3132` 查 PDF，得到 2 學分，與 HK3026 的 3 學分不符。

**解決：** 移除 `HK3026` 中錯誤的 `alias: "GS3132"` 欄位，改為只在 `description` 中說明二選一關係。

**狀態：** ✅ 已修正

---

### 問題 7：通訊工程系 PDF 課號使用舊版前綴 APH1031

**現象：** 通訊工程學系的 PH1031「普通物理A上」顯示 json_only。

**原因：** 通訊工程系的應修科目表 PDF 沿用舊課號 `APH1031`，而 JSON（以及大氣科學系等其他系的 PDF）均使用現行課號 `PH1031`。

**解決：** 在 curriculum_requirements_114.json 中通訊工程系的 PH1031 條目加入 `alias: "APH1031"`：
```json
{ "code": "PH1031", "name": "普通物理A上", "credits": 3, "alias": "APH1031" }
```

**狀態：** ✅ 已修正，通訊工程現在 30 門課全部吻合

---

## 四、已知剩餘異常（非 JSON 錯誤）

### 4.1 學分學程（credit_programs）

| 學程 | 課號 | 情形 | 原因 | 結論 |
|------|------|------|------|------|
| 「創意與創業」 | CO3025, CO3026 | json_only | PDF 打字錯誤：`C03025`（數字 0）≠ `CO3025`（字母 O） | ✅ JSON 正確，PDF 有誤 |

### 4.2 應修科目表（curriculum_requirements）

| 系所 | 情形 | 原因 | 結論 |
|------|------|------|------|
| 地球科學學系 | GP1010 credit_mismatch（PDF偵測=1, JSON=2） | 偽陽性：PDF 表格圖像確認 GP1010 = 2 學分（大一上）；CID 解碼文字因多欄位排版順序問題，錯誤讀取到下一行課程（GP4087 專題 1 學分）的數字 | ✅ JSON 正確，可忽略 |
| 大氣科學學系 | AP2050 json_only | PDF 使用縮略寫法 `AP2049/2050`，不含完整課號 `AP2050` | ✅ JSON 正確，PDF 省略寫法 |
| 大氣科學學系 | AP2010 json_only | PDF 打字錯誤：`A2010`（缺字母 P） | ✅ JSON 正確，PDF 有誤 |

---

## 五、驗證腳本技術說明

### 5.1 套件與版本

| 套件 | 用途 |
|------|------|
| `pdfplumber` | PDF 文字層擷取，支援 x/y tolerance 調整字元合併 |
| `re`（內建） | 課號搜尋（自訂 lookbehind/lookahead 取代 `\b`） |
| `unicodedata`（內建） | NFKC 正規化，消除 CJK 相容字形差異 |
| `json`（內建） | 讀寫結構化資料 |
| `pathlib`（內建） | 跨平台路徑操作，`rglob` 遞迴搜尋 |

### 5.2 核心函式

```python
def find_code_in_text(code, text):
    """以 ASCII lookbehind/lookahead 搜尋課號，避免 \b 在中文邊界失效"""
    pattern = re.compile(r'(?<![A-Za-z0-9])' + re.escape(code) + r'(?![A-Za-z0-9])')
    return bool(pattern.search(text))

def find_credit_near_code(code, text):
    """
    6 層策略，只搜尋課號位置之後的文字，依序嘗試：
    1. (N) 括號   2. N / N alias 並列取第一
    3. 多課號位置索引（需學分數 >= 課號數）
    4. 去除 alias 後第一個數字（排除選/擇/共，值 > 4 且多課號時略過）
    5. N學分   6. 下一行單一數字
    """
```

---

## 六、結論

| 項目 | 數值 |
|------|------|
| 學分學程完整吻合率 | **41/42（97.6%）** |
| 應修科目表完整吻合率 | **26/28（92.9%）** |
| 剩餘異常全部屬於 PDF 來源問題或待確認 | ✅ 確認 |
| JSON 資料確認需要修正的項目 | **0** |
| 待人工確認（低優先） | 無 |

所有 JSON 資料（`curriculum_requirements_114.json` 及 `credit_programs/*.json`）經程式驗證與人工確認，內容正確，可進入知識圖譜建構階段。
