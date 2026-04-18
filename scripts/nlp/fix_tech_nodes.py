"""
fix_tech_nodes.py  —  修復 nlp_tech_nodes.json

1. 簡體字 → 繁體字（opencc，若未安裝則跳過）
2. 英文 concept → 繁體中文翻譯（Qwen3-14B-AWQ via vLLM）
   - 純英文縮寫（CNN/RNN 等）保留縮寫並加中文說明
   - 工具/框架名稱（Python/Docker 等）保持英文
   - 一般技術概念翻成繁體中文

輸入：data/processed/nlp_tech_nodes.json
輸出：data/processed/nlp_tech_nodes.json（覆寫，原檔備份至 nlp_tech_nodes.bak.json）

模型：Qwen3-14B-AWQ，via vLLM openai-compatible API
      預設端點：http://localhost:8000/v1
"""

import json
import re
import shutil
from pathlib import Path

from openai import OpenAI

BASE     = Path(__file__).parent.parent.parent
IN_PATH  = BASE / "data" / "processed" / "nlp" / "nlp_tech_nodes.json"
BAK_PATH = BASE / "data" / "processed" / "nlp" / "nlp_tech_nodes.bak.json"

# ── 後端設定（vLLM）─────────────────────────────────────────
MODEL    = "Qwen/Qwen3-14B-AWQ"
API_BASE = "http://localhost:8000/v1"
API_KEY  = "token-abc"
# ─────────────────────────────────────────────────────────────

# 批次大小：每次送給 LLM 翻譯的術語數
BATCH_SIZE = 30

TRANSLATE_PROMPT = """\
你是一個技術術語翻譯助手。
請將以下英文（或中英混雜）技術名詞逐一翻譯成繁體中文。
所有輸出必須使用繁體中文，不得使用簡體中文。

術語列表：
{terms}

輸出格式（只輸出 JSON，不要有其他文字，不要有 markdown）：
{{"translations": {{"原文1": "翻譯1", "原文2": "翻譯2"}}}}

翻譯規則：
- 常見英文縮寫（CNN、RNN、LSTM、GAN、SVM、KNN、PCA 等）：保留縮寫並加中文，例如 "CNN（卷積神經網路）"
- 工具/框架/軟體名稱（Python、Docker、Git、PyTorch、MATLAB 等）：保持英文原文不翻譯
- 一般技術概念：直接翻成繁體中文
- 中英混雜的詞（如 "G20/OECD公司治理原則"）：保持原文中文部分，英文縮寫不翻
- 若原文已是繁體中文，直接原文回傳"""


def has_english(text: str) -> bool:
    """判斷字串是否含有需要翻譯的英文（排除純縮寫夾在中文裡的情況）。"""
    return bool(re.search(r'[a-zA-Z]{2,}', text))


def convert_to_traditional(text: str, converter) -> str:
    """用 opencc 轉繁體，若 converter 為 None 則原文回傳。"""
    if converter is None:
        return text
    return converter.convert(text)


def translate_batch(client: OpenAI, terms: list[str]) -> dict[str, str]:
    """送一批英文術語給 LLM 翻譯，回傳 {原文: 翻譯} dict。"""
    terms_str = "\n".join(f"- {t}" for t in terms)
    prompt = TRANSLATE_PROMPT.format(terms=terms_str)

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        parsed = json.loads(raw)
        return parsed.get("translations", {})
    except Exception as e:
        print(f"  翻譯批次失敗：{e}")
        return {}


def main():
    print("fix_tech_nodes.py：修復簡體字與英文術語")

    # 嘗試載入 opencc
    converter = None
    try:
        import opencc
        converter = opencc.OpenCC("s2tw")
        print("opencc 載入成功，將執行簡轉繁")
    except ImportError:
        print("未安裝 opencc，跳過簡轉繁（可執行：pip install opencc-python-reimplemented）")

    # 備份原檔
    shutil.copy(IN_PATH, BAK_PATH)
    print(f"已備份原檔至 {BAK_PATH.name}")

    with open(IN_PATH, encoding="utf-8") as f:
        data: dict = json.load(f)
    print(f"載入 {len(data)} 筆課程資料")

    # ── Step 1：收集所有需要翻譯的英文術語（去重）────────────────
    all_en_terms: set[str] = set()
    for v in data.values():
        for field in ("concepts", "tools"):
            for term in v.get(field, []):
                if has_english(term):
                    all_en_terms.add(term)

    print(f"找到含英文的術語：{len(all_en_terms)} 個，開始批次翻譯...")

    # ── Step 2：批次翻譯 ──────────────────────────────────────────
    client = OpenAI(base_url=API_BASE, api_key=API_KEY)
    translation_cache: dict[str, str] = {}
    term_list = sorted(all_en_terms)

    for i in range(0, len(term_list), BATCH_SIZE):
        batch = term_list[i:i + BATCH_SIZE]
        result = translate_batch(client, batch)
        translation_cache.update(result)
        print(f"  翻譯進度：{min(i + BATCH_SIZE, len(term_list))}/{len(term_list)}")

    # ── Step 3：套用翻譯 + 簡轉繁 ────────────────────────────────
    fixed_count = 0
    for code, v in data.items():
        changed = False
        for field in ("concepts", "tools", "languages"):
            new_list = []
            for term in v.get(field, []):
                # 簡轉繁
                term_tw = convert_to_traditional(term, converter)
                # 英文術語替換（concepts 和 tools 才翻，languages 保持英文）
                if field != "languages" and has_english(term_tw):
                    term_tw = translation_cache.get(term, translation_cache.get(term_tw, term_tw))
                new_list.append(term_tw)
            if new_list != v.get(field, []):
                v[field] = new_list
                changed = True
        if changed:
            fixed_count += 1

    print(f"修改了 {fixed_count} 筆課程資料")

    # ── Step 4：存檔 ──────────────────────────────────────────────
    with open(IN_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"完成，已覆寫 {IN_PATH.name}")
    print(f"若需還原，請使用備份檔 {BAK_PATH.name}")


if __name__ == "__main__":
    main()
