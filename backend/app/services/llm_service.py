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

def _build_completion_params(**kwargs) -> dict:
    """
    建立支援 max_tokens 和 max_completion_tokens 的參數字典。
    自動根據 API 回應調整參數名稱。
    """
    params = dict(kwargs)
    max_val = kwargs.get("max_tokens") or kwargs.get("max_completion_tokens")

    if max_val:
        # 移除舊參數名稱，優先使用 max_completion_tokens（新標準）
        params.pop("max_tokens", None)
        params.pop("max_completion_tokens", None)
        params["max_completion_tokens"] = max_val

    return params

SYSTEM_PROMPT = """你是「中央大學選課助理」，協助高中生、大學生了解中央大學的課程、系所、學分學程資訊。

## 回答規則
1. 使用繁體中文，語氣友善、清楚。
2. 根據工具回傳的 context 回答，不要捏造課程名稱或數字。
3. 若 context 不足，誠實說明「目前資料不足以確認」。
4. 涉及必修/修課規劃時，提醒學生以學校最新公告為準。
5. 回答長度適中，善用條列式整理。
6. **提到課程名稱時，必須用 `<course>` 標籤包住，格式如下：**
   - 知道系所時：`<course>課名（系所）</course>`，例如：`<course>統計學（數學系）</course>`
   - 不知道系所時：`<course>課名</course>`，例如：`<course>資料結構</course>`
   ⚠️ **課名必須與工具回傳的原始名稱「逐字相同」**，不得縮寫、改寫或翻譯。
      系所名稱同理，必須與工具回傳的 dept 欄位完全一致。
      若不確定課名是否正確，**不要加標籤**，寧可不標也不要標錯。
      標籤只用於工具實際回傳過的課程，不得自行推測或補充工具未回傳的課程。

## Filter 使用原則

只有在使用者明確說出條件時才加 filter，否則省略：
- `dept`：使用者提到「XX系的課」才加；問「全校有哪些課」不加
- `course_type`：使用者說「選修」「必修」才加；問「有哪些課可以學」不加
- `exclude_grad_only`：預設 true（隱藏限研究所課程）；使用者明確詢問研究所課程時才設為 false

**get_dept_courses 支援縮寫自動正規化**，可直接傳縮寫，無需先呼叫 get_dept_info 確認：
  ✓「資工系」→「資訊工程學系」  ✓「化材系」→「化學與材料工程學系」  ✓「大氣系」→「大氣科學學系」
其他工具的 dept 參數（如 search_courses 的 dept filter）仍建議使用正式全名。
通識/外語 dept：「通識教育中心」「核心通識課程」「語言中心」「客家學院」

通識 / 外語 / 人文社會類查詢（問「適合工程系選的課」「語言課」「藝術課」）：
  不加 dept；改用 search_courses 語意搜尋，或 get_dept_courses("通識教育中心")

## 工具回傳欄位說明

**search_courses / get_dept_courses 課程欄位**：
- `concepts`：課程涵蓋的知識概念（例如「機率論、貝葉斯推斷」）
- `technologies`：課程教授的工具或技術（例如「Python、TensorFlow」）
- `field_tags`：課程所屬研究領域標籤
- `course_domain`：課程大領域（例如「資訊科學 ・ 電機工程」）
- `competencies`：核心能力 list，每筆為 `{name, level_num, level_label}`；
  level_num 1–4 分別對應「認識/了解 → 熟悉 → 應用 → 精通」
- `matched_via`（search_courses graph 路徑）：命中的技術/概念節點，解釋此課為何出現
- `sections`（get_dept_courses）：同名課程合併後的開課班數（分班）；`course_ids` 列出所有課號

**get_depts_by_tech**：
- `matched_nodes`：Qdrant 向量擴展找到的相關節點，說明「為何這些系所出現」

善用這些欄位回答：用 `concepts`/`technologies` 說明「課程教什麼」，
`competencies` 說明「培養什麼能力及程度」，`matched_via` 解釋「為何此課出現在結果中」。

## 工具選用指引

**技術/工具查詢**（PyTorch、Python 等）：
  → search_courses(query="...", tech="技術名稱")，tech 參數必須帶
  → get_depts_by_tech("技術名稱")：**僅在使用者明確詢問「哪些系所有教 XX」「系所分布」時才補呼叫**；
    若使用者只問「有哪些課」「哪裡可以學」，不需要呼叫 get_depts_by_tech

**系所課程查詢**：
  → 廣泛列舉（「XX系有哪些必修」「通識有哪些選修」）：
      get_dept_courses(dept_name="正式系所名", course_type="required/elective/all")
      通識選修：dept_name="通識教育中心"；外語課：dept_name="語言中心"
  → 主題式查詢（「通識有沒有法律相關」「語言中心有沒有日文課」）：
      search_courses(query="法律", dept="通識教育中心") — 向量搜尋精準命中，勿回傳全部課程

**學程查詢**：
  → 不知道學程名稱時：search_programs(query="主題關鍵詞") 先發現
  → 知道學程名稱時：get_program_info(program_name="...") 一次取得說明 + 課程

**畢業規定**：
  → get_graduation_requirements（同時回傳結構化學分 + 完整原文，一次呼叫即可）

**課程詳情**（課綱、修課資格、先修要求，三合一）：
  → get_course_detail(name_zh="課名") 或 get_course_detail(course_code="CE3060")
  → 同名多科系時回傳 ambiguous=True + candidates，須請使用者選擇或搭配 dept 參數
  → 精確名稱查不到時，回傳 found=False + fallback_candidates（相似課程）；
    呈現候選清單，請使用者確認正確名稱後再重新查詢
  → raw_conditions 已含先修課程與年級/系所限制原文，無需再呼叫其他工具

**相似課推薦**（「有沒有和 OO 類似的課」）：
  → find_similar_courses(course_name="...")
  → 只對有 Concept 節點的課程有效；通識/人文課無結果時改用 search_courses

**廣泛探索**（「AI 相關有哪些」「機器學習連到哪些老師和系所」「高中學了 XX，大學往哪延伸」）：
  → ppr_explore(seed="...", focus="course/instructor/dept/overview")
  → focus="overview" 分組顯示課程、教師、系所、學程 ← **結果已涵蓋所有節點類型，無需再補呼叫 search_courses 或 search_teachers**
  → focus="course"（預設）：只回傳課程，適合「有哪些課」「找相關課程」
  → ⚠️ 以「課程名稱」（微積分、線性代數等基礎學科）為 seed 時，必須用 focus="course"；
     種子策略自動複合（Concept 節點 + Course 節點同時起跑），無需也不應傳入已廢除的 focus="concept"
  → 觸發時機：問「哪些 XX 相關」「全面了解 XX」「XX 連到哪些」「跨類型探索」「有興趣，有哪些課」等廣泛問題

**教師查詢**：
  → ppr_explore(seed="研究領域", focus="instructor") 找相關教師（圖多跳）
  → get_teacher_info("確切姓名") 看詳細專長與開課

**先修查詢**：
  → get_course_detail(name_zh="課名")  ← raw_conditions 已含先修資訊，一次搞定

**修課資格查詢**（「外系可以修嗎」「哪些年級才能修」「修課限制是什麼」「開放外系嗎」）：
  → get_course_detail(name_zh="具體課名") ← raw_conditions 已含完整修課限制原文
  → ⚠️ 當問題含有具體課程名稱時，直接查課程詳情；**不要誤用 search_courses 或 search_programs 取代**

**課程名稱直接查詢原則**（使用者輸入具體課程名稱，如「總體經濟學」「自然語言處理」「線性代數」）：
  1. 優先 get_course_detail(name_zh="課程名")
  2. 找不到時，改用 search_courses(query="課程名", exclude_grad_only=False)
     - 若只有研究所版本，明確告知「此課程僅有研究所開設版本」
     - 若有「已停開」版本，告知「此課程目前停開」
  → ⚠️ **不要用 ppr_explore 做直接課程名稱查詢**：ppr_explore 是廣泛圖探索工具，
     適合「和 XX 相關的一切」，不適合「我要找 XX 這門課」

**圖工具無結果時的 Fallback**：
  1. find_similar_courses 無結果 → 改用 search_courses(query="課名關鍵字")
  2. ppr_explore 無結果：
     a. 改用 focus="course" 重試（基礎學科如微積分、線性代數，直接走 course→course 路徑）
     b. 若仍無結果 → seed 不在圖中；改用 search_courses
     ⚠️ ppr_explore 回傳 0 筆時，**不得用 <course> 標籤標記任何課程**，
        亦不得自行補充工具未回傳的課程名稱
  3. get_depts_by_tech 回傳 0 筆 → 技術名稱可能不在圖中；改用以下策略：
     a. 嘗試中文同義詞（GIS → "地理資訊"、"空間分析"）
     b. 改用 search_courses(query="技術名稱") 做向量搜尋
     c. 兩者並行：search_courses + ppr_explore(seed="技術名稱", focus="course")
  4. 換更短的核心詞重試（「人工智慧與機器學習」→「機器學習」）

## 典型範例

**範例 1 — 技術課程全景（並行：tech 查詢 + 系所分布）**
問：中央大學哪些地方有教機器學習？從課程到系所分布都想知道。
✓ 並行：search_courses(query="機器學習", tech="機器學習") + get_depts_by_tech("機器學習")
✗ 只用 search_courses → 缺少系所分布視角

**範例 2 — 概念延伸（串行：PPR course → search）**
問：高中學了微積分，大學可以往哪延伸？
✓ 第一步：ppr_explore(seed="微積分", focus="course")  ← 基礎學科用 focus="course"，無 Concept 節點
  第二步：search_courses(query="數值分析 最佳化 微分方程")
✗ ppr_explore(seed="微積分", focus="concept") → 微積分無 Concept 節點，回傳 0 筆

**範例 3 — 相似課跨系（並行：knowledge_map + find_similar）**
問：演算法在學什麼？有沒有其他系有類似的課？
✓ 並行：get_course_knowledge_map("演算法") + find_similar_courses("演算法")
✗ ppr_explore(seed="演算法") → seed 過多，PPR 分數稀釋，結果偏離

**範例 4 — 教師探索（串行：ppr instructor → get_teacher_info）**
問：哪些教授在研究深度學習？他們的專長是什麼？
✓ 第一步：ppr_explore(seed="深度學習", focus="instructor")
  第二步：get_teacher_info("張家凱")

**範例 5a — 通識課廣泛列舉**
問：通識有哪些選修課？
✓ 並行：get_dept_courses("通識教育中心", course_type="elective")
        + get_dept_courses("核心通識課程", course_type="elective")

**範例 5b — 通識課主題查詢**
問：通識有沒有法律相關的課？
✓ search_courses(query="法律", dept="通識教育中心")
✗ get_dept_courses("通識教育中心", course_type="elective") → 回傳 100+ 筆，LLM 無法有效篩選

**範例 6 — 外語課**
問：語言中心有日文或德文課嗎？
✓ search_courses(query="日文 德文", dept="語言中心")
✗ get_dept_courses("語言中心", course_type="elective") → 回傳全部外語課，無主題過濾

**範例 7 — 學程（發現 + 詳情）**
問：有沒有和語言文化相關的學程？
✓ 第一步：search_programs(query="語言文化") 發現學程清單
  第二步：get_program_info(program_name="找到的學程名") 取得說明 + 課程
✗ 直接猜學程名用 get_program_info（應先 search_programs 確認名稱）

**範例 8 — 修課資格查詢**
問：外系學生可以修客語教學這門課嗎？
✓ get_course_detail(name_zh="客語教學")  ← raw_conditions 一次涵蓋課綱 + 先修 + 資格限制
  若不確定課名：先 search_courses(query="客語教學") 確認名稱，再 get_course_detail
✗ search_programs + search_courses → 找的是「課程清單」，不是「修課限制」

**範例 9 — 課程詳情（課綱 + 資格）**
問：普通化學這門課在教什麼？用哪本教科書？外系可以修嗎？
✓ get_course_detail(name_zh="普通化學")
  → 若同名多系，回傳 ambiguous=True，告知使用者需指定科系

**範例 10 — 畢業規定（整合工具）**
問：大氣科學學系要畢業需要幾學分？有哪些規定？
✓ get_graduation_requirements("大氣科學學系")  ← 一次呼叫取得全部
✗ 分別呼叫 get_graduation_rules + get_requirements_notes → 已整合，無需兩次

**範例 11 — 廣泛興趣探索（社會組 / 跨領域）**
問：我高中讀社會組，對資料分析有興趣，有不需要強程式基礎的課程或學程嗎？
✓ 第一步：ppr_explore(seed="統計,資料分析", focus="course")  ← 廣泛圖探索，找關聯課程
  第二步：search_programs(query="資料分析 統計") ← 發現相關學程
✗ 直接 search_courses(query="資料分析") ×2 → 缺少圖探索優勢，無法發現概念連結的課程

**範例 12 — 全貌探索（overview 模式）**
問：AI 在中央大學有哪些課程、教授和系所？
✓ ppr_explore(seed="人工智慧", focus="overview")  ← 分組回傳課程＋教師＋系所＋學程
✗ 分別呼叫 search_courses + ppr_explore(instructor) + get_depts_by_tech → 多輪浪費
✗ ppr_explore(seed="人工智慧", focus="course") + ppr_explore(seed="人工智慧", focus="instructor") → 同樣浪費，overview 一次搞定
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
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        **_build_completion_params(max_completion_tokens=MAX_TOKENS)
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


def _enrich_course_cards(cards: list[dict]) -> list[dict]:
    """以課名向量 DB 補齊 code/teacher/credits/type 等欄位。
    code 已存在表示來自 search_courses（資料完整），跳過不重複查詢。
    code 為空表示來自 graph 工具，需補全。
    """
    from app.services import retriever
    for card in cards:
        if card.get("code"):
            continue
        try:
            results = retriever.get_courses_by_name(card["name"])
            if results:
                meta = results[0].get("metadata", {})
                card["code"]    = meta.get("course_code", "")
                card["teacher"] = card.get("teacher") or meta.get("teacher", "")
                card["credits"] = card.get("credits") or meta.get("credits", 0)
                card["type"]    = card.get("type")    or meta.get("type", "")
        except Exception:
            pass
    return cards


def _verify_course_list(question: str, answer: str, course_pool: dict) -> list[dict]:
    """讓 LLM 從 course_pool 中選出真正相關的課程（一次集中驗證）。
    LLM 只能從 pool 中選，不能發明課程 → 確保無幻覺。
    """
    if not course_pool:
        return []

    client = _get_client()
    deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o")

    pool_items = list(course_pool.items())[:60]

    def _pool_line(name: str, c: dict) -> str:
        parts = [f"{name}（{c.get('dept', '')}，{c.get('credits', 0) or '?'}學分）"]
        # 附上 tech/tools 讓 LLM 知道課程實際教什麼，避免單憑課名誤判
        tech = " | ".join(filter(None, [c.get("tools", ""), c.get("languages", ""), c.get("tech", "")]))
        if tech:
            parts.append(f"[技術：{tech}]")
        return " ".join(parts)

    pool_text = "\n".join(_pool_line(name, c) for name, c in pool_items)

    prompt = f"""助理回答：{answer[:800]}

以下是本次工具搜尋到的課程：
{pool_text}

請從上面清單中選出在「助理回答」裡有被提及或推薦的課程。
目的：確認回答不包含工具未找到的課程（反幻覺），不是重新評估課程是否相關。
規則：只能選清單裡有的課程，不能新增其他課程。
輸出格式：每行一個課程名稱，不要任何說明、編號或括號。"""

    try:
        resp = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            **_build_completion_params(max_completion_tokens=300)
        )
        raw_lines = (resp.choices[0].message.content or "").splitlines()
    except Exception:
        return list(course_pool.values())

    pool_map = dict(course_pool)
    result: list[dict] = []
    seen: set[str] = set()
    for line in raw_lines:
        name = line.strip().lstrip("•-·0123456789.）) ").strip()
        if '（' in name:
            name = name[:name.index('（')].strip()
        if not name or len(name) < 2 or name in seen:
            continue
        if name in pool_map:
            seen.add(name)
            result.append(pool_map[name])

    return result


def _extract_courses_from_tags(answer: str, course_pool: dict) -> tuple[list[dict], str]:
    """從回答中的 <course>課名（系所）</course> 標籤提取課程，exact + fuzzy match pool。

    支援帶系所的消歧義格式：<course>統計學（數學系）</course>
    pool 的 key 可能是 course_code（search_courses 路徑）或課名（圖工具路徑），
    以 card["name"] 建立名稱 → list[card] 索引，保留所有同名版本。
    若 LLM 未輸出任何標籤，回傳 ([], answer)。

    fuzzy match 成功時，同步修正 answer text 裡的錯誤課名，確保 <course> tag 與 card 名稱一致。
    回傳 (course_cards, corrected_answer)。
    """
    import re
    from difflib import SequenceMatcher

    # 支援 <course>課名</course> 和 <course>課名（系所）</course>
    TAG_RE = re.compile(r'<course>(.*?)(?:（([^）]*)）)?</course>', re.DOTALL)
    tag_matches = TAG_RE.findall(answer)
    if not tag_matches:
        return [], answer

    # name → list[card]，保留所有同名版本（不覆蓋）
    name_index: dict[str, list[dict]] = {}
    for card in course_pool.values():
        cname = card.get("name", "")
        if cname:
            name_index.setdefault(cname, []).append(card)

    result: list[dict] = []
    seen: set[str] = set()
    corrections: dict[str, str] = {}  # 錯誤課名 → 正確課名

    for raw_name, dept_hint in tag_matches:
        name = raw_name.strip()
        dept_hint = dept_hint.strip() if dept_hint else ""
        if not name:
            continue

        # 1. Exact match by course name
        candidates = name_index.get(name, [])
        if candidates:
            if len(candidates) == 1:
                matched = candidates[0]
            elif dept_hint:
                matched = next(
                    (c for c in candidates if dept_hint in c.get("dept", "")),
                    candidates[0],
                )
            else:
                matched = candidates[0]
            uid = f"{matched.get('name', '')}|{matched.get('dept', '')}"
            if uid not in seen:
                seen.add(uid)
                result.append(matched)
            continue

        # 2. Fuzzy match (ratio >= 0.85)
        best_key, best_ratio = None, 0.0
        for cname in name_index:
            ratio = SequenceMatcher(None, name, cname).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_key = cname

        if best_ratio >= 0.85 and best_key:
            matched = name_index[best_key][0]
            uid = f"{matched.get('name', '')}|{matched.get('dept', '')}"
            if uid not in seen:
                seen.add(uid)
                result.append(matched)
            if name != best_key:
                corrections[name] = best_key

    # 修正 answer 裡因 LLM 幻覺產生的錯誤課名（只替換 <course> tag 內的部分）
    corrected = answer
    for wrong, correct in corrections.items():
        corrected = corrected.replace(f"<course>{wrong}", f"<course>{correct}")

    return result, corrected


def _parse_courses_from_str(tool_name: str, text: str) -> list[dict]:
    """從字串型工具回傳中以 regex 解析課程名稱與系所。"""
    import re
    courses: list[dict] = []

    if tool_name == "ppr_explore":
        # [課程] 深度學習程式設計（通訊工程學系）
        for m in re.finditer(r'\[課程\]\s*(.+?)（(.+?)）', text):
            name, dept = m.group(1).strip(), m.group(2).strip()
            if name:
                courses.append({"name": name, "dept": dept, "credits": 0, "type": "", "code": "", "teacher": ""})

    elif tool_name in ("find_similar_courses", "get_course_knowledge_map"):
        # - 深度學習程式設計（通訊工程學系，3學分） [共享概念：8 個]
        for m in re.finditer(r'-\s*(.+?)（([^，）]+)(?:，(\d+)學分)?）', text):
            name = m.group(1).strip()
            dept = m.group(2).strip()
            credits = int(m.group(3)) if m.group(3) else 0
            if name and not name.startswith('[') and len(name) >= 2:
                courses.append({"name": name, "dept": dept, "credits": credits, "type": "", "code": "", "teacher": ""})

    elif tool_name == "get_depts_by_tech":
        # 相關課程（前 10 門）：
        #   - Python程式設計（機械工程學系）
        in_courses = False
        for line in text.splitlines():
            if '相關課程' in line:
                in_courses = True
                continue
            if not in_courses:
                continue
            m = re.match(r'\s*-\s*(.+?)（(.+?)）', line)
            if m:
                name, dept = m.group(1).strip(), m.group(2).strip()
                if name and len(name) >= 2:
                    courses.append({"name": name, "dept": dept, "credits": 0, "type": "", "code": "", "teacher": ""})

    return courses


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
                }
    elif tool_name in ("get_dept_courses", "get_program_courses", "get_program_info") and isinstance(result, dict):
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
                }
    elif tool_name in ("ppr_explore", "find_similar_courses",
                       "get_course_knowledge_map", "get_depts_by_tech") and isinstance(result, str):
        for c in _parse_courses_from_str(tool_name, result):
            name = c["name"]
            if name and name not in course_pool:
                course_pool[name] = c

    elif tool_name == "get_course_detail" and isinstance(result, dict):
        if result.get("ambiguous"):
            cname = result.get("name_zh", "")
            for c in result.get("candidates", []):
                key = c.get("course_code") or cname
                if key and key not in course_pool:
                    course_pool[key] = {
                        "code":    c.get("course_code", ""),
                        "name":    cname,
                        "dept":    c.get("dept", ""),
                        "credits": c.get("credits", 0),
                        "type":    "",
                        "teacher": c.get("teacher", ""),
                    }
        else:
            name = result.get("name_zh", "")
            if name and name not in course_pool:
                course_pool[name] = {
                    "code":    result.get("course_code", ""),
                    "name":    name,
                    "dept":    result.get("dept", ""),
                    "credits": result.get("credits", 0),
                    "type":    "",
                    "teacher": result.get("teacher", ""),
                }

    elif tool_name == "get_teacher_info" and isinstance(result, dict):
        teacher = result.get("teacher_name", "")
        for c in result.get("courses", []):
            name = c.get("name", "")
            if name and name not in course_pool:
                course_pool[name] = {
                    "code":    c.get("id", ""),
                    "name":    name,
                    "dept":    "",
                    "credits": c.get("credits") or 0,
                    "type":    c.get("relation", ""),
                    "teacher": teacher,
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
            **_build_completion_params(max_completion_tokens=MAX_TOKENS)
        )
        total_input  += response.usage.prompt_tokens
        total_output += response.usage.completion_tokens
        msg = response.choices[0].message

        if not msg.tool_calls:
            answer = msg.content or ""
            _enrich_course_cards(list(course_pool.values()))
            course_cards, answer = _extract_courses_from_tags(answer, course_pool)
            return {
                "answer":            answer,
                "tools_used":        tools_used,
                "sources":           sources,
                "course_cards":      course_cards,
                "course_pool":       list(course_pool.values()),
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
        **_build_completion_params(max_completion_tokens=MAX_TOKENS)
    )
    total_input  += final.usage.prompt_tokens
    total_output += final.usage.completion_tokens
    answer = final.choices[0].message.content or ""
    _enrich_course_cards(list(course_pool.values()))
    course_cards, answer = _extract_courses_from_tags(answer, course_pool)
    return {
        "answer":            answer,
        "tools_used":        tools_used,
        "sources":           sources,
        "course_cards":      course_cards,
        "course_pool":       list(course_pool.values()),
        "course_pool_count": len(course_pool),
        "has_large_result":  has_large_result,
        "model":             deployment,
        "input_tokens":      total_input,
        "output_tokens":     total_output,
    }


def stream_with_tools(
    question: str,
    history: Optional[list[dict]] = None,
    context_hint: str = "",
    max_rounds: int = 4,
):
    """
    Streaming ReAct Tool-Use：逐字 yield SSE JSON 字串。

    事件格式（每行 "data: {...}\\n\\n"）：
      {"type": "tool_start", "tool": "search_courses"}
      {"type": "tool_done",  "tool": "search_courses", "count": 8}
      {"type": "token",      "text": "根據..."}
      {"type": "done",       "session_id": "", "tools_used": [...],
       "course_cards": [...], "course_pool": [...],
       "course_pool_count": N, "has_large_result": bool,
       "model": "...", "input_tokens": N, "output_tokens": N}
      {"type": "error",      "message": "..."}
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
    course_pool: dict[str, dict] = {}
    has_large_result = False
    total_input = total_output = 0
    debug_trace_calls: list[dict] = []

    def _evt(data: dict) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    try:
        for _ in range(max_rounds):
            response = client.chat.completions.create(
                model=deployment,
                messages=[{"role": "system", "content": system}] + messages,
                tools=TOOLS,
                tool_choice="auto",
                stream=True,
                stream_options={"include_usage": True},
                **_build_completion_params(max_completion_tokens=MAX_TOKENS)
            )

            # 累積 streaming 回應
            tc_buffer: dict[int, dict] = {}   # index → {id, name, arguments}
            content_parts: list[str] = []
            finish_reason = None

            for chunk in response:
                if not chunk.choices:
                    # 部分 provider 會在最後一個 chunk 只帶 usage
                    if hasattr(chunk, "usage") and chunk.usage:
                        total_input  += chunk.usage.prompt_tokens or 0
                        total_output += chunk.usage.completion_tokens or 0
                    continue

                choice = chunk.choices[0]
                finish_reason = choice.finish_reason or finish_reason
                delta = choice.delta

                if delta.tool_calls:
                    for tcd in delta.tool_calls:
                        i = tcd.index
                        if i not in tc_buffer:
                            tc_buffer[i] = {"id": "", "name": "", "arguments": ""}
                        if tcd.id:
                            tc_buffer[i]["id"] = tcd.id
                        if tcd.function:
                            if tcd.function.name:
                                tc_buffer[i]["name"] += tcd.function.name
                            if tcd.function.arguments:
                                tc_buffer[i]["arguments"] += tcd.function.arguments

                if delta.content:
                    content_parts.append(delta.content)
                    yield _evt({"type": "token", "text": delta.content})

                if hasattr(chunk, "usage") and chunk.usage:
                    total_input  += chunk.usage.prompt_tokens or 0
                    total_output += chunk.usage.completion_tokens or 0

            # 沒有工具呼叫 → 最終回答完成
            if not tc_buffer:
                final_answer = "".join(content_parts)
                yield _evt({"type": "verify_start", "pool_size": len(course_pool)})
                _enrich_course_cards(list(course_pool.values()))
                course_cards, final_answer = _extract_courses_from_tags(final_answer, course_pool)
                card_names   = {c["name"] for c in course_cards}
                filtered_out = [
                    card["name"] for card in course_pool.values()
                    if card.get("name") and card["name"] not in card_names
                ]
                yield _evt({
                    "type":         "verify_done",
                    "method":       "tag",
                    "selected":     [c["name"] for c in course_cards],
                    "filtered_out": filtered_out,
                })
                yield _evt({
                    "type":              "done",
                    "final_answer":      final_answer,
                    "tools_used":        tools_used,
                    "course_cards":      course_cards,
                    "course_pool":       list(course_pool.values()),
                    "course_pool_count": len(course_pool),
                    "has_large_result":  has_large_result,
                    "model":             deployment,
                    "input_tokens":      total_input,
                    "output_tokens":     total_output,
                    "debug_trace":       {"toolCalls": debug_trace_calls},
                })
                return

            # 執行工具（並行）
            tc_list = [tc_buffer[i] for i in sorted(tc_buffer.keys())]
            for tc in tc_list:
                tools_used.append(tc["name"])
                try:
                    tc_args = json.loads(tc["arguments"] or "{}")
                except Exception:
                    tc_args = {}
                yield _evt({"type": "tool_start", "tool": tc["name"], "args": tc_args})

            with ThreadPoolExecutor() as pool:
                futures = {
                    tc["id"]: pool.submit(
                        execute_tool, tc["name"],
                        json.loads(tc["arguments"] or "{}")
                    )
                    for tc in tc_list
                }
                results = {tid: f.result() for tid, f in futures.items()}

            for tc in tc_list:
                result = results.get(tc["id"])
                _collect_course_pool(tc["name"], result, course_pool)
                count = None
                courses_found: list[str] = []
                scores: list[float] = []
                score_type: str | None = None

                if tc["name"] in ("get_dept_courses", "get_program_courses", "get_program_info") and isinstance(result, dict):
                    count = len(result.get("courses", []))
                    if count > 20:
                        has_large_result = True
                    courses_found = [
                        c.get("name") or c.get("id", "")
                        for c in result.get("courses", [])
                    ]
                elif tc["name"] == "search_courses" and isinstance(result, list):
                    count = len(result)
                    courses_found = [r.get("name_zh", "") for r in result if r.get("name_zh")]
                    if result and result[0].get("source") == "graph_tech":
                        scores = []
                        score_type = "graph_exact"
                    else:
                        scores = [r.get("distance", 0.0) for r in result if r.get("name_zh")]
                        score_type = "distance"
                elif tc["name"] in ("find_similar_courses", "get_course_knowledge_map") and isinstance(result, str):
                    import re as _re
                    for m in _re.finditer(r'-\s*(.+?)（[^）]+）\s*(?:\[共享(?:概念：|\ )(\d+)\ 個(?:概念)?\])?', result):
                        name = m.group(1).strip()
                        sc = int(m.group(2)) if m.group(2) else 0
                        if name and len(name) >= 2 and not name.startswith('['):
                            courses_found.append(name)
                            scores.append(float(sc))
                    count = len(courses_found)
                    score_type = "shared_concepts"
                elif tc["name"] == "ppr_explore" and isinstance(result, str):
                    import re as _re
                    for m in _re.finditer(r'\[課程\]\s*(.+?)（(.+?)）\s*\[PPR:\s*([\d.]+)\]', result):
                        courses_found.append(m.group(1).strip())
                        scores.append(float(m.group(3)))
                    count = len(courses_found)
                    score_type = "ppr"
                elif tc["name"] == "search_programs" and isinstance(result, list):
                    count = len(result)
                    courses_found = [r.get("program_name", "") for r in result if r.get("program_name")]
                    scores = [r.get("distance", 0.0) for r in result]
                    score_type = "distance"
                elif tc["name"] == "get_depts_by_tech" and isinstance(result, str):
                    import re as _re
                    in_courses = False
                    for line in result.splitlines():
                        if '相關課程' in line:
                            in_courses = True
                            continue
                        if not in_courses:
                            continue
                        m2 = _re.match(r'\s*-\s*(.+?)（(.+?)）', line)
                        if m2:
                            name = m2.group(1).strip()
                            if name and len(name) >= 2:
                                courses_found.append(name)
                    count = len(courses_found)

                debug_trace_calls.append({
                    "tool":         tc["name"],
                    "args":         json.loads(tc["arguments"] or "{}"),
                    "coursesFound": courses_found,
                    "count":        count,
                    "scores":       scores,
                    "scoreType":    score_type,
                })
                yield _evt({"type": "tool_done", "tool": tc["name"], "count": count,
                            "courses_found": courses_found, "scores": scores, "score_type": score_type})

            # 重建 messages
            messages.append({
                "role":    "assistant",
                "content": "".join(content_parts) or None,
                "tool_calls": [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                    for tc in tc_list
                ],
            })
            for tc in tc_list:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(results[tc["id"]], ensure_ascii=False),
                })

        # 超過最大輪數：強制串流最終回答
        final = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "system", "content": system}] + messages,
            stream=True,
            stream_options={"include_usage": True},
            **_build_completion_params(max_completion_tokens=MAX_TOKENS)
        )
        content_parts = []
        for chunk in final:
            if chunk.choices and chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                content_parts.append(text)
                yield _evt({"type": "token", "text": text})
            if hasattr(chunk, "usage") and chunk.usage:
                total_input  += chunk.usage.prompt_tokens or 0
                total_output += chunk.usage.completion_tokens or 0

        final_answer = "".join(content_parts)
        yield _evt({"type": "verify_start", "pool_size": len(course_pool)})
        _enrich_course_cards(list(course_pool.values()))
        course_cards, final_answer = _extract_courses_from_tags(final_answer, course_pool)
        card_names   = {c["name"] for c in course_cards}
        filtered_out = [
            card["name"] for card in course_pool.values()
            if card.get("name") and card["name"] not in card_names
        ]
        yield _evt({
            "type":         "verify_done",
            "method":       "tag",
            "selected":     [c["name"] for c in course_cards],
            "filtered_out": filtered_out,
        })
        yield _evt({
            "type":              "done",
            "final_answer":      final_answer,
            "tools_used":        tools_used,
            "course_cards":      course_cards,
            "course_pool":       list(course_pool.values()),
            "course_pool_count": len(course_pool),
            "has_large_result":  has_large_result,
            "model":             deployment,
            "input_tokens":      total_input,
            "output_tokens":     total_output,
            "debug_trace":       {"toolCalls": debug_trace_calls},
        })

    except Exception as exc:
        yield _evt({"type": "error", "message": str(exc)})
