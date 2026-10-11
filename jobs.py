"""Bizzmind — background job queue on Postgres (public.jobs / public.job_events).

Every AI task (chat turn, data review, deck, translation) is a row in
public.jobs. The API only enqueues and reads status; one or more worker
processes (worker.py) claim jobs with SELECT … FOR UPDATE SKIP LOCKED and run
them. Progress lines the user sees in the live feed are rows in job_events,
so any API instance can serve them — no state in process memory.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime

import db
from psycopg.types.json import Jsonb

log = logging.getLogger("studio")


def _ts(v):
    return v.isoformat() if isinstance(v, datetime) else v


def enqueue(project_id: str, kind: str, payload: dict, lang: str = "bg", user_id: str | None = None) -> str:
    with db.pool().connection() as con:
        row = con.execute(
            "INSERT INTO public.jobs (project_id, kind, payload, lang, created_by) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (project_id, kind, Jsonb(payload), lang, user_id)).fetchone()
        con.commit()
    log.info(f"[{project_id}] job {row[0]} queued: {kind}")
    return str(row[0])


def get(job_id: str) -> dict | None:
    with db.pool().connection() as con:
        r = con.execute(
            "SELECT id, project_id, kind, status, payload, result, error, lang, created_at, started_at, finished_at "
            "FROM public.jobs WHERE id = %s", (job_id,)).fetchone()
    if not r:
        return None
    keys = ("id", "project_id", "kind", "status", "payload", "result", "error", "lang",
            "created_at", "started_at", "finished_at")
    d = dict(zip(keys, r))
    d["id"] = str(d["id"])
    for k in ("created_at", "started_at", "finished_at"):
        d[k] = _ts(d[k])
    return d


def events(job_id: str, since: int = 0) -> list[dict]:
    with db.pool().connection() as con:
        rows = con.execute(
            "SELECT seq, kind, text, created_at FROM public.job_events "
            "WHERE job_id = %s AND seq > %s ORDER BY seq", (job_id, since)).fetchall()
    return [{"seq": r[0], "kind": r[1], "text": r[2], "ts": r[3].strftime("%H:%M:%S")} for r in rows]


def log_event(job_id: str, kind: str, text: str) -> None:
    try:
        with db.pool().connection() as con:
            con.execute(
                "INSERT INTO public.job_events (job_id, seq, kind, text) VALUES (%s, "
                "(SELECT coalesce(max(seq), 0) + 1 FROM public.job_events WHERE job_id = %s), %s, %s)",
                (job_id, job_id, kind, text[:500]))
            con.commit()
    except Exception as e:
        log.info(f"job {job_id}: event write failed — {e}")


def latest_for_project(project_id: str, kinds: tuple[str, ...] | None = None) -> dict | None:
    """Most recent running/queued job of a project (lets the UI re-attach after reload)."""
    q = ("SELECT id FROM public.jobs WHERE project_id = %s AND status IN ('queued','running')"
         + (" AND kind = ANY(%s)" if kinds else "") + " ORDER BY created_at DESC LIMIT 1")
    with db.pool().connection() as con:
        r = con.execute(q, (project_id, list(kinds)) if kinds else (project_id,)).fetchone()
    return get(str(r[0])) if r else None


# --------------------------------------------------------------- worker side

def claim() -> dict | None:
    with db.pool().connection() as con:
        r = con.execute(
            "UPDATE public.jobs SET status = 'running', started_at = now() "
            "WHERE id = (SELECT id FROM public.jobs WHERE status = 'queued' "
            "            ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) "
            "RETURNING id, project_id, kind, payload, lang, created_by").fetchone()
        con.commit()
    if not r:
        return None
    return {"id": str(r[0]), "project_id": r[1], "kind": r[2], "payload": r[3] or {},
            "lang": r[4], "created_by": r[5]}


def claim_by_id(job_id: str) -> dict | None:
    """Claim one specific queued job (serverless trigger right after enqueue)."""
    with db.pool().connection() as con:
        r = con.execute(
            "UPDATE public.jobs SET status = 'running', started_at = now() "
            "WHERE id = %s AND status = 'queued' "
            "RETURNING id, project_id, kind, payload, lang, created_by", (job_id,)).fetchone()
        con.commit()
    if not r:
        return None
    return {"id": str(r[0]), "project_id": r[1], "kind": r[2], "payload": r[3] or {},
            "lang": r[4], "created_by": r[5]}


def finish(job_id: str, result: dict | None, settle=None) -> bool:
    """Publish success and its credit deduction together, exactly once.

    The same row lock is used by cancellation. A stopped job cannot publish
    success or charge credits, and clients cannot observe done with an old balance.
    """
    with db.pool().connection() as con:
        row = con.execute("SELECT status FROM public.jobs WHERE id = %s FOR UPDATE", (job_id,)).fetchone()
        if not row or row[0] in ("cancelled", "failed"):
            return False
        if row[0] == "done":
            return True
        if settle is not None:
            settle(con)
        con.execute("UPDATE public.jobs SET status = 'done', result = %s, finished_at = now() WHERE id = %s",
                    (Jsonb(result or {}), job_id))
        con.commit()
    return True


_cancel_cache: dict = {}          # job_id -> (checked_at, cancelled?)


def cancel(job_id: str) -> bool:
    """Ask a queued/running job to stop. Returns False if it already finished."""
    with db.pool().connection() as con:
        row = con.execute(
            "UPDATE public.jobs SET status = 'cancelled', finished_at = now(), "
            "error = 'cancelled by user' WHERE id = %s AND status IN ('queued','running') "
            "RETURNING 1", (job_id,)).fetchone()
        con.commit()
    _cancel_cache[job_id] = (time.time(), bool(row))
    return bool(row)


def is_cancelled(job_id: str) -> bool:
    """Checked between agent steps — cached briefly so it costs nothing."""
    hit = _cancel_cache.get(job_id)
    if hit and time.time() - hit[0] < 1.5:
        return hit[1]
    with db.pool().connection() as con:
        row = con.execute("SELECT status FROM public.jobs WHERE id = %s", (job_id,)).fetchone()
    out = bool(row and row[0] == "cancelled")
    _cancel_cache[job_id] = (time.time(), out)
    return out


def fail(job_id: str, error: str) -> None:
    with db.pool().connection() as con:
        con.execute("UPDATE public.jobs SET status = 'failed', error = %s, finished_at = now() WHERE id = %s",
                    (error[:2000], job_id))
        con.commit()


def requeue_stale(max_running_s: int = 1800) -> int:
    """Jobs left 'running' by a crashed worker go back to the queue."""
    with db.pool().connection() as con:
        n = con.execute(
            "UPDATE public.jobs SET status = 'queued', started_at = NULL "
            "WHERE status = 'running' AND started_at < now() - make_interval(secs => %s)",
            (max_running_s,)).rowcount
        con.commit()
    return n


def wait(job_id: str, timeout_s: float = 900, poll_s: float = 1.0) -> dict:
    """Blocking helper for scripts/tests."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        j = get(job_id)
        if j and j["status"] in ("done", "failed"):
            return j
        time.sleep(poll_s)
    raise TimeoutError(job_id)
