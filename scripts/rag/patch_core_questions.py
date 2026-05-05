"""
patch_core_questions.py

將 nlp_topic_tags.json 中的 core_questions 欄位 patch 進 ChromaDB metadata。
使用 collection.update() 只更新 metadata，不需要重新 embedding。

執行方式：
  cd <project_root>
  python scripts/rag/patch_core_questions.py
"""

import json
from pathlib import Path

import chromadb

ROOT = Path(__file__).parent.parent.parent
CHROMA_DIR = ROOT / "data" / "processed" / "chroma_db"
TOPIC_TAGS_PATH = ROOT / "data" / "processed" / "nlp" / "nlp_topic_tags.json"

COLLECTIONS = ["ncu_courses_ug", "ncu_courses_grad"]
BATCH_SIZE = 500


def patch_collection(col: chromadb.Collection, topic_data: dict) -> int:
    offset = 0
    total_patched = 0

    while True:
        res = col.get(
            include=["metadatas"],
            limit=BATCH_SIZE,
            offset=offset,
        )
        ids = res["ids"]
        metas = res["metadatas"]
        if not ids:
            break

        ids_to_update, metas_to_update = [], []
        for doc_id, meta in zip(ids, metas):
            code = meta.get("course_code", "")
            entry = topic_data.get(code)
            if not entry:
                continue

            core_qs = entry.get("core_questions", [])
            if not core_qs:
                continue

            new_value = " | ".join(core_qs[:3])
            if meta.get("core_questions") == new_value:
                continue  # 已是最新值，跳過

            updated_meta = dict(meta)
            updated_meta["core_questions"] = new_value
            ids_to_update.append(doc_id)
            metas_to_update.append(updated_meta)

        if ids_to_update:
            col.update(ids=ids_to_update, metadatas=metas_to_update)
            total_patched += len(ids_to_update)
            print(f"  [{col.name}] offset={offset} patched {len(ids_to_update)} records")

        offset += BATCH_SIZE
        if len(ids) < BATCH_SIZE:
            break

    return total_patched


def main():
    topic_data: dict = json.loads(TOPIC_TAGS_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(topic_data)} course codes from nlp_topic_tags.json")

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    for col_name in COLLECTIONS:
        try:
            col = client.get_collection(col_name)
        except Exception:
            print(f"[SKIP] collection '{col_name}' not found")
            continue
        print(f"Patching {col_name} ...")
        n = patch_collection(col, topic_data)
        print(f"  => {n} records updated in {col_name}")

    print("Done.")


if __name__ == "__main__":
    main()
