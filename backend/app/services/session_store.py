"""
session_store.py

以 JSON 檔案儲存對話歷史，每個 session 一個檔案。
儲存路徑：data/sessions/<session_id>.json
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
SESSIONS_DIR = ROOT / "data" / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

MAX_HISTORY = 20  # 保留最近幾輪（user+assistant 各算一條）


def _path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def new_session_id() -> str:
    return uuid.uuid4().hex


def load(session_id: str) -> list[dict]:
    """載入對話歷史，只回傳 role/content 清單（供 LLM 使用）。"""
    fp = _path(session_id)
    if not fp.exists():
        return []
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        return data.get("messages", [])[-MAX_HISTORY:]
    except Exception:
        return []


def save(session_id: str, user_msg: str, assistant_msg: str) -> None:
    """追加一輪對話（user + assistant）到 session 檔案。"""
    fp = _path(session_id)
    if fp.exists():
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            data = _new_data(session_id)
    else:
        data = _new_data(session_id)

    data["messages"].append({"role": "user",      "content": user_msg})
    data["messages"].append({"role": "assistant",  "content": assistant_msg})
    data["updated_at"] = _now()

    fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def delete(session_id: str) -> bool:
    """刪除 session 檔案，回傳是否成功。"""
    fp = _path(session_id)
    if fp.exists():
        fp.unlink()
        return True
    return False


def _new_data(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "created_at": _now(),
        "updated_at": _now(),
        "messages":   [],
    }


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
