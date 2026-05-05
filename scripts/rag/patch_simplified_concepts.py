"""
patch_simplified_concepts.py

將 nlp_simplified_concepts.json 中的所有概念說明 patch 進 ChromaDB metadata。
序列化格式：「原始術語::白話說明||原始術語::白話說明」（全部概念）

執行方式：
  cd <project_root>
  python scripts/rag/patch_simplified_concepts.py
"""

import json
from pathlib import Path

import chromadb

ROOT = Path(__file__).parent.parent.parent
CHROMA_DIR = ROOT / "data" / "processed" / "chroma_db"
SIMPLIFIED_PATH = ROOT / "data" / "processed" / "nlp" / "nlp_simplified_concepts.json"

COLLECTIONS = ["ncu_courses_ug", "ncu_courses_grad"]
BATCH_SIZE = 500


def serialize(concepts: list[dict]) -> str:
    parts = []
    for c in concepts:
        orig = c.get("original", "").replace("::", "").replace("||", "")
        disp = c.get("display", "").replace("::", "").replace("||", "")
        if orig and disp:
            parts.append(f"{orig}::{disp}")
    return "||".join(parts)


def patch_collection(col: chromadb.Collection, simplified_data: dict) -> int:
    offset = 0
    total_patched = 0

    while True:
        res = col.get(include=["metadatas"], limit=BATCH_SIZE, offset=offset)
        ids, metas = res["ids"], res["metadatas"]
        if not ids:
            break

        ids_to_update, metas_to_update = [], []
        for doc_id, meta in zip(ids, metas):
            code = meta.get("course_code", "")
            entry = simplified_data.get(code)
            if not entry:
                continue

            new_value = serialize(entry.get("simplified_concepts", []))
            if not new_value or meta.get("simplified_concepts") == new_value:
                continue

            updated = dict(meta)
            updated["simplified_concepts"] = new_value
            ids_to_update.append(doc_id)
            metas_to_update.append(updated)

        if ids_to_update:
            col.update(ids=ids_to_update, metadatas=metas_to_update)
            total_patched += len(ids_to_update)
            print(f"  [{col.name}] offset={offset} patched {len(ids_to_update)} records")

        offset += BATCH_SIZE
        if len(ids) < BATCH_SIZE:
            break

    return total_patched


def main():
    simplified_data = json.loads(SIMPLIFIED_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(simplified_data)} courses from nlp_simplified_concepts.json")

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    for col_name in COLLECTIONS:
        try:
            col = client.get_collection(col_name)
        except Exception:
            print(f"[SKIP] {col_name} not found")
            continue
        print(f"Patching {col_name} ...")
        n = patch_collection(col, simplified_data)
        print(f"  => {n} records updated in {col_name}")

    print("Done.")


if __name__ == "__main__":
    main()
