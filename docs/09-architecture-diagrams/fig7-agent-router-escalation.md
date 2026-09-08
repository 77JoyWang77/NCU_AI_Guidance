# Fig 7 — 3-Agent 路由與逃逸機制（Orchestrator + AgentLimitation，main 分支）

## 論文定位

對話系統最具原創性的設計：不是把所有能力塞進一個大 agent，而是用一個 **LLM Orchestrator**
依據每個 agent 回報的自我評估（`AgentStatus`）動態決定下一步，並用 `visited_agents` +
`MAX_HANDOFFS` 防止無限乒乓（ping-pong）。

`main` 分支只有 **3 個 agent**（`chat` / `retrieval` / `research`），比早期設計（5 個 agent）更精簡；
同時多了一套具體的**逃逸理由型別**（`AgentLimitation` enum）與一個**哨兵字串觸發的即時逃逸機制**
（`[INSUFFICIENT_CONTEXT]`），把「agent 自認不足」從抽象概念變成可觀察、可記錄的具體事件。

**本圖也記錄了一個死碼發現**：路由架構裡有一整套「組合最終回覆」（`compose_after`/
`ExecutionPlan.composition_step`）的機制已經完整實作，但目前程式碼裡**沒有任何地方把
`compose_after` 設成 `True`**——這是一個結構完整但目前不可達的功能路徑，值得在圖上標註。

---

## 圖表類型建議

State machine / 循環流程圖。中央畫一個 Orchestrator 決策框，三個 agent 節點
（`chat`/`retrieval`/`research`）圍繞四周，主路由箭頭與「逃逸」箭頭用不同顏色區分。
`chat` 節點旁畫出 `[INSUFFICIENT_CONTEXT]` 哨兵偵測與「清空已串流內容」的特殊路徑
（這是本圖除路由本身外最值得強調的細節）。
Composition（`compose_after`）路徑建議用**虛線 + 灰階**表示「已實作但目前不可達」。

---

## 3 個 Agent（`VALID_AGENTS = {"chat", "retrieval", "research"}`）

| Agent | 定位 | 執行器 |
|---|---|---|
| `chat` | no-tool 直接回答；context 不足時自我偵測並逃逸 | `no_tool_runner`（單次呼叫） |
| `retrieval` | ReAct tool-loop，工具集合已收斂為單一 `search_report`（見 Fig6 的 retriever 邏輯） | `runner`（LangGraph `create_agent`） |
| `research` | coverage-driven 多輪檢索管線（Fig6） | `research/research_graph` |

沒有獨立的 `question`／`evaluation` agent——測驗生成與品質評估在這個分支不是路由目標。

---

## 呼叫鏈

```
route_request()
      │ 公開 API
      ▼
_orchestrate()
      │ LLM 決策（mini-model 優先，見下）
      ▼
RouterDecision{agent_name, reason}          ← 注意：沒有 evaluate_after 欄位
      │
      ▼
_route_for_agent()
      │
      ▼
AgentRoute{agent_name, prompt_name, prompt_version, compose_after}
      │
      ▼
_build_execution_plan()
      │
      ▼
ExecutionPlan{trace_id, route, steps: (ExecutionStep(kind="primary"), ...)}
      │
      ▼
route_agent_message / route_agent_stream（while _hop < MAX_HANDOFFS 迴圈）
      │
      ▼
_escalation_route_for()
```

`ExecutionStep{agent_name, observation_id, trace_id, kind, reason}` 與 `ExecutionPlan`
是比早期設計更明確的「執行計畫」物件——把「這一輪要跑哪個 agent、要不要接組合步驟」
顯式建模成一個不可變的 dataclass，而非只靠散落的 if/else 判斷。

---

## Orchestrator 決策細節

```python
_router_llm = AzureChatOpenAI(
    azure_deployment=pdf_settings.azure_mini_deployment or pdf_settings.azure_chat_deployment,
    temperature=0,
)
```

路由本身用**mini 模型優先、無 mini 部署才退回主模型**——路由決策相對簡單，不需要主力模型，
這是成本分層的具體實踐。輸入 payload：

```json
{
  "message": "...",
  "document_context": "文件 abstract 前 300 字",
  "previous_agent": "...",
  "is_followup_signal": true,
  "agent_status": {"completed": false, "work_summary": "...", "gaps": [...], "agent_limitation": "context_insufficient"},
  "steering_guidance": "...",
  "available_agents": ["chat", "retrieval", "research"]
}
```

呼叫失敗時 fallback：`RouterDecision(agent_name="retrieval", reason="fallback")`
——保守選擇「主動查」而非「直接聊」，避免在異常情況下用可能過時的既有 context 硬答。

### 路由器本身的 token 也被計入逐輪成本

```python
raw_result = await chain.ainvoke(...)   # include_raw=True
acc.router_input_tokens += raw_result["raw"].usage_metadata["input_tokens"]
acc.router_output_tokens += ...
```

路由決策的 LLM 呼叫成本與 agent 執行本身的成本分開累計（見 Fig8 的逐輪遙測），
可以獨立分析「路由開銷」占整體成本的比例。

---

## `AgentLimitation` enum — 逃逸理由的型別化

```python
class AgentLimitation(str, Enum):
    NONE = ""
    CONTEXT_INSUFFICIENT = "context_insufficient"
    SINGLE_POINT_LOOKUP = "single_point_lookup"
    RESEARCH_BUDGET_EXHAUSTED = "research_budget_exhausted"

@dataclass(frozen=True)
class AgentStatus:
    completed: bool = True
    work_summary: str = ""
    gaps: list[str] = field(default_factory=list)
    agent_limitation: AgentLimitation = AgentLimitation.NONE
```

每個 agent 執行完後回傳這份**自我評估**，交給 Orchestrator LLM 判斷是否換 agent 繼續——
`agent_limitation` 把「為什麼不足」從自由文字（`gaps`）升級成一個**可程式化判讀的 enum**，
方便未來做路由規則統計或監控（例如統計 `CONTEXT_INSUFFICIENT` 觸發率）。

`retrieval` 完成時的自評邏輯是具體例子：

```python
_retrieval_has_answer = bool(sources) and len(response.strip()) >= 30
AgentStatus(
    completed=_retrieval_has_answer,
    gaps=[] if _retrieval_has_answer else ["未找到與問題相關的文件片段"],
    agent_limitation=AgentLimitation.NONE if _retrieval_has_answer
                      else AgentLimitation.SINGLE_POINT_LOOKUP,
)
```

---

## `[INSUFFICIENT_CONTEXT]` 哨兵字串——chat 的即時自我偵測逃逸機制（本圖最核心的細節）

`chat_agent` 的 prompt 允許模型在無法從既有 context 充分回答時，於回覆**最後一行**輸出
字面量 `[INSUFFICIENT_CONTEXT]`。`route_agent_stream` 逐 token 累積回覆後檢查：

```python
_chat_lines = _chat_full.strip().split("\n")
if _chat_lines[-1].strip() == "[INSUFFICIENT_CONTEXT]":
    _chat_full = "\n".join(_chat_lines[:-1]).strip()   # 剝除哨兵字串
    yield "", "replace", []                             # 通知前端：丟棄已經串流出去的內容
    agent_result = AgentResult(
        response=_chat_full,
        status=AgentStatus(
            completed=False,
            work_summary="chat 無法從現有 context 充分回答",
            agent_limitation=AgentLimitation.CONTEXT_INSUFFICIENT,
        ),
    )
```

這個機制的巧妙之處：`chat` 是**逐 token 串流**的，使用者可能已經看到一部分回覆，
但模型判斷「這樣答下去證據不夠」時，系統會送出一個 `"replace"` 訊號讓前端**清空剛剛顯示的內容**，
再無縫接上逃逸後其他 agent 的正式回答——而不是留下一段「答一半就被打斷」的殘留文字。

---

## 逃逸防護（Anti-Ping-Pong）

```python
async def _escalation_route_for(result, route, ..., hop_count, visited_agents):
    if result.status.completed or hop_count + 1 >= MAX_HANDOFFS:
        return None
    guidance = steering.get_and_clear(thread_id)
    decision = await _orchestrate(..., agent_status=result.status, steering_guidance=guidance)
    if decision.agent_name == route.agent_name or decision.agent_name in visited_agents:
        return None
    return _route_for_agent(decision.agent_name, document_id, thread_id)
```

`MAX_HANDOFFS = 3`，`while _hop < MAX_HANDOFFS` 顯式迴圈（非遞迴）；`visited_agents` 是
每個 hop 重建的 frozenset，拒絕路由回「自己」或「已造訪過」的 agent——3 個 agent 的情況下，
這代表一次對話最多換兩次 agent（例如 chat→retrieval→research），第三次必然停止並交付當前結果。

### `_looks_like_followup` 追問偵測（餵給 Orchestrator 的訊號之一）

```python
_FOLLOWUP_SIGNALS = (
    "繼續","再說","補充","更多","詳細","展開","那","那麼","這個",
    "剛才","你說的","上面","除此之外","另外","而且","還有",
    "more","continue","elaborate","expand","follow up",
)
def _looks_like_followup(message):
    return len(message.strip()) <= 60 and any(sig in message.lower() for sig in _FOLLOWUP_SIGNALS)
```

只對短訊息（≤60 字）生效，避免長訊息裡偶然出現「那」這類字被誤判。

---

## Composition 路徑——已實作但目前不可達的死碼

```python
def _route_for_agent(agent_name, document_id, thread_id=None):
    if agent_name == "research":
        return AgentRoute(agent_name, prompt.name, prompt.version, compose_after=False)  # 顯式 False
    if agent_name == "retrieval":
        return AgentRoute(agent_name, "retrieval_capability", prompt_version(...))       # 預設 False
    return AgentRoute("chat", "chat_mode", prompt_version("chat_mode"))                  # 預設 False
```

全專案搜尋 `compose_after=True`：**零筆結果**。`_build_execution_plan` 裡
「`if route.compose_after and agent_name != "chat": steps.append(composition_step)`」、
`_run_composition()`、`COMPOSE_MIN_CHARS=600` 長度閘門、以及 `route_agent_stream` 裡整段
「等待 research/retrieval 全部產出後再用 `chat_agent.compose_final_response` 重新格式化」的邏輯，
在目前的路由決策下**永遠不會被觸發**——`composition_step` 恆為 `None`。

這代表 `retrieval`/`research` 目前是**直接串流原始輸出給使用者**，不會經過「最終格式化層」。
這是一個值得在圖上明確標註的架構現況（可能是功能開發到一半、或曾經啟用後又停用但沒清除程式碼），
論文寫作時可以誠實呈現，並作為「系統演進留下的死碼」案例之一（與 Fig8 提到的 Qdrant 遺留問題、
與課程推薦系統中未被使用的 `intent_classifier.py` 屬同一類現象）。

---

## 設計決策補充說明（論文 Discussion 可引用）

- **為何用 LLM Orchestrator 而非規則式路由**：需要理解使用者訊息意圖與前一輪 `AgentStatus`
  自評之間的語意關聯，規則式判斷難以窮舉所有組合；路由器改用 mini 模型顯示團隊有意識地把
  「決策複雜度」與「決策成本」分開考慮
- **`AgentLimitation` enum 化的價值**：把逃逸理由從純自由文字（`gaps`）升級成可程式化列舉，
  是從「給人看的除錯資訊」進化到「系統可以統計、可以做規則」的中間型態
- **`[INSUFFICIENT_CONTEXT]` + `"replace"` 訊號的組合**：解決了串流 UI 常見的兩難——
  「要嘛等模型想清楚才開始輸出（延遲高），要嘛邊想邊串流（可能中途發現答不出來留下爛尾）」，
  這裡選擇後者但用一個明確的清空訊號補救體驗
- **Composition 路徑的死碼**：誠實記錄系統現況比假裝功能完整更符合論文的嚴謹性；
  同時也提醒「路由架構完整」不等於「所有分支都在跑」，兩者是不同層次的問題
