"""
session_store.py

以 PostgreSQL 持久化對話歷史。
需要在環境變數設定 DATABASE_URL。
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


MAX_HISTORY = 20  # 保留最近幾則 role/content 訊息給 LLM 使用
_SCHEMA_READY = False
_TW = timezone(timedelta(hours=8))
_ROOT = Path(__file__).parent.parent.parent.parent


@lru_cache(maxsize=1)
def _load_topic_tags() -> dict:
    p = _ROOT / "data" / "processed" / "nlp" / "nlp_topic_tags.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


@lru_cache(maxsize=1)
def _load_course_domains() -> dict[str, list[str]]:
    """course_code → list of 課程領域 strings（已切開）。"""
    p = _ROOT / "data" / "processed" / "course_index.json"
    if not p.exists():
        return {}
    idx = json.loads(p.read_text(encoding="utf-8"))
    return {code: entry.get("course_domains", []) for code, entry in idx.items()}


# 中心、處室 系所 → 通識大分類
GE_CATEGORY_MAP: dict[str, str] = {
    "語言中心":                             "外語",
    "體育室":                               "體育",
    "軍訓室":                               "體育",
    "學務處-服務學習發展中心":              "服務學習",
    "學務處-職涯發展中心":                  "服務學習",
    "通識教育中心":                         "通識",
    "核心通識課程":                         "通識",
    "總教學中心":                           "通識",
    "臺灣大專院校人工智慧學程聯盟":         "通識",
    "環境科技博士學位學程(台灣聯合大學系統)": "通識",
    "遙測科技碩士學位學程":                 "通識",
}

TOOL_LABELS: dict[str, str] = {
    "search_courses":              "課程語意搜尋",
    "get_dept_courses":            "系所課程查詢",
    "get_program_info":            "學分學程資訊",
    "get_program_courses":         "學分學程課程",
    "get_teacher_info":            "教師資訊查詢",
    "search_teachers":             "教師語意搜尋",
    "get_graduation_requirements": "畢業規定查詢",
    "get_graduation_rules":        "畢業規定查詢",
    "get_requirements_notes":      "修課規定查詢",
    "get_dept_info":               "系所介紹查詢",
    "get_course_detail":           "課程詳情查詢",
    "search_programs":             "學分學程搜尋",
    "get_program_description":     "學程說明查詢",
    "find_similar_courses":        "相似課程推薦",
    "get_course_knowledge_map":    "課程知識地圖",
    "get_depts_by_tech":           "技術科系分佈",
    "ppr_explore":                 "知識圖譜探索",
    "explore_concept_neighborhood": "概念鄰域探索",
}


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
        conn.execute(
            """
            create table if not exists user_analytics (
                user_id     text primary key,
                data        jsonb not null default '{}'::jsonb,
                computed_at timestamptz not null default to_timestamp(0)
            )
            """
        )
        conn.commit()

    _SCHEMA_READY = True


_ANALYTICS_TTL_SECONDS = 900  # 15 分鐘


def _analytics_cache_get(conn, user_id: str) -> dict | None:
    """若快取存在且未過期則回傳，否則回傳 None。"""
    row = conn.execute(
        """
        SELECT data, computed_at
        FROM user_analytics
        WHERE user_id = %s
          AND computed_at > now() - make_interval(secs => %s)
        """,
        (user_id, _ANALYTICS_TTL_SECONDS),
    ).fetchone()
    return _from_jsonb(row["data"], None) if row else None


def _analytics_cache_set(conn, user_id: str, data: dict) -> None:
    """寫入（upsert）快取。"""
    conn.execute(
        """
        INSERT INTO user_analytics (user_id, data, computed_at)
        VALUES (%s, %s::jsonb, now())
        ON CONFLICT (user_id) DO UPDATE
          SET data = EXCLUDED.data,
              computed_at = EXCLUDED.computed_at
        """,
        (user_id, _json(data)),
    )
    conn.commit()


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


_WEEKDAY_NAMES = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]


def get_analytics(
    user_id: str,
    college_map: dict[str, str] | None = None,
) -> dict:
    """從用戶歷史對話萃取學習傾向統計（15 分鐘快取）。"""
    if not user_id:
        return _empty_analytics()

    _ensure_schema()
    college_map = college_map or {}

    with _connect() as conn:
        cached = _analytics_cache_get(conn, user_id)
        if cached is not None:
            return cached

        session_row = conn.execute(
            "SELECT count(*)::int AS n FROM chat_sessions WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        total_sessions: int = session_row["n"] if session_row else 0

        rows = conn.execute(
            """
            SELECT t.tools_used, t.course_pool, t.course_cards, t.created_at
            FROM chat_turns t
            JOIN chat_sessions s ON s.session_id = t.session_id
            WHERE s.user_id = %s
            ORDER BY t.id ASC
            """,
            (user_id,),
        ).fetchall()

    total_turns = len(rows)
    seen_courses: set[str]            = set()
    dept_counter: dict[str, int]      = {}
    tool_counter: dict[str, int]      = {}
    card_name_counter: dict[str, int] = {}   # top_courses：來自 course_cards
    domain_tag_counter: dict[str, int] = {}  # 興趣標籤：course_cards.domain_tags
    ge_category_counter: dict[str, int] = {}  # 通識分類計數
    ge_codes: set[str] = set()               # 通識課程代碼，用於查 topic_tags
    course_domain_counter: dict[str, int] = {}  # 課程領域計數

    for row in rows:
        # 工具計數
        for tool in _from_jsonb(row["tools_used"], []):
            if isinstance(tool, str):
                tool_counter[tool] = tool_counter.get(tool, 0) + 1

        # course_pool：系所分佈 + 唯一課程數 + 通識分類
        for course in _from_jsonb(row["course_pool"], []):
            if not isinstance(course, dict):
                continue
            uid = course.get("code") or course.get("name", "")
            if uid:
                seen_courses.add(uid)
            dept = course.get("dept", "").strip()
            if dept:
                dept_counter[dept] = dept_counter.get(dept, 0) + 1
                ge_cat = GE_CATEGORY_MAP.get(dept)
                if ge_cat:
                    ge_category_counter[ge_cat] = ge_category_counter.get(ge_cat, 0) + 1
                    code = course.get("code", "").strip()
                    if code:
                        ge_codes.add(code)

            # 課程領域（從 course_index 查）
            code = course.get("code", "").strip()
            if code:
                for domain in _load_course_domains().get(code, []):
                    course_domain_counter[domain] = course_domain_counter.get(domain, 0) + 1

        # course_cards：AI 推薦課程名稱 + domain_tags 興趣標籤
        for card in _from_jsonb(row["course_cards"], []):
            if not isinstance(card, dict):
                continue
            name = card.get("name", "").strip()
            if name:
                card_name_counter[name] = card_name_counter.get(name, 0) + 1
            # domain_tags 格式："人工智慧::0.85||機器學習::0.72" 或純 "人工智慧||機器學習"
            for part in (card.get("domain_tags") or "").split("||"):
                part = part.strip()
                if not part:
                    continue
                if "::" in part:
                    tag, score_str = part.rsplit("::", 1)
                    tag = tag.strip()
                    try:
                        if tag and float(score_str) >= 0.5:
                            domain_tag_counter[tag] = domain_tag_counter.get(tag, 0) + 1
                    except ValueError:
                        if tag:  # 分數解析失敗，仍計入
                            domain_tag_counter[tag] = domain_tag_counter.get(tag, 0) + 1
                else:
                    domain_tag_counter[part] = domain_tag_counter.get(part, 0) + 1

    # ── 系所 Top 8（只保留 college_map 中有對應的真實系所）────────
    # course_pool 的 dept 欄位有時存學院名（如「工學院」院級課程），需過濾
    valid_depts = {d: c for d, c in dept_counter.items() if d in college_map}
    total_dept = sum(valid_depts.values()) or 1
    dept_distribution = [
        {"name": d, "count": c, "pct": round(c / total_dept * 100, 1)}
        for d, c in sorted(valid_depts.items(), key=lambda x: -x[1])[:8]
    ]

    # ── 學院 Top 5（從 dept 換算）────────────────────────────────
    college_counter: dict[str, int] = {}
    for dept, cnt in dept_counter.items():
        college = college_map.get(dept, "其他")
        college_counter[college] = college_counter.get(college, 0) + cnt
    total_col = sum(college_counter.values()) or 1
    college_distribution = [
        {"name": c, "count": n, "pct": round(n / total_col * 100, 1)}
        for c, n in sorted(college_counter.items(), key=lambda x: -x[1])[:5]
    ]
    fav_college = college_distribution[0]["name"] if college_distribution else ""

    # ── 工具使用頻率 ─────────────────────────────────────────────
    tool_usage = [
        {"tool": t, "label": TOOL_LABELS.get(t, t), "count": c}
        for t, c in sorted(tool_counter.items(), key=lambda x: -x[1])
    ]

    # ── AI 推薦課程 Top 10（來自 course_cards）────────────────────
    top_courses = [
        {"name": n, "count": c}
        for n, c in sorted(card_name_counter.items(), key=lambda x: -x[1])[:10]
    ]

    # ── 興趣標籤 Top 15（解析 course_cards.domain_tags）──────────
    top_domain_tags = [
        {"tag": t, "count": c}
        for t, c in sorted(domain_tag_counter.items(), key=lambda x: -x[1])[:15]
    ]

    # ── 通識 / 語言 / 體育 / 服務學習 分析 ───────────────────────
    ge_topic_counter: dict[str, int] = {}
    if ge_codes:
        topic_tags_db = _load_topic_tags()
        for code in ge_codes:
            for tag in topic_tags_db.get(code, {}).get("topic_tags", []):
                tag = str(tag).strip()
                if tag:
                    ge_topic_counter[tag] = ge_topic_counter.get(tag, 0) + 1

    GE_ORDER = ["通識", "外語", "體育", "服務學習"]
    ge_total = sum(ge_category_counter.values())
    general_edu = {
        "total": ge_total,
        "categories": [
            {"name": cat, "count": ge_category_counter.get(cat, 0)}
            for cat in GE_ORDER
            if ge_category_counter.get(cat, 0) > 0
        ],
        "top_topic_tags": [
            {"tag": t, "count": c}
            for t, c in sorted(ge_topic_counter.items(), key=lambda x: -x[1])[:20]
        ],
    }

    # ── 課程領域 Top 20 ──────────────────────────────────────────
    top_course_domains = [
        {"domain": d, "count": c}
        for d, c in sorted(course_domain_counter.items(), key=lambda x: -x[1])[:20]
    ]

    result = {
        "overview": {
            "total_sessions":         total_sessions,
            "total_turns":            total_turns,
            "total_courses_explored": len(seen_courses),
            "fav_college":            fav_college,
        },
        "dept_distribution":    dept_distribution,
        "college_distribution": college_distribution,
        "tool_usage":           tool_usage,
        "top_courses":          top_courses,
        "top_domain_tags":      top_domain_tags,
        "general_edu":          general_edu,
        "top_course_domains":   top_course_domains,
    }
    with _connect() as conn:
        _analytics_cache_set(conn, user_id, result)
    return result


def _empty_analytics() -> dict:
    return {
        "overview": {
            "total_sessions": 0, "total_turns": 0,
            "total_courses_explored": 0, "fav_college": "",
        },
        "dept_distribution":    [],
        "college_distribution": [],
        "tool_usage":           [],
        "top_courses":          [],
        "top_domain_tags":      [],
        "general_edu":          {"total": 0, "categories": [], "top_topic_tags": []},
        "top_course_domains":   [],
    }
