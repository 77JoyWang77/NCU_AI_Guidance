# Fig 8 — PDF Chat 完整請求生命週期（main 分支：配額 → 併發閘門 → 中途插話 → Middleware → 逐輪遙測）

## 論文定位

把 Fig7（路由決策）串起來，畫出「使用者送出一則訊息」到「收到回應」的完整時間序列。
`main` 分支的請求生命週期比單純的「路由 + middleware」複雜得多：進入路由之前，
還有**每日配額檢查**、**同執行緒重複請求偵測（含中途插話語意）**、**全域併發閘門**
三層前置關卡，結束後還有**逐輪成本/延遲遙測**寫入 DB。這張圖的價值在於呈現一個
「已經考慮過正式營運場景」的請求生命週期，而不只是「一個 agent 怎麼回答問題」。

---

## 圖表類型建議

UML 循序圖（Sequence Diagram），參與者：User、`/chat/stream` Route、
`pdf_quota_service`、`_stream_lock`（in-memory）、`pdf_llm_gate`、Router（Fig7）、
Middleware Stack、Memory Services（`pdf_agent_memory`）、DB（`PdfAgentMessage`）。
建議用時間軸標示 SSE 逐段輸出，並在配額/閘門/TTL 三個關卡各畫一個「提前返回」的分支路徑
（因為這三關任一失敗都會讓請求提早結束，不會進到路由）。

---

## 進入點

| Endpoint | 行為 |
|---|---|
| `POST /{project_id}/chat` | 阻塞式 JSON（`chat_with_project`），內部仍呼叫 `route_agent_stream` 但累積成單一回覆 |
| `POST /{project_id}/chat/stream` | SSE 逐 token（`chat_with_project_stream`），前端主要使用 |

兩者都在 `backend/app/routes/projects.py`，都是同步 request-scoped，不經過背景 worker queue
（PDF 摘要/題目在這個分支本來就不是即時服務，見 Fig5）。

---

## 請求進入路由之前：三道前置關卡

### 關卡 1 — 每日配額（`pdf_quota_service.check_and_reserve`）

```python
_quota_id = await check_and_reserve(user_id)   # 兩個 endpoint 一進來就呼叫
```

- 追蹤的是**請求次數**，不是 token 數：`pdf_agent_messages` 表當日筆數
- 預設 `PDF_CHAT_DAILY_LIMIT = 50`（環境變數可調）
- **DB 計數 + process 內 in-flight 計數**的預約制：`db_count + in_flight >= limit` 才拒絕，
  超過回 `HTTPException(429)`
- 匿名使用者以 `"anon:{anon_id}"` 為 key，前綴確保不會與真實 Firebase UID 撞名
- **文件明確承認的擴展限制**：這個原子性假設「只在單 Uvicorn worker（`WEB_CONCURRENCY=1`）下成立」，
  多 worker 部署需要改用 Postgres advisory lock——這是誠實記錄的已知技術債，適合當論文案例

### 關卡 2 — 同執行緒重複請求 / 中途插話（兩層獨立檢查，皆用 30 秒 TTL）

**第一層：in-memory 併發鎖**（在拿到 conversation 之前）

```python
lock_key = f"{project_id}:{user_id or anon_id or thread_id}"
if lock_key in _stream_lock:
    if request.thread_id == _stream_lock[lock_key]:
        steering.set(_active, request.message)   # 同一 thread 重送 → 視為中途插話
        return ack
    else:
        return drop                                # 不同 thread → 視為重複請求，直接丟棄
_stream_lock[lock_key] = thread_id
```

**第二層：DB 持久化時間戳**（拿到 conversation 之後，捕捉第一層鎖沒攔到的情況）

```python
def _is_within_ttl(stream_started_at, ttl_seconds=30) -> bool:
    return (datetime.now(timezone.utc) - stream_started_at).total_seconds() < ttl_seconds

if conv.stream_started_at and _is_within_ttl(conv.stream_started_at):
    steering.set(thread_id, request.message)
    return ack   # "已收到補充，將納入考量。"
```

兩層都會呼叫 `steering.set()` 並提早以 SSE 回一則 ack、釋放配額預約（`exit_reservation`，
因為插話不消耗當日配額額度）——**TTL 是 30 秒，不是分鐘級別**，反映這是設計給
「使用者在同一則回覆還在生成時，又追加補充說明」的短窗口情境，而非長時間離開後回來的情境。

### 關卡 3 — 全域併發閘門（`pdf_llm_gate`）

```python
MAX_CONCURRENT = 2
gate_acquired = await acquire_with_timeout(timeout=30.0)   # asyncio.Semaphore(2)
if not gate_acquired:
    return 503  # "服務目前繁忙，請稍後再試。"
```

全站同時最多 2 個 PDF agent 執行在跑，與使用者身分無關——process 層級的硬性背壓閥。
**SSE 版本有個體驗細節**：在等待這個閘門之前，會先送出 `{"session_id": thread_id}` 事件，
讓前端能在「排隊等候」的最長 30 秒內就顯示可用的取消按鈕，而不必等到真正開始處理才給使用者操作權。

```
使用者送出訊息
      │
      ▼
check_and_reserve()  ──失敗──► 429
      │成功
      ▼
_stream_lock 檢查    ──重複/插話──► ack / drop（釋放配額）
      │通過
      ▼
取得/建立 conversation
      │
      ▼
stream_started_at TTL(30s) 檢查  ──在窗口內──► ack（插話，釋放配額）
      │不在窗口內
      ▼
mark_stream(now) + chat_jobs.start()
      │
      ▼
yield {"session_id": ...}   ← 前端這時就能顯示取消鈕
      │
      ▼
acquire_with_timeout(30s)  ──逾時──► 503（釋放配額）
      │成功
      ▼
   進入 Router（Fig7）
```

---

## Router 執行期間：心跳與中斷處理

```python
pending = asyncio.create_task(aiter.__anext__())
while True:
    try:
        result = await asyncio.wait_for(asyncio.shield(pending), timeout=HEARTBEAT_INTERVAL)
    except asyncio.TimeoutError:
        # 逾時不代表失敗，只是還沒有新 token；趁機把 stage/agent_start 事件送給前端
        drain _meta_queue → yield {"type": "stage", ...} / {"type": "agent_start", ...}
```

用 `asyncio.shield` 包住真正等待下一個 chunk 的 task，逾時（心跳間隔）時不取消它，
只是先把累積在 `_meta_queue` 的階段性事件（例如「搜尋文件中」「產生研究整理」）送給前端，
讓 SSE 連線在長時間搜尋/生成過程中持續有心跳，同時不打斷底層真正在跑的 agent 呼叫。

---

## Middleware 堆疊（`runner.py::setup_checkpointer._make_agent`）

```python
middleware = [
    _memory_prompt,                                              # 動態注入記憶（見下）
    SummarizationMiddleware(model=mini_llm, trigger=("tokens", 8000), keep=("messages", 10)),
    ContextEditingMiddleware(edits=[ClearToolUsesEdit(trigger=20000, keep=3)]),
    _trim_messages,                                              # 硬上限 20 則，對齊 HumanMessage 開頭
    _track_model_cost,                                           # 累計進 _turn_cost_var
    ModelCallLimitMiddleware(run_limit=15, exit_behavior="end"),
    ModelRetryMiddleware(max_retries=2, retry_on=StructuredOutputValidationError, on_failure="continue"),
    ToolRetryMiddleware(max_retries=2, retry_on=(ConnectionError, TimeoutError), on_failure="return_message"),
]
if fallback_llm is not None:
    middleware.insert(6, ModelFallbackMiddleware(fallback_llm))  # 條件式插入，非固定順序
```

**沒有 `HumanInTheLoopMiddleware`**——這一層在 middleware 清單裡完全不存在（不是「已註冊但停用」，
是根本沒放進去）。但 `runner.py::_interrupts_from_chunk` 仍在解析串流 chunk 裡的 `__interrupt__`
事件，`chat_agent.stream` 也會把 `is_done=="interrupt"` 往上傳遞——代表如果真的要支援中斷，
機制必須來自**工具內部呼叫 LangGraph 的 `interrupt()`**，而非設定檔層級的 middleware 規則。

`_tool_agent`（主力模型 + `ModelFallbackMiddleware(mini_llm)` 保底）與 `_tool_agent_mini`
（直接用 mini 模型、無 fallback）是兩個預先建好的 agent 實例，依 `use_mini` 參數選用。

---

## `_memory_prompt` 展開：main 分支的記憶架構

```python
memory = await build_memory_context(agent_name, thread_id, user_id, query, document_id)
# 依 MEMORY_READ_POLICY[agent_name] 決定要不要查以下三種
```

| Agent | 讀 context_summary | 讀長期記憶 | 讀 user_profile | 寫 context_summary | 寫長期記憶 | 寫 user_profile |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `chat` | ✓ | ✓ | ✓ | | | |
| `retrieval` | ✓ | | | | | |
| `research` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

只有 `research` 會寫入任何記憶層；`chat`/`retrieval` 純讀取。**`chat` 雖然不寫，但讀取範圍
是三個 agent 裡最廣的**（連 `retrieval` 都讀不到的長期記憶與使用者畫像，`chat` 都讀得到）——
因為 `chat` 是「直接對使用者說話」的最終出口，最需要背景資訊做語氣與內容的個人化。

### 短期記憶：`context_summary`（決定性建構，兩種寫入路徑）

- `update_context_summary()`：`research` 專用，直接從 `AgentResult.coverage_result` 建構，
  **沒有額外 LLM 壓縮呼叫**——存 `{status, label, notes[:2]}` 精簡版證據
- `update_chat_context_summary()`：**main 分支新增**，`chat` 輪次也會寫一筆輕量版
  （只存 `question`/`answer_snippet`，`coverage: {}`），讓後續追問能參考到「上一輪 chat 說了什麼」，
  即使那一輪沒有任何 coverage 結果
- 兩者共用同一個 `findings` 陣列（上限 `MAX_FINDINGS=5`，新的覆蓋同問題的舊的）與同一組
  `_load_summary`/`_save_summary`，存在 `PdfConversation.context_summary`（JSON 欄位）

### 長期記憶：確認乾淨，沒有 Qdrant 遺留問題

```python
store = get_store()   # agents/pdf/runner.py，AsyncPostgresStore（Postgres + pgvector, dims=3072）
namespace = (user_id, "research_memories")
```

`pdf_memory_service.py`／`pdf_agent_memory.py`／`pdf_user_profile_service.py` 三個檔案裡
**完全沒有 Qdrant 相關程式碼**——與另一分支（`report-agent`）曾發現的「Qdrant collection
建立但實際走 Postgres」的死碼問題不同，這裡是乾淨的單一資料來源。
去重邏輯：同一份文件內，語意相似度 `≥0.92` 的問題不重複寫入（`store.asearch` 回傳的 cosine score）。

### 第三層：使用者畫像（`pdf_user_profile_service.py`）——main 分支獨有的記憶層

```python
namespace = (user_id, "user_profile")   # key = "profile"
```

只在 `research` agent 回答後、背景觸發一次 **mini-model LLM 呼叫**，把本輪問答萃取合併進既有畫像：

```json
{
  "preferred_language": "Traditional Chinese",
  "academic_background": "...(≤40字)",
  "topics_of_interest": ["...最多8個，去重"],
  "answer_style_preference": "詳細 / 簡潔 / 條列 / 不確定"
}
```

格式化後注入 `chat`/`research` 的 system message（`format_profile_for_injection`）。
匿名使用者（`user_id` 以 `"anon:"` 開頭）完全跳過這一層讀寫——個人化只服務登入使用者。

**沒有第四層文件快取**：另一分支的 `document_research_cache`（30 天 TTL 的文件級研究結果快取）
在這裡沒有對應實作，`research` 每次都重新跑完整的 coverage 迴圈（Fig6），不做結果重用。

---

## 收尾：逐輪成本/延遲遙測

```python
@dataclass
class _TurnCostAccumulator:
    input_tokens: int = 0
    output_tokens: int = 0
    router_input_tokens: int = 0    # 與 agent 本身的 token 分開累計
    router_output_tokens: int = 0
    agent_model: str = ""

_turn_cost_var: ContextVar[_TurnCostAccumulator | None] = ContextVar(...)
```

`_track_model_cost`（middleware，每次模型呼叫後執行）與 `_orchestrate()`（路由決策後）
都會把 token 用量累加進同一個透過 `ContextVar` 在整個請求生命週期共用的 accumulator。
請求結束時：

```python
_latency_ms = int((time.monotonic() - _wall_start) * 1000)
await _write_agent_message(
    thread_id=..., input_tokens=acc.input_tokens, output_tokens=acc.output_tokens,
    router_input_tokens=acc.router_input_tokens, router_output_tokens=acc.router_output_tokens,
    latency_ms=_latency_ms, model_name=acc.agent_model,
)
```

寫入 `PdfAgentMessage` 這張表（`input_tokens`/`output_tokens`/`router_input_tokens`/
`router_output_tokens`/`latency_ms`/`model_name` 皆為獨立欄位），並更新
`PdfConversation.last_agent_name`（供下一輪 `route_request` 的 `previous_agent_name` 使用）
與 `message_count`。這整套逐輪遙測資料，很可能就是 Monitor 頁面「PDF token/latency 入庫、
三種 model 費用分拆」功能的底層資料來源。

---

## `finally` 區塊：三道前置關卡的對稱釋放

無論成功、逾時或例外，都要對稱釋放：

```python
finally:
    if gate_acquired:
        get_gate().release()
    exit_reservation(_quota_id)
```

`_stream_lock` 的清除則發生在正常完成路徑或例外路徑各自的位置（避免鎖泄漏導致同一使用者
之後所有請求都被誤判為「重複」）。

---

## 設計決策補充說明（論文 Discussion 可引用）

- **三道前置關卡的分工**：配額關心「這個使用者今天用了多少次」，併發鎖關心「這個使用者/
  這個對話現在是否已經有一個請求在跑」，全域閘門關心「整個服務現在能不能再承接一個 LLM 密集
  請求」——三者維度正交（使用者 vs 對話 vs 服務），刻意分開檢查而非合併成一道
- **兩層 TTL/鎖檢查看似重複，實則互補**：in-memory 鎖檢查快、不需要查 DB，但只能防「同一
  lock_key 短時間內」的重複；DB 持久化時間戳檢查稍慢，但能在 in-memory 鎖因為某些邊界情況
  （例如鎖已被清除但 DB 時間戳還在窗口內）沒攔到時提供第二道防線
- **`context_summary` 不用 LLM 壓縮而用結構化資料直接建構**：`research` 走法沿用既有設計；
  `chat` 新增的輕量版本進一步證明這個原則被延伸套用到所有會寫記憶的路徑，而非只在最初設計的
  單一場景生效
- **成本遙測與路由決策成本分開累計**：能夠回答「路由本身花了多少 token」這個問題，
  對於評估「拆分路由 LLM 呼叫」這個架構選擇的實際成本效益很有幫助，是把工程決策量化的具體實踐
