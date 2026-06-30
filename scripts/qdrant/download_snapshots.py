"""
從 Qdrant Cloud 下載所有 collection 的 snapshot 到本地
執行：python scripts/qdrant/download_snapshots.py
"""
import os, sys, time, requests
from pathlib import Path
from dotenv import load_dotenv
from qdrant_client import QdrantClient

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")

QDRANT_URL    = os.getenv("QDRANT_URL", "").strip()
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "").strip() or None
SNAPSHOT_DIR  = ROOT / "data" / "processed" / "qdrant_snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

if not QDRANT_URL:
    print("[!] QDRANT_URL 未設定，請確認 .env 指向雲端")
    sys.exit(1)

print(f"雲端：{QDRANT_URL}")
print(f"存放：{SNAPSHOT_DIR}")
print("-" * 60)

client  = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=120)
headers = {"api-key": QDRANT_API_KEY} if QDRANT_API_KEY else {}

collections = [c.name for c in client.get_collections().collections]
print(f"共 {len(collections)} 個 collections：{collections}\n")

failed = []

for idx, name in enumerate(collections, 1):
    out_path = SNAPSHOT_DIR / f"{name}.snapshot"
    print(f"[{idx}/{len(collections)}] {name}")

    # 建立 snapshot
    print("  建立 snapshot...", end=" ", flush=True)
    try:
        snap = client.create_snapshot(collection_name=name)
        print(f"OK ({snap.name})")
    except Exception as e:
        print(f"FAIL: {e}")
        failed.append(name)
        continue

    # 下載
    url = f"{QDRANT_URL}/collections/{name}/snapshots/{snap.name}"
    print("  下載中...", end=" ", flush=True)
    t0 = time.time()
    try:
        with requests.get(url, headers=headers, stream=True, timeout=300) as r:
            r.raise_for_status()
            total = 0
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                    f.write(chunk)
                    total += len(chunk)
                    print(f"\r  下載中... {total/1024/1024:.1f} MB", end="", flush=True)
        elapsed = time.time() - t0
        print(f"\r  完成 {total/1024/1024:.1f} MB  ({elapsed:.1f}s) → {out_path.name}")
    except Exception as e:
        print(f"\n  [!] 下載失敗: {e}")
        failed.append(name)

print("\n" + "=" * 60)
if failed:
    print(f"[!] 以下 collection 失敗，請重新執行：{failed}")
else:
    print(f"全部 {len(collections)} 個 collection 下載完成！")
    print(f"下一步：python scripts/qdrant/restore_to_docker.py")
