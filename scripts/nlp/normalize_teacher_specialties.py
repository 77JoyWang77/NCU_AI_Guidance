"""
normalize_teacher_specialties.py

從 data/raw/114_ulistteacher.csv 整理教師專長，輸出：
  data/processed/dept_professor_map.json

格式：
{
  "資訊工程學系": {
    "specialty_vocab": ["機器學習", "深度學習", ...],   // 該系所所有教授專長的聯集
    "professors": [
      {"name": "陳某某", "rank": "教授", "employment": "專任", "specialties": ["機器學習", ...]}
    ]
  }
}

specialty_vocab 作為 Agent 2 教授專長領域匹配的「可選詞彙表」。
"""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).parent.parent.parent
CSV_PATH  = BASE / "data" / "raw" / "114_ulistteacher.csv"
OUT_PATH  = BASE / "data" / "processed" / "dept_professor_map.json"

# 分隔符：逗號、頓號、分號、全形分號、斜線
SEP = re.compile(r"[,，、；;/]+")

# 職級正規化
RANK_MAP = {
    "教授":     "教授",
    "副教授":   "副教授",
    "助理教授": "助理教授",
    "講師":     "講師",
    "研究員":   "研究員",
    "副研究員": "副研究員",
    "助理研究員": "助理研究員",
}


def parse_specialties(raw: str) -> list[str]:
    """切割並清理教師專長字串，回傳專長列表。"""
    if not raw or raw.strip() == "-":
        return []
    parts = SEP.split(raw)
    result = []
    for p in parts:
        p = p.strip().strip('"').strip()
        if p and p != "-":
            result.append(p)
    return result


def normalize_rank(raw: str) -> str:
    """正規化職級欄位。"""
    for key in RANK_MAP:
        if key in raw:
            return RANK_MAP[key]
    return raw.strip()


def main():
    if not CSV_PATH.exists():
        print(f"找不到 CSV：{CSV_PATH}")
        return

    # dept_name → {professors: [], specialty_set: set()}
    dept_map: dict[str, dict] = defaultdict(lambda: {"professors": [], "specialty_set": set()})

    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dept = row.get("系所名稱", "").strip()
            name = row.get("教師名稱", "").strip()
            rank_raw = row.get("聘書職級", "").strip()
            employment = row.get("專兼任", "").strip()
            specialty_raw = row.get("教師專長", "").strip()

            if not dept or not name:
                continue

            specialties = parse_specialties(specialty_raw)
            rank = normalize_rank(rank_raw)

            dept_map[dept]["professors"].append({
                "name": name,
                "rank": rank,
                "employment": employment,
                "specialties": specialties,
            })
            dept_map[dept]["specialty_set"].update(specialties)

    # 轉換成最終格式（set → sorted list）
    output: dict[str, dict] = {}
    for dept, data in sorted(dept_map.items()):
        output[dept] = {
            "specialty_vocab": sorted(data["specialty_set"]),
            "professors": data["professors"],
        }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 統計
    total_profs = sum(len(v["professors"]) for v in output.values())
    total_vocab = sum(len(v["specialty_vocab"]) for v in output.values())
    print(f"完成：{len(output)} 個系所，{total_profs} 位教師")
    print(f"各系所專長詞彙總計：{total_vocab} 條（含重複跨系所）")
    print(f"輸出：{OUT_PATH}")


if __name__ == "__main__":
    main()
