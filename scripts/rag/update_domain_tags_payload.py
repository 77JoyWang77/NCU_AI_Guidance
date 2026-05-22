"""
update_domain_tags_payload.py — 將修正後的 domain_tags 寫回 Qdrant payload

從 data/processed/nlp/nlp_domain_tags.json 讀取已修正（繁體化 + 符合詞彙表）的 domain_tags，
更新 ncu_courses_ug 與 ncu_courses_grad 兩個 collection 的 domain_tags_rich 欄位。

domain_tags_rich 格式：  "標籤A::high||標籤B::medium||標籤C::low"

用法：
  python scripts/rag/update_domain_tags_payload.py [--dry-run]
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
NLP_TAGS_PATH = ROOT / "data" / "processed" / "nlp" / "nlp_domain_tags.json"
QDRANT_DIR    = ROOT / "data" / "processed" / "qdrant_data"
COLLECTIONS   = ["ncu_courses_ug", "ncu_courses_grad"]
SCROLL_BATCH  = 200


def tags_to_rich_str(tags: list[dict]) -> str:
    """[{"field": "演算法", "relevance": "high"}, ...] → "演算法::high||..."."""
    parts = []
    for t in tags:
        field = str(t.get("field", "")).strip()
        rel   = str(t.get("relevance", "medium")).strip()
        if field:
            parts.append(f"{field}::{rel}")
    return "||".join(parts)


def build_code_to_point(client, collection: str) -> dict[str, int]:
    """Scroll 整個 collection，建立 course_code → point_id 的對照表。"""
    code_to_id: dict[str, int] = {}
    offset = None
    while True:
        batch, next_offset = client.scroll(
            collection,
            offset=offset,
            limit=SCROLL_BATCH,
            with_payload=["course_code"],
            with_vectors=False,
        )
        for pt in batch:
            code = pt.payload.get("course_code", "")
            if code:
                code_to_id[code] = pt.id
        if next_offset is None:
            break
        offset = next_offset
    return code_to_id


def main(dry_run: bool = False):
    from dotenv import load_dotenv
    import os

    for env_path in [ROOT / "backend" / ".env", ROOT / ".env", Path(".env")]:
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

    if not NLP_TAGS_PATH.exists():
        print(f"[錯誤] 找不到 {NLP_TAGS_PATH}")
        sys.exit(1)

    nlp_data: dict = json.loads(NLP_TAGS_PATH.read_text(encoding="utf-8"))
    print(f"載入 {len(nlp_data)} 筆 nlp_domain_tags 資料")

    # 只處理有實際 tag 的課程
    to_update: dict[str, str] = {}  # course_code → rich_str
    for code, val in nlp_data.items():
        if val.get("skipped") or not val.get("domain_tags"):
            continue
        rich = tags_to_rich_str(val["domain_tags"])
        if rich:
            to_update[code] = rich

    print(f"需要更新的課程數：{len(to_update)}")

    total_updated = 0

    for col in COLLECTIONS:
        print(f"\n[{col}] 建立 course_code → point_id 對照表...")
        code_to_id = build_code_to_point(client, col)
        print(f"  共 {len(code_to_id)} 個 course_code")

        matched = {code: pid for code, pid in code_to_id.items() if code in to_update}
        print(f"  命中需更新的課程：{len(matched)} 個")

        if dry_run:
            for code, pid in list(matched.items())[:5]:
                print(f"  [DRY] {code} (id={pid}) → {to_update[code][:60]}...")
            continue

        # 逐批更新（set_payload 支援 point_ids 清單）
        BATCH = 100
        items = list(matched.items())
        for i in range(0, len(items), BATCH):
            chunk = items[i:i + BATCH]
            for code, pid in chunk:
                client.set_payload(
                    collection_name=col,
                    payload={"domain_tags_rich": to_update[code]},
                    points=[pid],
                )
            total_updated += len(chunk)
            print(f"  進度: {min(i + BATCH, len(items))}/{len(items)}", end="\r")

        print(f"  [{col}] 完成更新 {len(matched)} 個 points")

    if not dry_run:
        print(f"\n全部完成！共更新 {total_updated} 個 Qdrant points")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    if dry:
        print("=== DRY RUN 模式（不寫入） ===")
    main(dry_run=dry)
