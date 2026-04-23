"""
update_syllabus_metadata.py

只更新 ChromaDB 中現有課程的 objective / content / textbook 三個 metadata 欄位，
不重新嵌入向量。

執行方式：
  cd <project_root>
  python scripts/rag/update_syllabus_metadata.py

可用 --collection 指定只更新哪個 collection（預設兩個都跑）：
  python scripts/rag/update_syllabus_metadata.py --collection ncu_courses_ug
"""

import argparse
import json
from pathlib import Path

import chromadb
from tqdm import tqdm

# ── 路徑 ────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent.parent.parent
DATA_RAW   = ROOT / "data" / "raw"
DATA_PROC  = ROOT / "data" / "processed"
CHROMA_DIR = DATA_PROC / "chroma_db"

COURSE_DIRS = {
    "ncu_courses_ug":   [DATA_RAW / "courses" / "114_1",
                         DATA_RAW / "courses" / "114_2",
                         DATA_RAW / "scraped_missing"],
    "ncu_courses_grad": [DATA_RAW / "graduate_courses" / "114_1",
                         DATA_RAW / "graduate_courses" / "114_2"],
}

UPDATE_BATCH = 500  # 每批 update 的筆數


def clean_code(raw: str) -> str:
    return raw.split("-")[0].strip() if raw else ""


def load_raw_courses(dirs: list[Path]) -> list[dict]:
    courses = []
    for d in dirs:
        if not d.exists():
            continue
        pattern = "*.json" if d.name != "scraped_missing" else "courses.json"
        for fp in d.glob(pattern):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    courses.extend(data)
            except Exception as e:
                print(f"  [WARN] {fp.name}: {e}")
    return courses


def build_syllabus_map(courses: list[dict]) -> dict[str, dict]:
    """
    以 doc_id 為 key，建立 {doc_id: {objective, content, textbook}} 的映射。
    doc_id 格式與 build_vector_index.py 一致：{year}{semester}_{serial}_{code}
    同一 key 後讀覆蓋前（114_2 優先）。
    """
    result: dict[str, dict] = {}
    for c in courses:
        syllabus = c.get("課程綱要") or {}
        if isinstance(syllabus, str):
            syllabus = {}

        year     = c.get("學年度", "")
        semester = c.get("學期", "")
        serial   = c.get("流水號", "")
        code     = clean_code(c.get("課號-班別", ""))

        if not (year and semester and serial and code):
            continue

        doc_id = f"{year}{semester}_{serial}_{code}"
        result[doc_id] = {
            "objective": syllabus.get("課程目標", "") or "",
            "content":   syllabus.get("授課內容", "") or "",
            "textbook":  syllabus.get("教科書/參考書", "") or "",
        }
    return result


def update_collection(col: chromadb.Collection, syllabus_map: dict[str, dict]) -> None:
    # 取得 collection 裡所有 id（不含 embedding，省記憶體）
    print(f"  取得現有 IDs …", end=" ", flush=True)
    all_ids: list[str] = col.get(include=[])["ids"]
    print(f"{len(all_ids)} 筆")

    # 只處理 syllabus_map 裡有對應的 id
    target_ids = [did for did in all_ids if did in syllabus_map]
    print(f"  可更新：{len(target_ids)} 筆（其餘無大綱資料，跳過）")

    updated = 0
    for start in tqdm(range(0, len(target_ids), UPDATE_BATCH), desc="  updating metadata"):
        batch_ids = target_ids[start : start + UPDATE_BATCH]

        # 取回現有 metadata
        result = col.get(ids=batch_ids, include=["metadatas"])
        existing_metas: list[dict] = result["metadatas"]

        # 將三個欄位合併進去
        new_metas = []
        for meta, did in zip(existing_metas, batch_ids):
            patch = syllabus_map[did]
            meta["objective"] = patch["objective"]
            meta["content"]   = patch["content"]
            meta["textbook"]  = patch["textbook"]
            new_metas.append(meta)

        col.update(ids=batch_ids, metadatas=new_metas)
        updated += len(batch_ids)

    print(f"  完成，共更新 {updated} 筆 metadata")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--collection",
        choices=list(COURSE_DIRS.keys()),
        default=None,
        help="只更新指定 collection（不填則兩個都跑）",
    )
    args = parser.parse_args()

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    targets = (
        {args.collection: COURSE_DIRS[args.collection]}
        if args.collection
        else COURSE_DIRS
    )

    for col_name, dirs in targets.items():
        print(f"\n=== {col_name} ===")
        try:
            col = client.get_collection(col_name)
        except Exception:
            print(f"  [SKIP] collection 不存在")
            continue

        courses = load_raw_courses(dirs)
        print(f"  原始課程資料：{len(courses)} 筆")

        syllabus_map = build_syllabus_map(courses)
        print(f"  建立 syllabus_map：{len(syllabus_map)} 個 doc_id")

        update_collection(col, syllabus_map)

    print("\n全部完成。")


if __name__ == "__main__":
    main()
