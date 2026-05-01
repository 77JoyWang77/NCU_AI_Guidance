"""
session_store.py

以 JSON 檔案持久化對話歷史，每個 session 一個檔案。
儲存路徑：data/sessions/<session_id>.json
"""

import json
import uuid
from datetime import datetime, timezone, timedelta
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


def save(
    session_id: str,
    user_msg: str,
    assistant_msg: str,
    course_cards: list | None = None,
    tools_used: list | None = None,
    course_pool: list | None = None,
    debug_trace: dict | None = None,
) -> None:
    """追加一輪對話到 session 檔案，同時儲存課程卡片與工具使用紀錄。"""
    fp = _path(session_id)
    if fp.exists():
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            data = _new_data(session_id)
    else:
        data = _new_data(session_id)

    # LLM history（純文字）
    data["messages"].append({"role": "user",      "content": user_msg})
    data["messages"].append({"role": "assistant",  "content": assistant_msg})

    # 顯示用 turns（含課程資料）
    if "turns" not in data:
        data["turns"] = []
    data["turns"].append({
        "user":         user_msg,
        "assistant":    assistant_msg,
        "course_cards": course_cards or [],
        "course_pool":  course_pool  or [],
        "tools_used":   tools_used   or [],
        "debug_trace":  debug_trace  or {},
        "created_at":   _now(),
    })

    # 以第一輪問題作為對話標題
    if not data.get("title") and user_msg:
        data["title"] = user_msg[:40]

    data["updated_at"] = _now()
    fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def delete(session_id: str) -> bool:
    """刪除 session 檔案，回傳是否成功。"""
    fp = _path(session_id)
    if fp.exists():
        fp.unlink()
        return True
    return False


def list_sessions(limit: int = 50) -> list[dict]:
    """列出所有 session 摘要，按更新時間降序排列。"""
    sessions = []
    for fp in SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            sessions.append({
                "session_id": data["session_id"],
                "title":      data.get("title", "未命名對話"),
                "updated_at": data.get("updated_at", ""),
                "turn_count": len(data.get("turns", [])),
            })
        except Exception:
            continue
    sessions.sort(key=lambda x: x["updated_at"], reverse=True)
    return sessions[:limit]


def get_display(session_id: str) -> dict | None:
    """取得完整對話資料（含課程卡片與工具紀錄）供前端顯示。"""
    fp = _path(session_id)
    if not fp.exists():
        return None
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        return {
            "session_id": session_id,
            "title":      data.get("title", "未命名對話"),
            "updated_at": data.get("updated_at", ""),
            "turns":      data.get("turns", []),
        }
    except Exception:
        return None


def _new_data(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "title":      "",
        "created_at": _now(),
        "updated_at": _now(),
        "messages":   [],
        "turns":      [],
    }


_TW = timezone(timedelta(hours=8))

def _now() -> str:
    return datetime.now(_TW).strftime("%Y-%m-%dT%H:%M:%S+08:00")
