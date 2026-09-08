# Fig 6 — Coverage-Driven 證據迴圈（Research Graph 內部結構，main 分支）

## 論文定位

`research` agent（`backend/app/agents/pdf/research/`）是整個 PDF 對話系統中最有技術含量的一塊：
不是「問一次答一次」的傳統 RAG，而是一個 **coverage-driven 的多輪檢索迴圈**——
先決定「這次任務需要哪些證據槽」，再逐輪補齊，直到證據足夠才動筆寫摘要。

**本圖最重要的揭露**：LangGraph 實際只有 **3 個 node**（`scheduler → slot_executor → writer`），
Planner／Retriever／Reflector **並非獨立 graph node**，而是融合在 `slot_executor` 內部依序呼叫的
函式（`_run_single_slot`）。表面上像多階段管線，實際上是精簡的 3 節點狀態機 + 內嵌子流程。

---

## 圖表類型建議

State machine 圖。外層畫 3 個真實 LangGraph node（`scheduler ⇄ slot_executor → writer`），
`slot_executor` 內再展開一個小型子流程框（plan → retrieve → reflect → cross-slot routing →
void-slot 檢查）。建議用雙層框呈現「看起來像多階段，實際上是 3 節點 + 內嵌函式」的落差感。
每個 node 旁可標註其 `RetryPolicy`/`TimeoutPolicy` 具體數值（見下），呈現這是一個有明確容錯設計
的系統，而非天真的線性呼叫鏈。

---

## ResearchGraphState 關鍵欄位

| 欄位 | 說明 |
|---|---|
| `coverage_items` | 本次任務需要填的證據槽清單（見下方 4 槽預設，含 `use_hyde` 旗標） |
| `slot_status` | `dict[slot_id → SlotStatus]`：`FILLED / PARTIAL / NOT_FILLED / EXHAUSTED / NOT_FOUND / OMITTED` |
| `evidence` / `evidence_details` | 每槽已蒐集的證據；`evidence_details` 含 `filename/page/chunk_id/quote/interpretation` |
| `search_count` / `consecutive_no_new` | 搜尋預算控制 |
| `scheduled_slot` / `void_slot_attempts` | scheduler ↔ executor 之間的合約欄位 |
| `min_evidence_per_slot` | 品質門檻：每槽至少要幾筆證據才算「填滿」 |
| `messages` / `llm_call_count` / `final_answer` / `final_sources` | trace 與最終輸出 |

**狀態只能單向前進**：`NOT_FILLED(0) < PARTIAL(1) < EXHAUSTED(2) < FILLED(3)`（`reflector.py::_status_rank`）。

**`DEFAULT_SUMMARY_COVERAGE`**（4 個預設證據槽，皆 `use_hyde=False`）：
`research_motivation` / `research_methods` / `research_findings` / `research_limitations`

### Checkpoint 大小的明確工程紀律（`state.py`）

一整排 `_CAP_*` 常數，各自搭配自訂 LangGraph reducer，避免 Postgres checkpoint 隨對話輪數無限成長：

```
_CAP_EVIDENCE_PER_SLOT = 20        _CAP_SOURCES = 20
_CAP_EVIDENCE_DETAILS_PER_SLOT=12  _CAP_KEYWORDS = 80
_CAP_USED_QUERIES = 30             _CAP_QUERY_TERMS = 20
_CAP_CHUNK_KEYS = 200              _CAP_TRACE_ENTRIES = 30
_CAP_MESSAGES = 30
```

`planner_prompt_dict()` 另外對送進 LLM 的內容做更嚴格的裁切（如 `known_keywords[:20]`、
`used_queries[-15:]`、`evidence[slot][:8]`），checkpoint 上限與 prompt token 上限是兩層獨立控制。

---

## 圖拓樸（真實 LangGraph 結構）

```python
builder.add_node("scheduler", scheduler_node,
    retry_policy=RetryPolicy(max_attempts=2, initial_interval=1.0),
    timeout=TimeoutPolicy(run_timeout=90),
    error_handler=_scheduler_error_handler)
builder.add_node("slot_executor", slot_executor_node,
    retry_policy=RetryPolicy(max_attempts=2, initial_interval=2.0),
    timeout=TimeoutPolicy(run_timeout=600),
    error_handler=_slot_executor_error_handler)
builder.add_node("writer", writer_node,
    retry_policy=RetryPolicy(max_attempts=2, initial_interval=2.0),
    timeout=TimeoutPolicy(run_timeout=240),
    error_handler=_writer_error_handler)

START → scheduler → slot_executor → (should_continue: scheduler | writer) → writer → END
```

每個 node 的容錯策略都不同（timeout 90s／600s／240s，retry 間隔 1.0s／2.0s／2.0s），
且各自有**專屬的錯誤退化行為**，而非統一 catch-all：

| Node | 耗盡重試後的行為 |
|---|---|
| `_scheduler_error_handler` | 把所有尚未終結的必填 slot 強制標成 `OMITTED`，逼迫流程進 writer |
| `_slot_executor_error_handler` | 清空 `scheduled_slot`，`consecutive_no_new += 1`，讓下一輪重新排程 |
| `_writer_error_handler` | 直接呼叫 `_fallback_writeup`（證據堆疊 fallback），確保一定有輸出 |

---

## Node 1：`scheduler_node` — 決定下一輪處理哪一個 slot

```python
candidates = get_candidate_slots(state, rs, counts, _per_slot_cap(state))
if not candidates:
    return {"scheduled_slot": None}
decision = await decide_slot_ordering(llm, rs, candidates, void_slot_attempts)
scheduled_slot = ranked[0] if ranked else None   # 只取排序後第一名
```

每一輪只挑選「單一下一個 slot」，並非一次排出完整順序——這是刻意的「每輪重新評估」設計：
上一輪 `slot_executor` 完成後，狀態已經更新（可能因 cross-slot 路由意外填滿其他槽），
scheduler 用最新狀態重新排序，而非沿用舊排序表。

---

## Node 2：`slot_executor_node` — 隱藏的子流程（本圖核心）

`slot_executor_node` 呼叫 `_run_single_slot_with_retry`（asyncio 層級 retry，`max_retries=2`，
`timeout_seconds=180`，與 LangGraph node 本身的 `RetryPolicy` 是兩層獨立的容錯），
內部依序執行 4 步：

```
scheduled_slot
      │
      ▼
① plan_query_for_slot（planner.py，逾時 60s）
      │  LLM → PlannerDecision{thought, next_slot, display_intent,
      │         keyword_query, semantic_query, section_terms,
      │         use_hyde, expected_evidence, rationale}
      │  失敗（含 429 限流）→ 指數退避重試最多 3 次：sleep(5 * 2^attempt)
      │  仍失敗 → 決定性 fallback: build_slot_decision
      │  _repair_bundle：拒絕過於通用/重複的 query，重新從 fallback 填補
      ▼
② retrieve_evidence（retriever.py → run_search_report）
      │  硬停止：search-count 超額 / 連續無新結果 / 所有 chunk 已見過
      │  expand_queries：關鍵字 + 語意 + 章節詞擴展
      │  可選 HyDE（見下方精確觸發規則）
      ▼
③ reflect_results（reflector.py，逾時 60s）
      │  LLM → Reflection{quality, filled_item, updates:[CoverageUpdate],
      │         new_keywords, missing_gap, next_search_angle, ...}
      │  ★ cross-slot 證據路由（見下方精確算分公式）
      │  _filter_limitation_notes：排除「前人研究的限制」被誤植為本文限制
      │  apply_reflection：狀態只能單向前進合併
      ▼
④ void-slot 檢查（在 slot_executor_node 內，非 _run_single_slot 內）
      │  quality ∈ {NO_RESULTS, NOT_USEFUL} 且無新證據
      │  → void_slot_attempts[slot] += 1
      │  → 達 MAX_VOID_TOTAL(=4) 次：必填 slot → NOT_FOUND；選填 slot → OMITTED
      ▼
   回報給 scheduler，帶著更新後的 slot_status 重新排序
```

### HyDE 精確觸發規則（`planner.py::should_use_hyde`）

```python
def should_use_hyde(state, slot, requested=False):
    has_search_context = (
        state.search_count > 0
        or bool(state.next_search_angle)
        or any(state.evidence.get(item_id) for item_id in state.coverage_ids())
    )
    if not has_search_context:
        return False
    derived_slot = is_derived_hyde_slot(state, slot)      # 見下
    weak_retrieval = state.consecutive_no_new > 0 or state.slot_status.get(slot) == "PARTIAL"
    return derived_slot or (requested and weak_retrieval)
```

`is_derived_hyde_slot`：優先看 coverage item 上顯式的 `use_hyde` 旗標；否則比對關鍵字表：

```python
_DERIVED_HYDE_TERMS = ("有趣","辨識","導讀","興趣","量表","特色","亮點","吸引",
                       "notable","distinctive","interesting","student","hook")
```

也就是說：HyDE 只用在「衍生性/詮釋性」的槽位（例如「特色發現」「興趣切入」這類需要 LLM
自行推論後才好檢索的內容），對「研究方法」這種可直接在文件章節找到的事實性槽位則不啟用——
且**必須先有過至少一輪搜尋 context** 才允許使用（不會在第一輪搜尋就用 HyDE）。

### Cross-slot 證據路由：精確算分公式（`reflector.py::_slot_match_score`）

```python
def _slot_match_score(item, slot, text) -> int:
    terms = [item.label, *item.search_hints, *_SLOT_HINTS[slot]]
    score = sum(2 if term == item.label else 1 for term in terms if term in text)
    score += sum(1 for marker in ("動機","方法","成果","限制")
                 if marker in item.description and marker in text)
    return score
```

同一次檢索的 6 個 chunk 會拿去對**每一個尚未被本輪更新到的其他 slot**算分：
- 該 slot 的整體匹配分數 `≥ 3` 才會被納入候選
- 個別 chunk 對該 slot 的分數 `≥ 2` 才會被採用為證據
- 每個被「順便填到」的 slot 最多納 2 則證據，狀態設為 `PARTIAL`

一次搜尋、多槽受益——建議在圖上畫成一個搜尋框發散多支箭頭指向不同 coverage 方塊。

---

## `should_continue` 路由條件（`research_graph.py`）

轉往 `writer` 的三種情況（精確邏輯）：

1. `search_count >= _hard_max_searches(state)`（硬預算耗盡）
2. 所有必填 slot 已達終態（`FILLED/EXHAUSTED/NOT_FOUND/OMITTED`），且若設定了
   `min_evidence_per_slot`，還要滿足每個非 EXHAUSTED/NOT_FOUND/OMITTED 的必填 slot
   證據數 `≥ min_evidence_per_slot`
3. 「停滯」：`consecutive_no_new >= max_consecutive_no_new` **且**所有必填 slot 都已搜過至少一次

否則若已無候選 slot（都終結或都超過單槽搜尋上限）也直接轉 writer；不然回到 `scheduler`。

---

## Node 3：`writer_node` — 產出最終摘要

- `write_summary` → `ResearchWriteup{answer, sections, sources}`，以 `evidence_details`
  （含頁碼、引用句）為唯一依據
- 品質閘門 `_answer_ok`：`answer` 長度 ≥150 字元，且所有必填 coverage 的 label 都出現在
  answer 裡（**但 `NOT_FOUND`/`OMITTED` 狀態的必填 slot 會被排除在檢查之外**——因為這類槽位
  預期就是要寫「找不到」，不該被要求出現特定 label 文字）
- 不通過 → 帶著具體缺漏清單（例如「缺少以下必要段落：研究限制」或「答案長度不足」）重試一次
- 仍不通過 → `_fallback_writeup`（證據堆疊）

---

## 任務規劃：`task_planner.py` 的受眾自適應設計

`create_research_plan()` 先嘗試用 LLM 產生 coverage plan（`ResearchPlan{goal, coverage_items,
output_contract}`，每個 item 含 `use_hyde` 旗標，最多 6 個 item），失敗時走**規則式 fallback**，
而這個 fallback 已經內建了「受眾偵測」：

```python
def _summary_fallback_from_question(question: str) -> ResearchPlan:
    if _contains_any(question, ("高中生","導讀","興趣量表","學生","學習")):
        return _student_plan(question)      # 學生導向 plan
    if _contains_any(question, ("方法","步驟","流程","分析方法")) and not ...:
        return _method_plan(question)
    if _contains_any(question, ("成果","發現","結論","貢獻")) and not ...:
        return _result_plan(question)
    return _summary_plan(question)          # 預設 4 槽摘要
```

`_student_plan()` 的 5 個槽位裡，`distinctive_findings`（特色發現）與 `learning_hooks`
（興趣切入）**顯式設定 `use_hyde=True`**——也就是說，「高中生導讀」這個受眾設計不只在最終
輸出的措辭（例如 Step3/Step2 的展示文字），而是**在證據檢索策略本身**就已經考慮了「要找有趣、
有辨識度的內容」，這是比單純換一套 prompt 更深層的受眾適配設計。

---

## 呼叫端的兩種調參 profile

| 呼叫來源 | max_searches | max_searches_per_slot | max_consecutive_no_new |
|---|---|---|---|
| `router_agent.py::run_research_agent`（即時聊天路由到 `research`） | 14 | 3 | 2 |

同一套 research graph 被聊天路由以較保守的參數呼叫（單槽最多搜 3 次、總共最多 14 次），
控制單輪對話的延遲與成本上限。

---

## 運維面：graceful drain

```python
if runtime.drain_requested:
    logger.info("slot_executor skipping (drain requested: %s)", runtime.drain_reason)
    return {"scheduled_slot": None, "search_count": 0}
```

`slot_executor_node` 會檢查 LangGraph runtime 的 `drain_requested` 旗標，服務關閉時可以讓
research run 在 superstep 邊界優雅停止，而非被強制中斷在檢索或 LLM 呼叫中途。

---

## 設計決策補充說明（論文 Discussion 可引用）

- **為何「每輪只處理一個 slot」而非平行 fan-out**：避免多槽同時展開造成 context 爆炸，
  且每輪都能用最新證據重新排序優先序（cross-slot 路由可能讓某槽意外被填滿，下一輪立刻反映）
- **HyDE 觸發條件的分層設計**：「衍生性槽位」判斷（關鍵字/顯式旗標）與「弱檢索」判斷
  （`consecutive_no_new>0` 或 `PARTIAL`）是兩個獨立條件，前者處理「這類問題本來就需要推論」，
  後者處理「一般查詢真的搜不到東西時的補救」
- **`_student_plan` 把受眾適配做進檢索策略**：多數系統會在「輸出措辭」層做受眾客製化
  （例如換一套 prompt 語氣），這裡則是連「該搜尋什麼、要不要用 HyDE」都因應「高中生導讀」
  這個使用情境而改變，是更徹底的端到端受眾設計
- **三層獨立容錯**：asyncio-level retry（`_run_single_slot_with_retry`）、LangGraph node-level
  `RetryPolicy`/`TimeoutPolicy`、以及各 node 專屬的 `error_handler` 退化邏輯——三層各自處理不同
  層級的失敗模式（暫時性錯誤 vs 逾時 vs 徹底失敗後仍要交付可用結果）
