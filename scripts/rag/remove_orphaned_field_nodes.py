"""
remove_orphaned_field_nodes.py — 從 ncu_graph_nodes 刪除孤立 Field 節點

修正 nlp_domain_tags.json（刪除無效 tag）後，knowledge graph 裡多出的
Field 節點也會殘留在 Qdrant ncu_graph_nodes collection。
此腳本直接刪除這些孤立節點，不需要重新 embed（不花錢）。

用法：
  python scripts/rag/remove_orphaned_field_nodes.py [--dry-run]
"""

import json
import sys
from pathlib import Path

ROOT         = Path(__file__).parent.parent.parent
NLP_DIR      = ROOT / "data" / "processed" / "nlp"
QDRANT_DIR   = ROOT / "data" / "processed" / "qdrant_data"
COLLECTION   = "ncu_graph_nodes"
SCROLL_BATCH = 200


def build_valid_fields() -> set[str]:
    """從修正後的 nlp_domain_tags.json + dept_professor_map.json 取得所有合法 field 名稱。"""
    valid: set[str] = set()

    domain_path = NLP_DIR / "nlp_domain_tags.json"
    if domain_path.exists():
        data = json.loads(domain_path.read_text(encoding="utf-8"))
        for v in data.values():
            for tag in v.get("domain_tags", []):
                if isinstance(tag, dict) and tag.get("field"):
                    valid.add(tag["field"].strip())

    dept_map_path = NLP_DIR / "dept_professor_map.json"
    if dept_map_path.exists():
        dept_map = json.loads(dept_map_path.read_text(encoding="utf-8"))
        for dept_data in dept_map.values():
            for prof in dept_data.get("professors", []):
                for spec in prof.get("specialties", []):
                    valid.add(spec.strip())

    return valid


def main(dry_run: bool = False):
    from dotenv import load_dotenv
    import os

    for env_path in [ROOT / ".env", ROOT / "backend" / ".env", Path(".env")]:
        if env_path.exists():
            load_dotenv(env_path)
            break

    try:
        from qdrant_client import QdrantClient
    except ImportError:
        print("[錯誤] 請先安裝 qdrant-client")
        sys.exit(1)

    qdrant_url = os.getenv("QDRANT_URL", "").strip()
    if qdrant_url:
        client = QdrantClient(url=qdrant_url, api_key=os.getenv("QDRANT_API_KEY") or None, timeout=60)
        print(f"連線至遠端 Qdrant: {qdrant_url}")
    else:
        client = QdrantClient(path=str(QDRANT_DIR))
        print(f"使用本地 Qdrant: {QDRANT_DIR}")

    valid_fields = build_valid_fields()
    print(f"合法 Field 名稱數量：{len(valid_fields)}")

    # 全量 scroll（node_type 無索引，在 Python 端過濾）
    orphan_ids: list[int] = []
    orphan_names: list[str] = []
    offset = None
    total_scanned = 0

    print(f"\n掃描 {COLLECTION} 中所有節點...")
    while True:
        batch, next_offset = client.scroll(
            COLLECTION,
            offset=offset,
            limit=SCROLL_BATCH,
            with_payload=["name", "node_type"],
            with_vectors=False,
        )
        for pt in batch:
            total_scanned += 1
            if pt.payload.get("node_type") != "Field":
                continue
            name = pt.payload.get("name", "")
            if name not in valid_fields:
                orphan_ids.append(pt.id)
                orphan_names.append(name)

        if next_offset is None:
            break
        offset = next_offset

    print(f"掃描完成：共 {total_scanned} 個節點")

    print(f"找到孤立 Field 節點：{len(orphan_ids)} 個")

    if not orphan_ids:
        print("無需刪除。")
        return

    if dry_run:
        print("\n[DRY RUN] 前 20 個待刪除節點：")
        for name in orphan_names[:20]:
            print(f"  - {name}")
        return

    # 分批刪除
    BATCH = 100
    deleted = 0
    for i in range(0, len(orphan_ids), BATCH):
        chunk = orphan_ids[i:i + BATCH]
        client.delete(collection_name=COLLECTION, points_selector=chunk)
        deleted += len(chunk)
        print(f"  進度: {deleted}/{len(orphan_ids)}", end="\r")

    print(f"\n完成！已刪除 {deleted} 個孤立 Field 節點")

    # 驗證
    info = client.get_collection(COLLECTION)
    print(f"剩餘 {COLLECTION} 節點數：{info.points_count}")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    if dry:
        print("=== DRY RUN 模式（不寫入） ===")
    main(dry_run=dry)
