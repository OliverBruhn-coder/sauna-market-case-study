"""Excerpt from the scraper: how changes between two snapshots become events.

These functions are copied unchanged from the project. The surrounding file
(fetching, parsing and the provider loop) is not included."""

import json
import datetime as dt
import sqlite3
from typing import Any, Dict, Optional



def normalize_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:  # noqa: BLE001
        return None


def normalize_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    return bool(value)


def load_latest_snapshots(
    conn: sqlite3.Connection, actor: str
) -> Dict[str, sqlite3.Row]:
    sql = """
    WITH latest_snapshots AS (
      SELECT actor, session_id, MAX(scrape_timestamp) AS max_ts
      FROM session_snapshots
      WHERE actor = ?
      GROUP BY actor, session_id
    )
    SELECT
      ss.session_id,
      ss.capacity_total,
      ss.booked_count,
      ss.is_waitlist,
      ss.is_sold_out
    FROM session_snapshots ss
    JOIN latest_snapshots ls
      ON ls.actor = ss.actor
      AND ls.session_id = ss.session_id
      AND ls.max_ts = ss.scrape_timestamp
    WHERE ss.actor = ?
    """
    rows = conn.execute(sql, (actor, actor)).fetchall()
    return {row["session_id"]: row for row in rows}


def build_change_fields(
    prev_session: Optional[sqlite3.Row],
    prev_snapshot: Optional[sqlite3.Row],
    session: Dict[str, Any],
    snapshot: Dict[str, Any],
    is_new: bool,
) -> Dict[str, Any]:
    changes: Dict[str, Any] = {}
    meta_fields = [
        ("session_date", "date"),
        ("session_start_time", "start_time"),
        ("session_end_time", "end_time"),
        ("location_name", "location"),
        ("sauna_name", "sauna"),
        ("session_title", "title"),
        ("holdtype", "type"),
        ("instructor_name_raw", "instructor"),
    ]

    if not is_new:
        for field, key in meta_fields:
            prev_value = prev_session[field] if prev_session is not None else None
            curr_value = session.get(field)
            if prev_value != curr_value:
                changes[key] = {"from": prev_value, "to": curr_value}

    prev_booked = normalize_int(prev_snapshot["booked_count"]) if prev_snapshot else None
    curr_booked = normalize_int(snapshot.get("booked_count"))
    if curr_booked is not None:
        if is_new or prev_booked is None or prev_booked != curr_booked:
            delta = None if prev_booked is None else curr_booked - prev_booked
            changes["booked"] = {
                "from": prev_booked,
                "to": curr_booked,
                "delta": delta if delta is not None else curr_booked,
            }

    prev_capacity = normalize_int(prev_snapshot["capacity_total"]) if prev_snapshot else None
    curr_capacity = normalize_int(snapshot.get("capacity_total"))
    if curr_capacity is not None:
        if is_new or prev_capacity is None or prev_capacity != curr_capacity:
            delta = None if prev_capacity is None else curr_capacity - prev_capacity
            changes["capacity"] = {
                "from": prev_capacity,
                "to": curr_capacity,
                "delta": delta if delta is not None else curr_capacity,
            }

    prev_sold_out = normalize_bool(prev_snapshot["is_sold_out"]) if prev_snapshot else None
    curr_sold_out = normalize_bool(snapshot.get("is_sold_out"))
    if curr_sold_out is not None:
        if is_new or prev_sold_out is None or prev_sold_out != curr_sold_out:
            changes["sold_out"] = {"from": prev_sold_out, "to": curr_sold_out}

    prev_waitlist = normalize_bool(prev_snapshot["is_waitlist"]) if prev_snapshot else None
    curr_waitlist = normalize_bool(snapshot.get("is_waitlist"))
    if curr_waitlist is not None:
        if is_new or prev_waitlist is None or prev_waitlist != curr_waitlist:
            changes["waitlist"] = {"from": prev_waitlist, "to": curr_waitlist}

    return changes


def insert_change_event(conn: sqlite3.Connection, event: Dict[str, Any]) -> None:
    sql = """
    INSERT INTO session_change_events (
      actor,
      session_id,
      change_timestamp,
      change_type,
      change_fields,
      session_date,
      session_start_time,
      location_name,
      session_title
    ) VALUES (
      :actor,
      :session_id,
      :change_timestamp,
      :change_type,
      :change_fields,
      :session_date,
      :session_start_time,
      :location_name,
      :session_title
    )
    """
    conn.execute(sql, event)


def record_removed_sessions(
    conn: sqlite3.Connection,
    actor: str,
    existing_sessions: Dict[str, sqlite3.Row],
    current_ids: set,
    scrape_ts: str,
    today: dt.date,
) -> int:
    prev_row = conn.execute(
        """
        SELECT MAX(scrape_timestamp) AS ts
        FROM session_snapshots
        WHERE actor = ? AND scrape_timestamp < ?
        """,
        (actor, scrape_ts),
    ).fetchone()
    prev_ts = prev_row["ts"] if prev_row else None
    if not prev_ts:
        return 0

    prev_rows = conn.execute(
        "SELECT session_id FROM session_snapshots WHERE scrape_timestamp = ? AND actor = ?",
        (prev_ts, actor),
    ).fetchall()
    prev_ids = {row["session_id"] for row in prev_rows}
    removed_ids = prev_ids - current_ids
    if not removed_ids:
        return 0

    removed = 0
    for session_id in removed_ids:
        prev_session = existing_sessions.get(session_id)
        if prev_session is None:
            prev_session = conn.execute(
                """
                SELECT session_date, session_start_time, location_name, session_title
                FROM sessions
                WHERE actor = ? AND session_id = ?
                """,
                (actor, session_id),
            ).fetchone()
        if prev_session is None:
            continue
        session_date = prev_session["session_date"]
        if session_date:
            date_obj = date_from_iso(session_date)
            if date_obj and date_obj < today:
                continue

        event = {
            "actor": actor,
            "session_id": session_id,
            "change_timestamp": scrape_ts,
            "change_type": "removed",
            "change_fields": None,
            "session_date": prev_session["session_date"],
            "session_start_time": prev_session["session_start_time"],
            "location_name": prev_session["location_name"],
            "session_title": prev_session["session_title"],
        }
        insert_change_event(conn, event)
        removed += 1

    return removed
