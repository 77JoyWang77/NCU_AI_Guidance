"""
run_agent4_simplify.py  —  Agent 4：概念高中生友善化

針對 nlp_tech_nodes.json 中每門課的 concepts，
改寫成高中生能理解的說法（方案 A+B）：
  A：換成淺白的中文詞彙
  B：優先與高中課程連結（數學、物理、化學、生物、地科、資訊）

依開課學院自動分類，使用對應的 prompt 示範範例（共 11 類）。

輸入：data/processed/nlp_tech_nodes.json
輸出：data/processed/nlp_simplified_concepts.json

格式：
{
  "課號": {
    "simplified_concepts": [
      {"original": "梯度下降", "display": "最佳化方法（高中數學：最小值）"},
      {"original": "六書", "display": "漢字六種造字原則（高中國文：文字學）"},
      {"original": "市場區隔與定位", "display": "把消費者分群再決定產品定位的策略"}
    ],
    "college": "eecs"
  }
}

模型：Qwen3-14B-AWQ，via vLLM openai-compatible API
      預設端點：http://localhost:8000/v1
      啟動指令：vllm serve Qwen/Qwen3-14B-AWQ --max-model-len 8192 --gpu-memory-utilization 0.8
"""

import json
import re
import sys
from pathlib import Path

from openai import OpenAI

BASE      = Path(__file__).parent.parent.parent
IN_PATH   = BASE / "data" / "processed" / "nlp_tech_nodes.json"
OUT_PATH  = BASE / "data" / "processed" / "nlp_simplified_concepts.json"

sys.path.insert(0, str(BASE / "scripts" / "nlp"))
from course_classifier import classify_course  # noqa: E402

# ── 後端設定（vLLM）─────────────────────────────────────────
MODEL    = "Qwen/Qwen3-14B-AWQ"
API_BASE = "http://localhost:8000/v1"
API_KEY  = "token-abc"
BACKEND  = "vllm"
# ─────────────────────────────────────────────────────────────

NUM_CTX = 8192

# ── 學院識別關鍵字（越特殊的放越前面，避免被通用詞截走）────────
COLLEGE_KEYWORDS = {
    "biomedical":  ["生醫", "生物醫學", "系統生物", "轉譯醫學", "認知神經", "神經科學"],
    "life_sci":    ["生命科學"],
    "sustain":     ["永續", "綠能", "能源工程"],
    "earth_space": ["地球科學", "地球系統", "大氣科學", "天文", "太空", "水文與海洋",
                    "應用地質", "遙測"],
    "chemistry":   ["化學學系", "化學工程"],
    "math_phys":   ["數學系", "物理學系", "統計研究所", "理學院學士班"],
    "eecs":        ["資訊工程", "資訊管理", "電機工程", "光電科學", "通訊工程",
                    "資訊電機", "人工智慧", "計算機"],
    "engineering": ["土木工程", "機械工程", "材料科學", "工業管理", "環境工程",
                    "工學院", "能源工程", "化工"],
    "social_law":  ["法律", "師資培育", "學習與教學", "網路學習科技", "亞際文化",
                    "社會科學"],
    "management":  ["管理", "企業", "經濟", "會計", "財務", "人力資源", "產業經濟"],
    "liberal_arts":["文學", "哲學", "歷史", "語文", "語言", "藝術", "客家",
                    "法國", "英美"],
}

# ── 課名二層偵測：特定跨域系所依課程名稱進一步細分 ─────────────
# 格式：{系所名稱: [(課名關鍵字列表, 對應類別), ...], 預設類別}
DEPT_COURSE_OVERRIDES: dict[str, tuple[list[tuple[list[str], str]], str]] = {
    "客家語文暨社會科學學系": (
        [
            (["語音", "客語", "音韻", "語言學", "語言綜", "閩南語", "文法", "詞彙", "文學", "民間", "雙語教學"], "liberal_arts"),
            (["社會", "政治", "行政", "文化人類", "田野", "族群", "認同", "食農", "環境政策"], "social_law"),
        ],
        "social_law",   # 其他課（如傳播行銷）預設 social_law
    ),
    "文學院學士班": (
        [
            (["電影", "影像", "拍攝", "剪輯", "動態影像", "紀錄片", "劇場", "舞台"], "film_media"),
        ],
        "liberal_arts",
    ),
    "英美語文學系": (
        [
            (["性別", "女性主義", "酷兒", "亞際", "後殖民", "族裔"], "social_law"),
        ],
        "liberal_arts",
    ),
    "產業經濟研究所碩士班": (
        [
            (["法", "憲法", "公平交易", "法學", "訴訟"], "social_law"),
        ],
        "management",
    ),
    "財務金融學系": (
        [
            (["民法", "公司法", "法律", "法制"], "social_law"),
        ],
        "management",
    ),
}

# ── 各學院專屬 prompt 範例（根據實際資料整理）────────────────
COLLEGE_EXAMPLES = {
    "eecs": """\
輸入概念 → display 範例（資訊電機領域）：
- 演算法 → 解決問題的步驟規則（高中資訊）
- 資料結構 → 儲存與整理資料的方式（高中資訊）
- 卷積神經網路 → CNN，辨識影像的 AI 模型
- 電路分析 → 計算電流與電壓的方法（高中物理：電路）
- 訊號處理 → 分析電波與音訊的技術（高中物理：波動）
- 作業系統排程 → 電腦分配工作順序的機制
- 編譯器 → 把程式碼轉成電腦能執行的工具
- 幾何光學 → 研究光線折射與反射規律的學問（高中物理：光學）""",

    "engineering": """\
輸入概念 → display 範例（工程領域）：
- 熱力學 → 研究熱與能量轉換規律（高中物理）
- 材料力學 → 研究材料受力後如何變形
- 有限元素法 → 把複雜結構切成小區塊分析的計算法
- 流體力學 → 研究液體與氣體流動規律（高中物理）
- 要徑法 → 找出工程專案最長關鍵路徑的排程方法
- BIM → 建築資訊模型，建築的 3D 數位雙胞胎
- 混凝土配比 → 決定水泥砂石比例以控制強度的技術
- EOQ模型 → 計算最佳一次訂貨量的庫存模型""",

    "math_phys": """\
輸入概念 → display 範例（數學/物理/統計領域）：
- 微積分 → 計算變化率與面積的數學工具（高中數學進階）
- 線性代數 → 矩陣與向量空間的數學（高中數學：向量）
- 牛頓定律 → 描述力與運動關係的基本定律（高中物理）
- 量子力學 → 描述微觀粒子行為的物理理論
- 馬爾可夫鏈 → 根據當前狀態預測下一狀態的機率模型（高中數學：機率）
- 傅立葉轉換 → 把訊號分解為不同頻率的數學工具（高中物理：波動）
- 特徵值 → 矩陣作用下保持方向不變的縮放量
- 泊松過程 → 描述隨機事件在時間內發生次數的機率模型""",

    "chemistry": """\
輸入概念 → display 範例（化學領域）：
- 原子結構 → 質子中子電子的排列方式（高中化學）
- 週期性與原子結構 → 元素週期表背後的規律（高中化學）
- 酸與鹼 → 酸鹼反應與 pH 值（高中化學）
- 熱化學 → 化學反應的能量變化（高中化學：反應熱）
- 相圖 → 描述物質在不同溫壓下狀態的圖（高中化學：相變）
- 有機化學 → 含碳化合物的結構與反應（高中化學）
- 色層分析法 → 利用物質移動速度不同來分離混合物的技術
- 立體化學 → 研究分子三維空間結構的化學分支""",

    "life_sci": """\
輸入概念 → display 範例（生命科學領域）：
- 細胞結構 → 細胞的基本組成與構造（高中生物）
- 演化 → 物種隨時間改變的過程（高中生物）
- 生態學 → 生物與環境的交互關係（高中生物）
- 細胞間通訊 → 細胞接收外部訊號並做出反應的機制（高中生物）
- DNA複製 → DNA 在細胞分裂前自我複製的過程（高中生物）
- 遺傳機制 → 基因如何傳遞給下一代（高中生物）
- 基因表現 → DNA 如何指導蛋白質合成（高中生物）
- 微生物分類 → 依形態與基因將微生物歸類的方法""",

    "biomedical": """\
輸入概念 → display 範例（生醫/神經科學領域）：
- 基因表現 → DNA 如何指導蛋白質合成（高中生物）
- 細胞訊號傳遞 → 細胞接收外部指令並做出反應的機制
- 磁振造影 → MRI，利用磁場偵測體內結構的醫學影像技術
- 影像分割 → 自動圈出醫學影像中病灶的技術
- 傅立葉轉換 → 分析生理訊號頻率成分（高中物理：波動）
- 記憶編碼 → 大腦將資訊轉為長期記憶的過程（高中生物）
- 腦機介面 → 讓大腦直接控制外部裝置的技術
- 幹細胞 → 能分化成各種細胞類型的原始細胞（高中生物）""",

    "earth_space": """\
輸入概念 → display 範例（地球科學/太空領域）：
- 板塊構造 → 地球岩石圈移動的理論（高中地科）
- 地震波 → 地震產生用來探測地球內部的波（高中物理：波動）
- 大氣環流 → 全球大氣流動的規律，影響氣候（高中地科）
- 氣候變遷 → 人為溫室氣體導致全球暖化的現象（高中地科）
- 黑體輻射 → 物體因溫度發出電磁輻射的現象（高中物理）
- 重力測量 → 量測各地重力差異來推算地球內部構造
- 傅立葉轉換 → 分析地震波頻率成分（高中物理：波動）
- 地下水 → 儲存在地層孔隙中的水資源（高中地科）""",

    "sustain": """\
輸入概念 → display 範例（永續/綠能領域）：
- 永續發展目標(SDG) → 聯合國訂定的 17 項全球永續目標（高中社會）
- 淨零排放 → 碳排放量與碳吸收量相等的狀態
- 循環經濟 → 讓資源循環使用、減少廢棄物的經濟模式
- 電池儲能 → 用電池儲存多餘電力供需要時使用（高中物理：電路）
- 碳封存 → 將二氧化碳捕捉並永久儲存地下的技術
- 燃料電池 → 將氫氣轉換成電能的發電裝置（高中化學：氧化還原）
- 內部碳定價 → 企業內部對碳排放訂定價格以促進減排
- RE100 → 企業承諾 100% 使用再生能源的國際倡議""",

    "management": """\
輸入概念 → display 範例（管理商學領域）：
- 財務報表分析 → 讀懂公司財務狀況的方法
- 折現現金流量評價 → 計算未來錢現在值多少的方法
- 市場區隔與定位 → 把消費者分群再決定產品定位的策略
- 供應鏈管理 → 從原料到消費者的全流程協調（高中社會：產業鏈）
- 組織行為 → 研究人在組織中的行為規律
- 線性規劃 → 在限制條件下求最佳解（高中數學）
- 產品生命週期 → 產品從推出到退出市場的四個階段
- ERP → 整合公司各部門資訊的管理系統""",

    "social_law": """\
輸入概念 → display 範例（法律/社會科學/教育領域）：
- 公司法 → 規範公司設立與運作的法律（高中公民）
- 行政法 → 規範政府機關行為的法律（高中公民）
- 建構主義教學 → 讓學生主動建構知識的教學方法
- 認知發展理論 → 研究兒童如何學習與思考的理論
- 社會流動 → 個人在社會階層中往上或往下移動的現象（高中社會）
- 質性研究 → 用訪談觀察等方式深入理解社會現象的研究方法
- 行為取向學習理論 → 透過刺激與反應解釋學習的理論（高中心理概念）
- 信度與效度 → 研究測量工具的準確性與一致性""",

    "liberal_arts": """\
輸入概念 → display 範例（人文語言領域）：
- 六書 → 漢字六種造字原則（高中國文：文字學）
- 積極修辭 → 運用比喻排比等增強表達效果的技巧（高中國文）
- 音韻、聲母、韻母 → 分析語音結構的系統（高中：注音符號）
- 田野調查 → 親赴現場收集第一手資料的研究方法
- 語碼轉換 → 說話者在不同語言或方言間切換的現象
- 民族誌 → 深入描述某文化群體生活方式的研究報告
- 文學思潮 → 某時代影響文學創作方向的主流觀念
- 政治意識形態 → 對社會應如何組織運作的系統性信念""",

    "film_media": """\
輸入概念 → display 範例（電影/媒體/劇場領域）：
- 分鏡 → 拍攝前規劃每個鏡頭畫面的圖表
- 場面調度 → 導演安排畫面中人物與物件的方式
- 類型電影 → 依主題分類的電影格式（西部片、恐怖片等）
- 剪輯藝術 → 將鏡頭組合成完整故事的後製技術
- 舞台設計 → 規劃劇場視覺環境與道具的藝術工作
- 敘事結構 → 故事的開展與組織方式（高中國文）
- 聲音設計 → 為影像搭配音效與音樂的技術
- 台灣新電影 → 1980年代起台灣電影的寫實主義風潮""",

    "default": """\
輸入概念 → display 範例（通用）：
- 機率統計 → 分析數據與預測事件可能性（高中數學）
- 資料視覺化 → 把數字轉成圖表讓人一眼理解
- 機器學習 → 讓電腦從數據自動學習的技術
- 永續發展 → 不破壞環境地滿足人類需求（高中地理）
- 田野調查 → 親赴現場收集第一手資料的研究方法
- 量子力學 → 描述微觀粒子行為的物理理論
- 法律解釋學 → 分析法條文字如何被理解與適用""",
}

PROMPT_BASE = """\
你是一個幫助高中生認識大學課程的助手。
請將以下大學課程的技術概念，改寫成台灣高中生能理解的簡短說法。
所有輸出必須使用繁體中文，不得使用簡體中文。

課程名稱：{course_name}
開課系所：{dept}

{college_examples}

概念列表：
{concepts}

改寫原則（依優先順序）：
1. 若概念與台灣高中課程直接相關，加上科目標示，例如「（高中數學）」
2. 若無高中課程連結，用最簡短的淺白說法描述用途或定義
3. 若概念已夠淺顯或是工具名稱（Python、Excel、Git 等），display 直接等於 original

輸出格式（只輸出 JSON，不要有其他文字，不要有 markdown）：
{{
  "simplified_concepts": [
    {{"original": "原始概念", "display": "高中生友善說法"}}
  ]
}}

規則：
- display 限 20 字以內，不要用句子說故事，要像詞條說明
- 不需要每個都加括號，有高中連結才加
- 所有輸出必須使用繁體中文，不得使用簡體中文"""


def detect_college(dept: str, course_name: str = "") -> str:
    """
    判斷課程的學院類別，兩層偵測：
    1. 若系所在 DEPT_COURSE_OVERRIDES 中，依課程名稱關鍵字細分
    2. 否則依 COLLEGE_KEYWORDS 系所關鍵字判斷
    """
    # 第一層：特定跨域系所的課名細分
    if dept in DEPT_COURSE_OVERRIDES:
        rules, fallback = DEPT_COURSE_OVERRIDES[dept]
        for keywords, college in rules:
            if any(kw in course_name for kw in keywords):
                return college
        return fallback

    # 第二層：系所關鍵字判斷
    for college, keywords in COLLEGE_KEYWORDS.items():
        if any(kw in dept for kw in keywords):
            return college
    # 理學院精確匹配（避免「管理學院」誤命中「理學」）
    if dept in ("理學院", "理學院學士班"):
        return "math_phys"
    return "default"


def simplify_concepts(client: OpenAI, course_name: str, dept: str,
                      concepts: list[str]) -> list[dict] | None:
    if not concepts:
        return None

    college = detect_college(dept, course_name)
    examples = COLLEGE_EXAMPLES[college]
    concepts_str = "\n".join(f"- {c}" for c in concepts)

    prompt = PROMPT_BASE.format(
        course_name=course_name,
        dept=dept,
        college_examples=examples,
        concepts=concepts_str,
    )

    try:
        kwargs = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }
        if BACKEND == "ollama":
            kwargs["extra_body"] = {"options": {"num_ctx": NUM_CTX}}
        resp = client.chat.completions.create(**kwargs)
        raw = resp.choices[0].message.content.strip()
        # 寫入 debug log
        with open(BASE / "logs" / "agent4_llm_debug.txt", "a", encoding="utf-8") as dbg:
            dbg.write(f"\n{'='*60}\n[{course_name}] [{college}]\n{raw}\n")
        # 移除 Qwen3 thinking block
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        parsed = json.loads(raw)
        return parsed.get("simplified_concepts", [])
    except json.JSONDecodeError as e:
        print(f"  JSON 解析失敗：{e}，raw={repr(raw[:100])}")
        return "error"
    except Exception as e:
        print(f"  LLM 錯誤：{e}")
        return "error"


def load_courses() -> dict:
    """載入原始課程資料，補充課程名稱與系所。"""
    RAW_DIRS = [
        BASE / "data" / "raw" / "courses",
        BASE / "data" / "raw" / "graduate_courses",
    ]
    courses = {}
    sep = re.compile(r"-[A-Z0-9*]+$")
    for raw_dir in RAW_DIRS:
        if not raw_dir.exists():
            continue
        for json_file in sorted(raw_dir.rglob("*.json")):
            try:
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            items = data if isinstance(data, list) else data.get("courses", [])
            for c in items:
                code = sep.sub("", c.get("課號-班別", "").strip())
                if code and code not in courses:
                    courses[code] = c
    return courses


def main():
    print("Agent 4：概念高中生友善化")
    print(f"模型：{MODEL}  端點：{API_BASE}")

    with open(IN_PATH, encoding="utf-8") as f:
        tech_nodes: dict = json.load(f)
    print(f"載入 nlp_tech_nodes：{len(tech_nodes)} 筆")

    courses = load_courses()
    print(f"載入課程資料：{len(courses)} 門")

    # 斷點續跑
    if OUT_PATH.exists():
        with open(OUT_PATH, encoding="utf-8") as f:
            results: dict = json.load(f)
        print(f"載入已有結果：{len(results)} 筆，從斷點繼續")
    else:
        results: dict = {}

    to_process = [
        code for code, v in tech_nodes.items()
        if v.get("concepts")
        and not v.get("skipped")
        and (code not in results or results[code].get("error"))
    ]
    print(f"待處理：{len(to_process)} 門")

    # 統計各學院分布
    college_dist: dict[str, int] = {}
    for code in to_process:
        dept   = courses.get(code, {}).get("系所", courses.get(code, {}).get("department", ""))
        cname  = courses.get(code, {}).get("課程名稱(中文)", "")
        c = detect_college(dept, cname)
        college_dist[c] = college_dist.get(c, 0) + 1
    for col, cnt in sorted(college_dist.items(), key=lambda x: -x[1]):
        print(f"  {col}: {cnt} 門")

    client = OpenAI(base_url=API_BASE, api_key=API_KEY)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    for i, code in enumerate(to_process, 1):
        v        = tech_nodes[code]
        course   = courses.get(code, {})
        name     = course.get("課程名稱(中文)", code)
        dept     = course.get("系所", course.get("department", ""))
        concepts = v.get("concepts", [])

        simplified = simplify_concepts(client, name, dept, concepts)

        if simplified is None:
            results[code] = {"simplified_concepts": [], "skipped": True}
        elif simplified == "error":
            results[code] = {"simplified_concepts": [], "error": True}
        else:
            results[code] = {
                "simplified_concepts": simplified,
                "college": detect_college(dept, name),
            }

        if i % 50 == 0:
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"  [{i}/{len(to_process)}] 已存檔")

        if i % 10 == 0:
            print(f"  [{i}/{len(to_process)}] {name[:30]}")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    non_empty = sum(1 for v in results.values() if v.get("simplified_concepts"))
    print(f"\n完成：{len(results)} 筆，其中 {non_empty} 筆有友善化概念")
    print(f"輸出：{OUT_PATH}")


if __name__ == "__main__":
    main()
