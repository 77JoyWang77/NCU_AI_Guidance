"""
session_store.py

以 PostgreSQL 持久化對話歷史。
需要在環境變數設定 DATABASE_URL。
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row


MAX_HISTORY = 20  # 保留最近幾則 role/content 訊息給 LLM 使用
_SCHEMA_READY = False
_TW = timezone(timedelta(hours=8))


def new_session_id() -> str:
    return uuid.uuid4().hex


def load(session_id: str, user_id: str | None = None) -> list[dict]:
    """載入對話歷史，只回傳 role/content 清單（供 LLM 使用）。"""
    if user_id is None:
        return []

    _ensure_schema()
    turn_limit = max(1, MAX_HISTORY // 2)

    with _connect() as conn:
        session = _get_accessible_session(conn, session_id, user_id)
        if session is None:
            return []

        rows = conn.execute(
            """
            select user_msg, assistant_msg
            from chat_turns
            where session_id = %s
            order by id desc
            limit %s
            """,
            (session_id, turn_limit),
        ).fetchall()

    messages: list[dict] = []
    for row in reversed(rows):
        messages.append({"role": "user", "content": row["user_msg"]})
        messages.append({"role": "assistant", "content": row["assistant_msg"]})
    return messages[-MAX_HISTORY:]


def save(
    session_id: str,
    user_msg: str,
    assistant_msg: str,
    course_cards: list | None = None,
    tools_used: list | None = None,
    course_pool: list | None = None,
    debug_trace: dict | None = None,
    user_id: str | None = None,
    user_profile: dict | None = None,
) -> None:
    """追加一輪對話到 PostgreSQL。"""
    if user_id is None:
        return

    _ensure_schema()
    now = _now_datetime()
    title = user_msg[:40] if user_msg else ""

    with _connect() as conn:
        if user_id:
            _upsert_user(conn, user_id, user_profile or {}, now)

        existing = conn.execute(
            "select user_id from chat_sessions where session_id = %s",
            (session_id,),
        ).fetchone()

        if existing is None:
            conn.execute(
                """
                insert into chat_sessions (session_id, user_id, title, created_at, updated_at)
                values (%s, %s, %s, %s, %s)
                """,
                (session_id, user_id, title, now, now),
            )
        elif not _can_access(existing["user_id"], user_id):
            return
        else:
            conn.execute(
                """
                update chat_sessions
                set
                    user_id = coalesce(user_id, %s),
                    title = case when title = '' then %s else title end,
                    updated_at = %s
                where session_id = %s
                """,
                (user_id, title, now, session_id),
            )

        conn.execute(
            """
            insert into chat_turns (
                session_id,
                user_msg,
                assistant_msg,
                course_cards,
                course_pool,
                tools_used,
                debug_trace,
                created_at
            )
            values (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s)
            """,
            (
                session_id,
                user_msg,
                assistant_msg,
                _json(course_cards or []),
                _json(course_pool or []),
                _json(tools_used or []),
                _json(debug_trace or {}),
                now,
            ),
        )
        conn.commit()


def delete(session_id: str, user_id: str | None = None) -> bool:
    """刪除 session，回傳是否成功。"""
    if user_id is None:
        return False

    _ensure_schema()
    with _connect() as conn:
        session = _get_accessible_session(conn, session_id, user_id)
        if session is None:
            return False

        result = conn.execute(
            "delete from chat_sessions where session_id = %s",
            (session_id,),
        )
        conn.commit()
        return (result.rowcount or 0) > 0


def list_sessions(limit: int = 50, user_id: str | None = None) -> list[dict]:
    """列出 session 摘要，按更新時間降序排列。"""
    if user_id is None:
        return []

    _ensure_schema()
    with _connect() as conn:
        rows = conn.execute(
            """
            select
                s.session_id,
                coalesce(nullif(s.title, ''), '未命名對話') as title,
                s.updated_at,
                count(t.id)::int as turn_count
            from chat_sessions s
            left join chat_turns t on t.session_id = s.session_id
            where s.user_id = %s
            group by s.session_id, s.title, s.updated_at
            order by s.updated_at desc
            limit %s
            """,
            (user_id, limit),
        ).fetchall()

    return [
        {
            "session_id": row["session_id"],
            "title": row["title"],
            "updated_at": _format_dt(row["updated_at"]),
            "turn_count": row["turn_count"],
        }
        for row in rows
    ]


def get_display(session_id: str, user_id: str | None = None) -> dict | None:
    """取得完整對話資料（含課程卡片與工具紀錄）供前端顯示。"""
    if user_id is None:
        return None

    _ensure_schema()
    with _connect() as conn:
        session = _get_accessible_session(conn, session_id, user_id)
        if session is None:
            return None

        rows = conn.execute(
            """
            select
                user_msg,
                assistant_msg,
                course_cards,
                course_pool,
                tools_used,
                debug_trace,
                created_at
            from chat_turns
            where session_id = %s
            order by id asc
            """,
            (session_id,),
        ).fetchall()

    return {
        "session_id": session_id,
        "title": session["title"] or "未命名對話",
        "updated_at": _format_dt(session["updated_at"]),
        "turns": [
            {
                "user": row["user_msg"],
                "assistant": row["assistant_msg"],
                "course_cards": _from_jsonb(row["course_cards"], []),
                "course_pool": _from_jsonb(row["course_pool"], []),
                "tools_used": _from_jsonb(row["tools_used"], []),
                "debug_trace": _from_jsonb(row["debug_trace"], {}),
                "created_at": _format_dt(row["created_at"]),
            }
            for row in rows
        ],
    }


def _connect() -> psycopg.Connection:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for PostgreSQL session storage")
    return psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10)


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return

    with _connect() as conn:
        conn.execute(
            """
            create table if not exists app_users (
                user_id text primary key,
                email text not null default '',
                name text not null default '',
                picture text not null default '',
                provider text not null default 'firebase',
                created_at timestamptz not null default now(),
                updated_at timestamptz not null default now(),
                last_seen_at timestamptz not null default now()
            )
            """
        )
        conn.execute(
            """
            create table if not exists chat_sessions (
                session_id text primary key,
                user_id text,
                title text not null default '',
                created_at timestamptz not null default now(),
                updated_at timestamptz not null default now()
            )
            """
        )
        conn.execute(
            """
            create table if not exists chat_turns (
                id bigserial primary key,
                session_id text not null references chat_sessions(session_id) on delete cascade,
                user_msg text not null,
                assistant_msg text not null,
                course_cards jsonb not null default '[]'::jsonb,
                course_pool jsonb not null default '[]'::jsonb,
                tools_used jsonb not null default '[]'::jsonb,
                debug_trace jsonb not null default '{}'::jsonb,
                created_at timestamptz not null default now()
            )
            """
        )
        conn.execute(
            "create index if not exists idx_chat_sessions_user_updated on chat_sessions(user_id, updated_at desc)"
        )
        conn.execute(
            "create index if not exists idx_app_users_email on app_users(email)"
        )
        conn.execute(
            "create index if not exists idx_chat_turns_session_id on chat_turns(session_id, id)"
        )
        conn.commit()

    _SCHEMA_READY = True


def _get_accessible_session(
    conn: psycopg.Connection,
    session_id: str,
    user_id: str | None,
) -> dict | None:
    session = conn.execute(
        "select session_id, user_id, title, updated_at from chat_sessions where session_id = %s",
        (session_id,),
    ).fetchone()
    if session is None:
        return None
    if not _can_access(session["user_id"], user_id):
        return None
    return session


def _upsert_user(
    conn: psycopg.Connection,
    user_id: str,
    profile: dict,
    now: datetime,
) -> None:
    conn.execute(
        """
        insert into app_users (
            user_id,
            email,
            name,
            picture,
            provider,
            created_at,
            updated_at,
            last_seen_at
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (user_id) do update
        set
            email = excluded.email,
            name = excluded.name,
            picture = excluded.picture,
            updated_at = excluded.updated_at,
            last_seen_at = excluded.last_seen_at
        """,
        (
            user_id,
            profile.get("email", ""),
            profile.get("name", ""),
            profile.get("picture", ""),
            profile.get("provider", "firebase"),
            now,
            now,
            now,
        ),
    )


def _can_access(owner: str | None, user_id: str | None) -> bool:
    return user_id is not None and owner == user_id


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _from_jsonb(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value


def _now_datetime() -> datetime:
    return datetime.now(_TW)


def _format_dt(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(_TW).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    if value:
        return str(value)
    return ""
