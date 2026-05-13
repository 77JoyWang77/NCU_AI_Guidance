"""
update_schedule_payload.py

不重新嵌入，僅用 Qdrant set_payload API 更新 ncu_courses_ug / ncu_courses_grad
兩個 collection 中的學期資訊欄位。

新增/更新欄位：
  when_contexts     — list[str]，所有科系的 "{dept_id}@{when}" 完整列表
  when_is_dept_scoped — True：when 為系所相對時間，跨系過濾無意義
  when_year_start / when_year_end / when_sem_start / when_sem_end
  when_semesters    — list[str]，供 MatchAny 過濾（需同時指定 dept filter）
  verified          — bool，是否有任一科系人工驗證

執行：
  python scripts/rag/update_schedule_payload.py
"""

import json
import os
import re
from pathlib import Path

from qdrant_client import QdrantClient

BASE        = Path(__file__).parent.parent.parent
DATA_PROC   = BASE / "data" / "processed"
QDRANT_DIR  = DATA_PROC / "qdrant_data"
SCHEDULE_DIR = DATA_PROC / "schedule_draft"

COLLECTIONS = ["ncu_courses_ug", "ncu_courses_grad"]
SCROLL_LIMIT = 100

# ── 學期解析（與 build_vector_index.py 保持一致）────────────────────────────

_YEAR_MAP = {"一": 1, "二": 2, "三": 3, "四": 4}
_SEM_MAP  = {"上": 1, "下": 2}
_ALL_SEMS = [(y, s) for y in range(1, 5) for s in (1, 2)]


def _parse_single(s: str):
    m = re.search(r"大([一二三四])([上下])?", s)
    if not m:
        return None, None
    return _YEAR_MAP.get(m.group(1)), _SEM_MAP.get(m.group(2)) if m.group(2) else None


def parse_when(when_str: str, dept_id: str = "") -> dict:
    """解析代表性 when_str，回傳 Qdrant payload 基礎欄位（不含 when_contexts）。"""
    result = {
        "when_is_dept_scoped": True,
        "when_year_start": 0, "when_year_end": 0,
        "when_sem_start": 0,  "when_sem_end": 0,
        "when_semesters": [],
    }
    if not when_str:
        return result
    parts = [p.strip() for p in when_str.split("~")]
    y_s, s_s = _parse_single(parts[0])
    if y_s is None:
        return result
    y_e, s_e = _parse_single(parts[1]) if len(parts) > 1 else (y_s, s_s)
    if y_e is None:
        y_e, s_e = y_s, s_s
    result.update({
        "when_year_start": y_s,  "when_sem_start": s_s or 1,
        "when_year_end":   y_e,  "when_sem_end":   s_e or 2,
    })
    try:
        idx_s = _ALL_SEMS.index((y_s, result["when_sem_start"]))
        idx_e = _ALL_SEMS.index((y_e, result["when_sem_end"]))
        result["when_semesters"] = [f"{y}_{s}" for y, s in _ALL_SEMS[idx_s:idx_e + 1]]
    except ValueError:
        pass
    return result


# ── 建立 lookup {course_code: payload_dict} ──────────────────────────────────

def build_lookup() -> dict[str, dict]:
    """每個 course_code 累積所有科系的 when_context，
    存成 when_contexts list，解決多科系共必修時的非確定性問題。
    """
    from collections import defaultdict
    # code → list of (dept_id, when_str, verified)
    raw: defaultdict[str, list[tuple[str, str, bool]]] = defaultdict(list)

    def _index(courses: list, dept_id: str):
        for rc in courses:
            code = rc.get("code", "").strip()
            when = rc.get("when", "")
            if not code or not when:
                continue
            verified = rc.get("verified", False)
            raw[code].append((dept_id, when, verified))

    for college_dir in sorted(SCHEDULE_DIR.iterdir()):  # sorted → 確定性順序
        if not college_dir.is_dir():
            continue
        for dept_file in sorted(college_dir.glob("*.json")):
            try:
                data = json.loads(dept_file.read_text(encoding="utf-8"))
                dept_id = data.get("id", dept_file.stem)
                _index(data.get("required_courses", []), dept_id)
                for track in data.get("specialization_tracks", []):
                    tid = track.get("id", dept_id)
                    _index(track.get("required_courses", []), tid)
                    for grp in track.get("groups", []):
                        gid = grp.get("id", tid)
                        _index(grp.get("required_courses", []), gid)
                for grp in data.get("groups", []):
                    gid = grp.get("id", dept_id)
                    _index(grp.get("required_courses", []), gid)
            except Exception as e:
                print(f"  [WARN] {dept_file.name}: {e}")

    lookup: dict[str, dict] = {}
    for code, entries in raw.items():
        # 代表性 when：優先取 verified 的，否則取第一個
        rep = next((e for e in entries if e[2]), entries[0])
        rep_dept_id, rep_when, _ = rep
        base = parse_when(rep_when, dept_id=rep_dept_id)

        # when_contexts：所有科系的 dept_id@when（去重，sorted 確定性）
        all_contexts = sorted({
            f"{dept_id}@{when}" for dept_id, when, _ in entries if dept_id and when
        })
        base["when_contexts"] = all_contexts
        # verified：只要有任一科系驗證過即為 True
        base["verified"] = any(v for _, _, v in entries)
        lookup[code] = base

    multi = sum(1 for v in lookup.values() if len(v["when_contexts"]) > 1)
    print(f"Schedule lookup: {len(lookup)} 筆（其中 {multi} 門為多科系必修）")
    return lookup


# ── 主程式 ───────────────────────────────────────────────────────────────────

def main():
    lookup = build_lookup()
    if not lookup:
        print("lookup 為空，跳過")
        return

    qdrant_url = os.environ.get("QDRANT_URL", "")
    qdrant_api_key = os.environ.get("QDRANT_API_KEY")
    if qdrant_url:
        client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    else:
        client = QdrantClient(path=str(QDRANT_DIR))

    for col in COLLECTIONS:
        try:
            info = client.get_collection(col)
        except Exception:
            print(f"  Collection {col} 不存在，跳過")
            continue

        total = info.points_count
        print(f"\n[{col}] {total} 筆，開始掃描…")

        updated = 0
        offset = None
        while True:
            results, next_offset = client.scroll(
                collection_name=col,
                limit=SCROLL_LIMIT,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            if not results:
                break

            for point in results:
                code = (point.payload or {}).get("course_code", "")
                if not code:
                    # 嘗試從 id 解析
                    code = str(point.id).split("::")[0] if "::" in str(point.id) else ""
                if code and code in lookup:
                    client.set_payload(
                        collection_name=col,
                        payload=lookup[code],
                        points=[point.id],
                    )
                    updated += 1

            if next_offset is None:
                break
            offset = next_offset

        print(f"  → 更新 {updated} 筆")

        # 清除舊版欄位（when_raw、when_context 已由 when_contexts 取代）
        print(f"  清除舊欄位 when_raw / when_context …")
        stale_ids = []
        offset2 = None
        while True:
            results2, next2 = client.scroll(
                collection_name=col,
                limit=SCROLL_LIMIT,
                offset=offset2,
                with_payload=["when_raw", "when_context"],
                with_vectors=False,
            )
            if not results2:
                break
            for point in results2:
                p = point.payload or {}
                if "when_raw" in p or "when_context" in p:
                    stale_ids.append(point.id)
            if next2 is None:
                break
            offset2 = next2

        if stale_ids:
            BATCH = 200
            for i in range(0, len(stale_ids), BATCH):
                client.delete_payload(
                    collection_name=col,
                    keys=["when_raw", "when_context"],
                    points=stale_ids[i:i + BATCH],
                )
            print(f"  → 清除 {len(stale_ids)} 筆舊欄位")
        else:
            print(f"  → 無舊欄位需清除")

    print("\n✓ 完成")


if __name__ == "__main__":
    main()
