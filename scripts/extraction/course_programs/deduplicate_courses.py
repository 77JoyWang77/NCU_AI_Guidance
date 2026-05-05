"""
deduplicate_courses.py — 建立正規化課程 canonical JSON

去重規則：
  Key = 課號-班別（完整字串，含班別後綴，如 CE1001-A、CE1001-B、CE1001-*）
  同一 Key 出現多次時，優先順序（高者蓋低者）：
    scraped_missing（最低）→ 114_1 → 114_2（最高）

輸出（保持 raw 欄位格式，與 courses.py convert_course_format 相容）：
  data/processed/courses_deduped/undergrad.json
  data/processed/courses_deduped/grad.json

用法：
  python scripts/rag/deduplicate_courses.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
RAW  = ROOT / "data" / "raw"
OUT  = ROOT / "data" / "processed" / "courses_deduped"

UNDERGRAD_DIRS = [
    ("scraped_missing", RAW / "scraped_missing" / "courses.json"),  # 單一 JSON 檔
    ("114_1",           RAW / "courses" / "114_1"),
    ("114_2",           RAW / "courses" / "114_2"),
]

GRAD_DIRS = [
    ("114_1", RAW / "graduate_courses" / "114_1"),
    ("114_2", RAW / "graduate_courses" / "114_2"),
]


def load_from_dir(dir_path: Path) -> list[dict]:
    courses = []
    for fp in sorted(dir_path.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(data, list):
                courses.extend(data)
        except Exception as e:
            print(f"  [WARN] {fp.name}: {e}")
    return courses


def deduplicate(sources: list[tuple[str, Path]]) -> list[dict]:
    """依 sources 順序載入並去重（後者覆蓋前者），key = 課號-班別。"""
    seen: dict[str, dict] = {}
    for label, path in sources:
        if not path.exists():
            print(f"  [SKIP] {label}: {path} 不存在")
            continue
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            courses = data if isinstance(data, list) else []
        else:
            courses = load_from_dir(path)

        before = len(seen)
        for c in courses:
            key = c.get("課號-班別", "").strip()
            if key:
                seen[key] = c
        print(f"  [{label}] 載入 {len(courses)} 筆，累計 unique: {len(seen)}（新增 {len(seen)-before}）")

    return list(seen.values())


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("=== 大學部課程去重 ===")
    undergrad = deduplicate(UNDERGRAD_DIRS)
    ug_path = OUT / "undergrad.json"
    ug_path.write_text(json.dumps(undergrad, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ 輸出 {len(undergrad)} 筆 → {ug_path}\n")

    print("=== 研究所課程去重 ===")
    grad = deduplicate(GRAD_DIRS)
    grad_path = OUT / "grad.json"
    grad_path.write_text(json.dumps(grad, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ 輸出 {len(grad)} 筆 → {grad_path}")

    # 簡單驗證：確認同課號-班別不重複
    ug_keys = [c.get("課號-班別", "") for c in undergrad]
    dups = len(ug_keys) - len(set(ug_keys))
    print(f"\n[驗證] undergrad 重複 key 數：{dups}（應為 0）")
    grad_keys = [c.get("課號-班別", "") for c in grad]
    dups_g = len(grad_keys) - len(set(grad_keys))
    print(f"[驗證] grad 重複 key 數：{dups_g}（應為 0）")


if __name__ == "__main__":
    main()
