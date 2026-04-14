"""
postprocess_simplified.py — agent4 輸出後處理

1. 移除所有「（高中...）」標籤（含簡體/繁體變體）
2. 修正簡體字滲入：優先用 opencc 全面轉換，再用 SIMP_FIX 修正特殊詞
3. 清理多餘空白與結尾標點
4. 統計修改量

輸入/輸出：data/processed/nlp_simplified_concepts.json（覆寫）
"""

import json
import re
import shutil
from pathlib import Path

# 嘗試載入 opencc
try:
    import opencc
    _cc = opencc.OpenCC("s2tw")
    def _to_trad(text: str) -> str:
        return _cc.convert(text)
    print("opencc 載入成功，將用 opencc 轉繁體")
except ImportError:
    _cc = None
    def _to_trad(text: str) -> str:
        return text
    print("未安裝 opencc，僅用字典修正（建議：pip install opencc-python-reimplemented）")

BASE     = Path(__file__).parent.parent.parent
IN_PATH  = BASE / "data" / "processed" / "nlp_simplified_concepts.json"
BAK_PATH = BASE / "data" / "processed" / "nlp_simplified_concepts.bak.json"

# ── 移除高中標籤的 regex ─────────────────────────────────────
# 匹配：（高中XX）、(高中XX)、（高中XX、XX）等變體
HS_TAG = re.compile(
    r'[（(]\s*高中[^）)]*[）)]'
)

# ── 簡體字修正對照表 ──────────────────────────────────────────
SIMP_FIX = {
    "高中语文": "高中國文",
    "语文":  "國文",   "语言":  "語言",   "语法":  "語法",
    "语音":  "語音",   "语义":  "語義",   "语境":  "語境",
    "语气":  "語氣",   "语态":  "語態",
    "认知":  "認知",   "认识":  "認識",   "认为":  "認為",
    "结构":  "結構",   "结果":  "結果",   "结合":  "結合",
    "统计":  "統計",   "统一":  "統一",
    "应用":  "應用",   "应该":  "應該",
    "数据":  "數據",   "数字":  "數字",   "数学":  "數學",
    "实验":  "實驗",   "实践":  "實踐",   "实现":  "實現",
    "电力":  "電力",   "电气":  "電氣",   "电路":  "電路",
    "电子":  "電子",
    "沥青":  "瀝青",   "铺设":  "鋪設",   "压实":  "壓實",
    "词语":  "詞語",   "短语":  "短語",   "词汇":  "詞彙",
    "对称":  "對稱",   "对比":  "對比",   "对象":  "對象",
    "分析":  "分析",   "过程":  "過程",   "过去":  "過去",
    "时间":  "時間",   "时态":  "時態",
    "学习":  "學習",   "学生":  "學生",
    "问题":  "問題",   "关系":  "關係",   "关联":  "關聯",
    "设计":  "設計",   "变化":  "變化",   "发展":  "發展",
}


def fix_simplified_chinese(text: str) -> str:
    # 先用 opencc 做全面轉換
    text = _to_trad(text)
    # 再用字典修正 opencc 可能處理不佳的特殊詞
    for simp, trad in SIMP_FIX.items():
        text = text.replace(simp, trad)
    return text


def clean_display(display: str) -> str:
    """移除高中標籤、修正簡體字、清理多餘空白。"""
    # 1. 移除高中標籤
    text = HS_TAG.sub("", display).strip()
    # 2. 修正簡體字（opencc + 字典）
    text = fix_simplified_chinese(text)
    # 3. 清理多餘空白（移除標籤後可能留下的空格）
    text = re.sub(r"\s{2,}", " ", text).strip()
    # 4. 移除結尾多餘的標點
    text = text.rstrip("，。、 ")
    return text


def main():
    if not IN_PATH.exists():
        print(f"找不到 {IN_PATH.name}，請先執行 run_agent4_simplify.py")
        return

    shutil.copy(IN_PATH, BAK_PATH)
    print(f"已備份至 {BAK_PATH.name}")

    with open(IN_PATH, encoding="utf-8") as f:
        data: dict = json.load(f)
    print(f"載入 {len(data)} 筆")

    changed_courses = 0
    changed_items   = 0

    for code, v in data.items():
        if not v.get("simplified_concepts"):
            continue
        modified = False
        for item in v["simplified_concepts"]:
            original_display = item.get("display", "")
            new_display = clean_display(original_display)
            if new_display != original_display:
                item["display"] = new_display
                changed_items += 1
                modified = True
        if modified:
            changed_courses += 1

    with open(IN_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"修改了 {changed_courses} 門課程、{changed_items} 個 display")
    print(f"完成，已覆寫 {IN_PATH.name}")


if __name__ == "__main__":
    main()
