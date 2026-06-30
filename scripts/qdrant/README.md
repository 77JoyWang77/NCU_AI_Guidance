# Qdrant 備份與還原教學

從雲端 Qdrant 備份所有 collection 到本地，並透過 Docker 在本地端運行。

## 檔案說明

| 檔案 | 用途 |
|------|------|
| `test_connection.py` | 測試 Qdrant 連線並列出所有 collections |
| `download_snapshots.py` | 從雲端下載所有 collection 的 snapshot |
| `restore_to_docker.py` | 將 snapshot 還原至本地 Docker Qdrant |

---

## 備份流程

### Step 1 — 確認 `.env` 指向雲端

```env
QDRANT_URL=https://<your-cluster>.cloud.qdrant.io
QDRANT_API_KEY=<your-api-key>
```

### Step 2 — 下載所有 snapshot

```bash
python scripts/qdrant/download_snapshots.py
```

snapshot 檔案會存放於 `data/processed/qdrant_snapshots/`。

### Step 3 — 啟動本地 Qdrant Docker

```bash
docker-compose up -d
```

### Step 4 — 還原所有 snapshot

```bash
python scripts/qdrant/restore_to_docker.py
```

若只需還原特定 collection：

```bash
python scripts/qdrant/restore_to_docker.py ncu_departments ncu_graph_nodes
```

### Step 5 — 切換 `.env` 至本地模式

```env
QDRANT_URL=http://localhost:6333
# QDRANT_API_KEY 不需要，可刪除或註解
```

---

## 驗證

```bash
python scripts/qdrant/test_connection.py
```

或直接查詢：

```bash
curl http://localhost:6333/collections
```

---

## 注意事項

- `qdrant_data/` 資料夾為 Docker volume 掛載路徑，container 重啟後資料不會消失
- 若還原失敗，直接重跑指定 collection 即可，腳本會自動刪除舊的再重建
- 雲端 snapshot 下載時間依 collection 大小而定，`ncu_graph_nodes` 約需數分鐘
