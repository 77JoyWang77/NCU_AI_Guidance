"""
快速測試 Qdrant 雲端連線，執行：
  python scripts/test_qdrant_connection.py
"""
import os, sys, time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

QDRANT_URL = os.getenv("QDRANT_URL", "").strip()
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "").strip() or None

print(f"URL  : {QDRANT_URL or '(未設定，將使用本機路徑)'}")
print(f"KEY  : {'已設定' if QDRANT_API_KEY else '(未設定)'}")
print("-" * 50)

if not QDRANT_URL:
    print("[!] QDRANT_URL 未設定，請確認 .env 檔案")
    sys.exit(1)

try:
    from qdrant_client import QdrantClient
except ImportError:
    print("[!] qdrant-client 未安裝，請執行：pip install qdrant-client")
    sys.exit(1)

print("[1] 建立 QdrantClient …")
client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=15)

print("[2] 測試 /healthz …")
t0 = time.time()
try:
    ok = client.http.cluster_api.cluster_status()
    print(f"    cluster status: {ok}")
except Exception as e:
    print(f"    cluster_status 失敗（嘗試用 get_collections 代替）: {e}")

print("[3] 列出 collections …")
try:
    t0 = time.time()
    cols = client.get_collections()
    elapsed = time.time() - t0
    names = [c.name for c in cols.collections]
    print(f"    回應時間: {elapsed:.2f}s")
    print(f"    Collections ({len(names)}): {names}")
except Exception as e:
    print(f"[ERROR] 連線失敗: {e}")
    print()
    print("可能原因：")
    print("  1. Qdrant Cloud cluster 已暫停 / 刪除")
    print("  2. API key 過期或無效")
    print("  3. 網路防火牆封鎖 443 port")
    print("  4. QDRANT_URL 末尾多了斜線或空白")
    sys.exit(1)

if not names:
    print("[!] 連線成功，但沒有任何 collection")
else:
    print("[4] 測試第一個 collection 計數 …")
    try:
        count = client.count(names[0])
        print(f"    {names[0]}: {count.count} 筆向量")
    except Exception as e:
        print(f"    count 失敗: {e}")

print()
print("[OK] Qdrant 連線正常！")
