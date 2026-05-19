"""
migrate_qdrant_to_cloud.py

將本地 Qdrant local-mode 資料夾 data/processed/qdrant_data 搬到 Qdrant Cloud。

用法：
  python scripts/rag/migrate_qdrant_to_cloud.py
  python scripts/rag/migrate_qdrant_to_cloud.py --reset
  python scripts/rag/migrate_qdrant_to_cloud.py --collections ncu_courses_ug ncu_teachers

需要 .env：
  QDRANT_URL=https://xxxx.region.cloud.qdrant.io
  QDRANT_API_KEY=...
"""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct


ROOT = Path(__file__).parent.parent.parent
QDRANT_DIR = ROOT / "data" / "processed" / "qdrant_data"
BATCH_SIZE = 256


def _local_client() -> QdrantClient:
    if not QDRANT_DIR.exists():
        raise FileNotFoundError(f"找不到本地 Qdrant 資料夾：{QDRANT_DIR}")
    return QdrantClient(path=str(QDRANT_DIR))


def _cloud_client() -> QdrantClient:
    qdrant_url = os.getenv("QDRANT_URL", "").strip()
    qdrant_api_key = os.getenv("QDRANT_API_KEY", "").strip()
    if not qdrant_url:
        raise RuntimeError("請先設定 QDRANT_URL")
    if not qdrant_api_key:
        raise RuntimeError("請先設定 QDRANT_API_KEY")
    return QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=60)


def _collection_names(client: QdrantClient) -> list[str]:
    return [c.name for c in client.get_collections().collections]


def migrate_collection(
    local: QdrantClient,
    cloud: QdrantClient,
    collection_name: str,
    reset: bool,
) -> None:
    local_info = local.get_collection(collection_name)
    cloud_collections = set(_collection_names(cloud))

    if collection_name in cloud_collections:
        if reset:
            print(f"[{collection_name}] 刪除雲端舊 collection")
            cloud.delete_collection(collection_name)
        else:
            print(f"[{collection_name}] 雲端已存在，略過（加 --reset 可覆蓋）")
            return

    vectors_config = local_info.config.params.vectors
    cloud.create_collection(
        collection_name=collection_name,
        vectors_config=vectors_config,
    )

    total = local_info.points_count or 0
    print(f"[{collection_name}] 開始搬移 {total} 筆")

    offset = None
    uploaded = 0
    while True:
        records, offset = local.scroll(
            collection_name=collection_name,
            limit=BATCH_SIZE,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        if not records:
            break

        points = [
            PointStruct(
                id=record.id,
                vector=record.vector,
                payload=record.payload or {},
            )
            for record in records
        ]
        cloud.upsert(collection_name=collection_name, points=points)
        uploaded += len(points)
        print(f"[{collection_name}] {uploaded}/{total}", end="\r")

        if offset is None:
            break

    print(f"\n[{collection_name}] 完成")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="覆蓋雲端既有 collections")
    parser.add_argument("--collections", nargs="*", help="只搬指定 collections")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")

    local = _local_client()
    cloud = _cloud_client()
    local_collections = _collection_names(local)
    collections = args.collections or local_collections

    missing = [name for name in collections if name not in local_collections]
    if missing:
        raise RuntimeError(f"本地不存在這些 collections：{missing}")

    print(f"本地 Qdrant：{QDRANT_DIR}")
    print(f"準備搬移 collections：{', '.join(collections)}")

    for collection_name in collections:
        migrate_collection(local, cloud, collection_name, reset=args.reset)

    print("\n全部完成。雲端 collections：")
    for name in _collection_names(cloud):
        try:
            info = cloud.get_collection(name)
            print(f"  {name}: {info.points_count} 筆")
        except Exception:
            print(f"  {name}")


if __name__ == "__main__":
    main()
