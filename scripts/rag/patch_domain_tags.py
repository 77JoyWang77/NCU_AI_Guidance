"""
patch_domain_tags.py

將 nlp_domain_tags.json 的領域標籤（含 relevance）patch 進 ChromaDB metadata。
序列化格式：「領域::relevance||領域::relevance」（全部標籤）

執行方式：
  cd <project_root>
  python scripts/rag/patch_domain_tags.py
"""

import json
from pathlib import Path

import chromadb

ROOT = Path(__file__).parent.parent.parent
CHROMA_DIR = ROOT / "data" / "processed" / "chroma_db"
DOMAIN_TAGS_PATH = ROOT / "data" / "processed" / "nlp" / "nlp_domain_tags.json"

COLLECTIONS = ["ncu_courses_ug", "ncu_courses_grad"]
BATCH_SIZE = 500


def serialize(domain_tags: list[dict]) -> str:
    parts = []
    for t in domain_tags:
        field = t.get("field", "").replace("::", "").replace("||", "")
        relevance = t.get("relevance", "medium").replace("::", "").replace("||", "")
        if field:
            parts.append(f"{field}::{relevance}")
    return "||".join(parts)


def patch_collection(col: chromadb.Collection, domain_data: dict) -> int:
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
            # Try pure code (e.g. "GP1010") extracted from serial_no
            pure_code = code.split("_")[-1] if "_" in code else code
            entry = domain_data.get(pure_code) or domain_data.get(code)
            if not entry or entry.get("skipped"):
                continue

            tags = entry.get("domain_tags", [])
            if not tags:
                continue

            new_value = serialize(tags)
            if not new_value or meta.get("domain_tags_rich") == new_value:
                continue

            updated = dict(meta)
            updated["domain_tags_rich"] = new_value
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
    domain_data = json.loads(DOMAIN_TAGS_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(domain_data)} entries from nlp_domain_tags.json")

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    for col_name in COLLECTIONS:
        try:
            col = client.get_collection(col_name)
        except Exception:
            print(f"[SKIP] {col_name} not found")
            continue
        print(f"Patching {col_name} ...")
        n = patch_collection(col, domain_data)
        print(f"  => {n} records updated in {col_name}")

    print("Done.")


if __name__ == "__main__":
    main()
