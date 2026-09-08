# Fig 5 — 摘要/題目資料的真實來源：離線 ETL 快照 + 語意轉用

## 論文定位

**這張圖的重點跟原本預期的不一樣**：`main` 分支上線的 PDF 對話系統（`backend/app/agents/pdf/`），
**沒有任何即時運作的「Step1-4 批次摘要/題目生成管線」**。使用者上傳 PDF 後，系統只做
parsing/chunking/indexing（供即時聊天檢索用），完全不會產生結構化摘要或興趣題目。

真正曾經跑過 Step1-4（研究動機/方法/成果/限制的多輪檢索摘要 + 3 題興趣量表，設計細節見另一個分支
`report-agent` 的 `backend/services/extraction.py`）的，是**一次性的離線流程**：某個環境／分支
跑過一次完整管線後，把結果匯出成一份快照 `data/raw/step2_step3_summaries.jsonl`，
再由一支 CLI 腳本 `scripts/data/import_step2_step3_summaries.py` 讀取這份快照，
把資料**寫死合併**進兩個靜態 JSON 檔案，供正式站台唯讀服務。

這是很好的論文 Discussion 素材：一套精緻的多輪 LLM 研究管線（Step1-4），
在正式產品化後**沒有被保留為線上服務**，而是被降維成「跑一次、凍結、當靜態資料用」——
且過程中 Step3 的原始語意（針對「這篇論文」的 3 題興趣量表）被**重新設計用途**，
變成橫跨多篇論文的「科系興趣量表」題庫。

---

## 圖表類型建議

左右兩欄對照：左欄「離線一次性 ETL」（虛線框，強調這不是常態運作的服務），
右欄「正式站台唯讀服務」。中間畫一條「資料寫死複製」的箭頭，
並在 Step3 → 題庫那一段特別標註「語意被重新詮釋」（可用顏色或圖示強調）。
建議搭配一張小圖說明「PDF 上傳後在 main 分支實際會發生什麼事」（只有 parsing/indexing，無摘要生成），
避免讀者誤以為正式站台在即時跑 LLM 摘要。

---

## 正式站台：PDF 文件的 DB schema 只有 4 個欄位

```python
class PdfDocument(PdfBase):
    __tablename__ = "pdf_documents"
    id = Column(Integer, primary_key=True)
    filename = Column(Text, nullable=False)
    abstract_text = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="ready")
```

沒有 `motivation`/`method`/`results`/`tags`/`interest_questions` 欄位——不是欄位被廢棄，
而是**從來沒有為批次摘要設計過對應的資料表**。`abstract_text` 只被當作聊天時的原始摘要文字
context 使用（`runner.py::_get_abstract`、`_memory_prompt` 注入），並非結構化摘要。

---

## 離線流程：`scripts/data/import_step2_step3_summaries.py`

```
data/raw/step2_step3_summaries.jsonl   ← 某環境跑過一次 Step1-4 後匯出的快照
（每列：{document, extraction, step2:{motivation,method,results,tags},
        step3:{intro, questions}}）
      │
      ├─────────────────────────────┐
      ▼                              ▼
apply_step2_to_projects()      build_assessment_questions()
（用 documentId 或檔名比對）      （用 documentId 或檔名比對）
      │                              │
      ▼                              ▼
data/processed/projects.json    data/processed/assessment_questions.json
Project.motivation/method/       重組成跨論文題庫（見下方語意轉用）
result/tags 直接覆寫
```

### `apply_step2_to_projects()`

依 `documentId` 或正規化後的檔名比對，把 `step2.motivation/method/results/tags`
直接覆寫進 `projects.json` 對應 `Project` 條目的 `motivation/method/result/tags` 欄位
（`backend/app/models/schemas.py::Project`，結構與 Step2 的 `CoreExtractionResponse`
幾乎一致，但**完全沒有字數限制驗證**——原本 Step2 的「≤200字」規則只存在於離線那次生成時的
prompt 裡，匯入時不重新檢查）。

### `build_assessment_questions()` ——語意被重新詮釋的關鍵步驟

```python
for mode, items in (
    ("grade1", balanced_order(matched, seed + 1, limit=40)),
    ("grade2", balanced_order(matched, seed + 2)),          # 無上限
    ("grade3", balanced_order(matched, seed + 3, limit=50)),
):
    for row, project in items:
        questions.append(make_assessment_item(row, project, mode, question_id))
```

- `balanced_order()`：先依 `department`（系所）分組，組間輪流取一筆（round-robin），
  組內用 `random.Random(seed)` 洗牌——目的是讓最終題庫**跨系所平均分布**，
  而不是某幾個系所的論文題目擠在一起
- 產出三種 `mode`（`grade1`/`grade2`/`grade3`，對應不同年級的量表長度），
  `grade1`/`grade3` 各自有上限（40／50 題），`grade2` 無上限
- 每筆題目輸出 `{id, mode, department, title, intro, questions, tags, sourceDocumentId, projectId}`

**Step3 原本的設計語意**是「針對這一篇論文，給學生 3 題興趣量表，判斷『你對這篇研究有沒有興趣』」。
匯入後，這些題目被**打散、按系所重新分組、跨論文抽樣組成題庫**，
變成「回答完一系列來自不同論文的題目，判斷你可能適合哪個科系」——
從「單篇論文的興趣探測」變成「跨論文的科系適性測驗」，服務對象從「這篇論文的讀者」
變成「還沒決定念哪個系的高中生」。

---

## 正式站台如何服務這些資料

- `GET /projects`、`GET /projects/{project_id}`（`backend/app/routes/projects.py`）：
  唯讀回傳 `projects.json` 裡的條目，含匯入進去的 `motivation/method/result/tags`
- `GET /assessment/questions?mode=...`、`POST /assessment/submit`（`backend/app/routes/assessment.py`）：
  唯讀回傳題庫，作答後依 `department_scores`/`tag_scores` 計分——這是**與單篇 PDF 完全解耦**的
  獨立產品功能，使用者作答時不會意識到這些題目其實各自來自不同論文的 Step3 產出

---

## PDF 上傳後，正式站台實際會做什麼

```
使用者上傳 PDF
      │
      ▼
Parsing + Chunking + Indexing
（供 Fig6 的 research/retrieval agent 即時檢索用）
      │
      ▼
PdfDocument 寫入（僅 filename/abstract_text/status）
      │
      ▼
── 沒有任何批次摘要/題目生成呼叫 ──
      │
      ▼
使用者若想要摘要/題目 → 只能透過即時聊天（Fig6/7/8 的 research / question 相關能力）
```

不存在 `job_service.py`、Celery 或 Redis worker 之類的背景任務系統在做 PDF 摘要——
整個 `backend/app/` 底下唯一跟「背景」沾邊的是 `pdf_llm_gate.py`（併發閘門，見 Fig8）
與 `chat_jobs.py`（純聊天串流的取消訊號追蹤），兩者都與批次摘要無關。

---

## 舊 CLI 腳本的痕跡（佐證「離線一次性」是一貫模式，非單一特例）

`scripts/extraction/projects_pdf/` 底下還留著更早期的嘗試：
- `2_generate_questions.py`：純樣板字串產生假的 motivation/method/result，不呼叫 LLM
- `3b_summarize_with_azure.py`：真的呼叫 Azure OpenAI 做摘要，但透過 CLI 手動執行
  （`--dry-run`/`--limit` 參數），直接寫入 `assessment_questions.json`

這些腳本與 `import_step2_step3_summaries.py` 共同說明一件事：這個專案裡，
「PDF 摘要/題目生成」**從頭到尾都被當成離線 CLI 資料前處理工作**，不是執行期服務——
`import_step2_step3_summaries.py` 只是這個模式裡最新、資料品質最好（因為上游是真正跑過
Step1-4 完整管線）的一版。

---

## 設計決策補充說明（論文 Discussion 可引用）

- **研究原型如何被產品化**：Step1-4（見 `report-agent` 分支設計）是一套工程上很講究的多輪
  coverage-driven 摘要管線，但正式站台選擇不把它保留成即時服務，而是「跑一次、凍結、當靜態
  資料」。這犧牲了「每篇論文摘要品質可被 Step4 品質閘門把關、可隨時重跑」的彈性，換取「零執行期
  LLM 成本、零背景任務維運負擔、回應時間可預測（純讀 JSON）」——對一個以「瀏覽既有論文清單」
  為主要互動模式的產品來說，這是合理的成本/彈性取捨
- **為何 Step3 的語意會被重新詮釋**：單篇論文的「你對這篇研究有沒有興趣」在產品上價值有限
  （使用者通常還沒讀那篇論文，無法回答），但「跨多篇論文的科系性向測驗」是一個更完整、
  更能直接導出「你適合什麼系」結論的產品功能——**同一批 LLM 產出的題目素材，被下游用途重新賦予了
  不同的產品意義**，這是資料重用（data repurposing）的具體案例
- **與 `report-agent` 分支的關係**：不建議把 Step1-4 的設計直接畫成「本系統的摘要生成流程」，
  因為它在 `main`（實際上線分支）並非執行期架構；比較誠實的呈現方式是把它畫成「資料的起源」，
  搭配這張圖說明它如何變成今天看到的靜態 JSON
