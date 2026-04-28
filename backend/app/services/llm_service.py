"""
llm_service.py

Azure OpenAI GPT-4o 呼叫 + LangSmith 監控。

環境變數：
  AZURE_OPENAI_API_KEY          — Azure OpenAI 金鑰
  AZURE_OPENAI_ENDPOINT         — https://<resource>.openai.azure.com/
  AZURE_OPENAI_API_VERSION      — 例如 2024-12-01-preview
  AZURE_OPENAI_CHAT_DEPLOYMENT  — 對話模型的部署名稱（例如 gpt-4o）
  LANGSMITH_API_KEY             — LangSmith 金鑰（選填）
  LANGSMITH_PROJECT             — LangSmith 專案名稱（預設 "ncu-rag-system"）
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Optional

from openai import AzureOpenAI

try:
    from langsmith import traceable
    from langsmith.wrappers import wrap_openai
    _LANGSMITH_AVAILABLE = True
except ImportError:
    _LANGSMITH_AVAILABLE = False

    def traceable(func=None, **kwargs):
        if func is not None:
            return func
        def decorator(f):
            return f
        return decorator


MAX_TOKENS = 2048

SYSTEM_PROMPT = """你是「中央大學選課助理」，協助高中生、大學生了解中央大學的課程、系所、學分學程資訊。

## 回答規則
1. 使用繁體中文，語氣友善、清楚。
2. 根據提供的 context 回答，不要捏造課程名稱或數字。
3. 若 context 不足以回答，誠實說明「目前資料不足以確認」。
4. 涉及必修/修課規劃時，可提醒學生以學校最新公告為準。
5. 回答長度適中，善用條列式整理。

## Tool 選用指引

**學程說明查詢**：使用者問學程介紹、目標、修課方式時，優先呼叫 `get_program_description`，
可同時呼叫 `get_program_courses` 取得課程清單（平行呼叫，不需等待）。

**畢業規定查詢**：使用者問系所畢業學分、修業規定時，優先呼叫 `get_requirements_notes`，
比 `get_graduation_rules` 包含更多原文說明。

**技術/工具查詢**：使用者問「有哪些課教 PyTorch/Python/TensorFlow...」時，
必須傳入 `tech` 參數給 `search_courses`（觸發 graph-first 精確查詢）。

**相似課程推薦**：使用者問「有沒有類似 OO 的課」或「跨系有沒有教 OO 的課」時，
呼叫 `find_similar_courses`，透過 Concept 節點找跨系相似課程。

## 平行查詢策略
當問題涉及多個面向時，同一輪同時呼叫多個 tool：
- 詢問學程：同時呼叫 `get_program_description` + `get_program_courses`
- 詢問系所課程：同時呼叫 `get_dept_courses(required)` + `get_dept_courses(elective)`
- 詢問教師：同時呼叫 `get_teacher_info` + `search_teachers`

## Fallback 策略
若第一個 tool 回傳空結果，立即嘗試：
1. 換關鍵字（如「演算法」→「Algorithm」、只保留核心詞）
2. 改用另一個 tool（如 graph → vector，或換用 `find_similar_courses`）
3. 對課程名稱嘗試變體（「人工智慧」可能叫「人工智慧概論」「AI導論」「生成式AI」）

## 課程名稱查詢注意事項
同一門課可能有多種名稱：
- 「演算法」可能叫：演算法設計、演算法分析、資料結構與演算法
- 「人工智慧」可能叫：人工智慧概論、AI導論、生成式AI、人工智慧與機器學習
- 若查詢無結果，嘗試用更短的核心詞重新查詢
"""


@lru_cache(maxsize=1)
def _get_client() -> AzureOpenAI:
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    if not api_key or not endpoint:
        raise EnvironmentError("請設定 AZURE_OPENAI_API_KEY 和 AZURE_OPENAI_ENDPOINT 環境變數")

    client = AzureOpenAI(
        api_key=api_key,
        azure_endpoint=endpoint,
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
    )

    # LangSmith 包裝（若有設定 API key 才啟用）
    if (
        _LANGSMITH_AVAILABLE
        and os.environ.get("LANGSMITH_API_KEY")
        and os.environ.get("LANGSMITH_TRACING", "true").lower() == "true"
    ):
        return wrap_openai(client)
    return client


def _build_context(
    vector_results: list[dict],
    graph_results: dict,
) -> str:
    """將向量搜尋結果和圖查詢結果組裝成 context 字串"""
    parts: list[str] = []

    if vector_results:
        parts.append("【相關課程資訊】")
        for i, r in enumerate(vector_results[:6], 1):
            meta = r.get("metadata", {})
            name = meta.get("name_zh", "")
            dept = meta.get("dept", "")
            credits = meta.get("credits", "")
            type_ = meta.get("type", "")
            teacher = meta.get("teacher", "")
            doc = r.get("document", "")[:300]

            header = f"{i}. {name}"
            if dept:
                header += f"（{dept}"
                if credits:
                    header += f"，{credits}學分"
                if type_:
                    header += f"，{type_}"
                header += "）"
            if teacher:
                header += f" ／ 授課：{teacher}"
            parts.append(header)
            if doc:
                parts.append(f"   {doc}")
            spec = meta.get("teacher_specialties", "")
            when_raw = meta.get("when_raw", "")
            prereq = meta.get("prereq_codes", "")
            eligible = meta.get("eligible_years", "")
            if spec:
                parts.append(f"   教師專長：{spec[:80]}")
            if when_raw:
                parts.append(f"   建議修習：{when_raw}")
            if prereq:
                parts.append(f"   先修課號：{prereq}")
            if eligible:
                parts.append(f"   適合年級：{eligible}")
            parts.append("")

    if graph_results:
        if graph_results.get("required_courses"):
            parts.append("【系所必修課程】")
            for c in graph_results["required_courses"][:20]:
                line = f"- {c.get('name', c.get('id', ''))}"
                if c.get("credits"):
                    line += f"（{c['credits']}學分）"
                parts.append(line)
            parts.append("")

        if graph_results.get("elective_courses"):
            parts.append("【系所選修課程】")
            for c in graph_results["elective_courses"][:20]:
                line = f"- {c.get('name', c.get('id', ''))}"
                if c.get("credits"):
                    line += f"（{c['credits']}學分）"
                parts.append(line)
            parts.append("")

        if graph_results.get("program_courses"):
            parts.append("【學程課程】")
            for c in graph_results["program_courses"][:20]:
                line = f"- {c.get('name', c.get('id', ''))}（{c.get('relation', '')}）"
                parts.append(line)
            parts.append("")

        if graph_results.get("teacher_courses"):
            parts.append("【教師開課】")
            for c in graph_results["teacher_courses"][:10]:
                line = f"- {c.get('name', c.get('id', ''))}"
                parts.append(line)
            parts.append("")

        if graph_results.get("graduation_info"):
            info = graph_results["graduation_info"]
            parts.append(f"【畢業規定：{info.get('dept_name', '')}】")
            parts.append(f"最低畢業學分：{info.get('min_credits', 0)}")
            parts.append(f"必修學分：{info.get('required_credits', 0)}")
            for rule in info.get("graduation_rules", [])[:8]:
                parts.append(f"- {rule.get('description', '')}")
            certs = info.get("certifications", [])
            if certs:
                parts.append(f"證照要求：{', '.join(certs)}")
            parts.append("")

        if graph_results.get("prereq_courses"):
            parts.append("【先修課程詳情】")
            for r in graph_results["prereq_courses"][:5]:
                m = r.get("metadata", {})
                parts.append(f"- {m.get('name_zh', r.get('id', ''))}（{m.get('dept', '')}）")
            parts.append("")

    return "\n".join(parts) if parts else "（無相關資料）"


@traceable(name="ncu_rag_answer", run_type="llm")
def generate_answer(
    question: str,
    vector_results: Optional[list[dict]] = None,
    graph_results: Optional[dict] = None,
    extra_context: Optional[str] = None,
) -> dict:
    """
    根據 context 生成回答。

    回傳：
      {"answer": str, "model": str, "input_tokens": int, "output_tokens": int}
    """
    client = _get_client()
    deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o")

    context = _build_context(vector_results or [], graph_results or {})
    if extra_context:
        context = extra_context + "\n\n" + context

    user_message = f"""以下是關於這個問題的相關資料：

{context}

問題：{question}

請根據上面的資料回答問題。"""

    response = client.chat.completions.create(
        model=deployment,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    answer = response.choices[0].message.content or ""
    return {
        "answer": answer,
        "model": deployment,
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
    }


def generate_simple_answer(question: str, context: str) -> str:
    """輕量版：直接傳入 context 字串"""
    result = generate_answer(question, extra_context=context)
    return result["answer"]


def _extract_mentioned_courses(answer: str, course_pool: dict) -> list[dict]:
    """掃描 answer 中出現的課程名稱，與 course_pool 比對，回傳已驗證課程卡片。"""
    mentioned = []
    seen: set[str] = set()
    for course in course_pool.values():
        name = course.get("name", "")
        if not name or len(name) < 2:
            continue
        if name in answer and name not in seen:
            seen.add(name)
            mentioned.append(course)
    return mentioned


def _collect_course_pool(tool_name: str, result, course_pool: dict) -> None:
    """從單次工具回傳結果中收集課程資料到 course_pool。"""
    if tool_name == "search_courses" and isinstance(result, list):
        for item in result:
            key = item.get("course_code") or item.get("name_zh", "")
            if key:
                course_pool[key] = {
                    "code":    item.get("course_code", ""),
                    "name":    item.get("name_zh", ""),
                    "dept":    item.get("dept", ""),
                    "credits": item.get("credits", 0),
                    "type":    item.get("type", ""),
                    "teacher": item.get("teacher", ""),
                    "summary": item.get("summary", "")[:150],
                }
    elif tool_name in ("get_dept_courses", "get_program_courses") and isinstance(result, dict):
        dept_or_prog = result.get("dept_name") or result.get("program_name", "")
        for c in result.get("courses", []):
            name = c.get("name") or c.get("id", "")
            if name:
                course_pool[name] = {
                    "code":    c.get("id", ""),
                    "name":    name,
                    "dept":    dept_or_prog,
                    "credits": c.get("credits", 0),
                    "type":    c.get("relation", ""),
                    "teacher": c.get("teacher", ""),
                    "summary": "",
                }


@traceable(name="ncu_rag_tools", run_type="llm")
def generate_with_tools(
    question: str,
    history: Optional[list[dict]] = None,
    context_hint: str = "",
    max_rounds: int = 4,
) -> dict:
    """
    ReAct Tool-Use 模式：LLM 自行決定工具呼叫順序，支援並行執行。

    回傳：
      {"answer": str, "tools_used": list[str], "sources": list[dict],
       "course_cards": list[dict], "course_pool_count": int, "has_large_result": bool,
       "model": str, "input_tokens": int, "output_tokens": int}
    """
    from app.services.tools import TOOLS, execute_tool

    client = _get_client()
    deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o")

    system = SYSTEM_PROMPT
    if context_hint:
        system += f"\n\n## 學生背景資訊\n{context_hint}"

    messages: list[dict] = list(history or [])
    messages.append({"role": "user", "content": question})

    tools_used: list[str] = []
    sources: list[dict] = []
    course_pool: dict[str, dict] = {}
    has_large_result = False
    total_input = total_output = 0

    for _ in range(max_rounds):
        response = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "system", "content": system}] + messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=MAX_TOKENS,
        )
        total_input  += response.usage.prompt_tokens
        total_output += response.usage.completion_tokens
        msg = response.choices[0].message

        if not msg.tool_calls:
            answer = msg.content or ""
            return {
                "answer":            answer,
                "tools_used":        tools_used,
                "sources":           sources,
                "course_cards":      _extract_mentioned_courses(answer, course_pool),
                "course_pool_count": len(course_pool),
                "has_large_result":  has_large_result,
                "model":             deployment,
                "input_tokens":      total_input,
                "output_tokens":     total_output,
            }

        # 並行執行所有工具呼叫
        with ThreadPoolExecutor() as pool:
            futures = {
                tc.id: pool.submit(execute_tool, tc.function.name,
                                   json.loads(tc.function.arguments))
                for tc in msg.tool_calls
            }
            results = {tid: f.result() for tid, f in futures.items()}

        # 收集課程資料 + 來源
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            result = results.get(tc.id)
            tools_used.append(tool_name)

            _collect_course_pool(tool_name, result, course_pool)

            if tool_name == "search_courses" and isinstance(result, list):
                for item in result[:5]:
                    if item.get("name_zh"):
                        sources.append({
                            "name": item["name_zh"],
                            "dept": item.get("dept", ""),
                            "type": item.get("type", ""),
                        })

            if tool_name in ("get_dept_courses", "get_program_courses") and isinstance(result, dict):
                if len(result.get("courses", [])) > 20:
                    has_large_result = True

        # 把 assistant 訊息（含 tool_calls）加回對話
        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name":      tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        })

        # 加入每個工具的回傳結果
        for tc in msg.tool_calls:
            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      json.dumps(results[tc.id], ensure_ascii=False),
            })

    # 超過最大輪數：強制生成最終回答
    final = client.chat.completions.create(
        model=deployment,
        messages=[{"role": "system", "content": system}] + messages,
        max_tokens=MAX_TOKENS,
    )
    total_input  += final.usage.prompt_tokens
    total_output += final.usage.completion_tokens
    answer = final.choices[0].message.content or ""
    return {
        "answer":            answer,
        "tools_used":        tools_used,
        "sources":           sources,
        "course_cards":      _extract_mentioned_courses(answer, course_pool),
        "course_pool_count": len(course_pool),
        "has_large_result":  has_large_result,
        "model":             deployment,
        "input_tokens":      total_input,
        "output_tokens":     total_output,
    }
