"""Bizzmind — background worker: runs queued AI jobs.

    .venv/bin/python worker.py            # loop forever
    .venv/bin/python worker.py --once     # run at most one job and exit

Runs alongside the API (locally two processes; in production a separate
service — Railway/Fly — because serverless functions cannot host it). Several
workers may run in parallel; Postgres row locks hand each job to exactly one.
Within one worker the Claude Agent SDK session per project is reused, so a
project's turns stay sequential (AGENT_LOCK in app.py).
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as core   # noqa: E402  (FastAPI module: agent, prompts, project logic)
import db
import jobs          # noqa: E402

log = logging.getLogger("studio")
_stop = False


def _sig(*_):
    global _stop
    _stop = True
    log.info("worker: stopping after current job…")


proj_ref: list = [None]


async def run_job(job: dict) -> dict:
    proj = core.get_project(job["project_id"])
    proj.app_touched = False
    proj_ref[0] = proj
    proj.lang = job.get("lang") or "bg"
    proj.job_id = job["id"]
    kind, p = job["kind"], job["payload"] or {}
    if kind in ("chat", "review"):
        from bizzmind import plans
        proj.ai_model_id = plans.MODELS[plans.norm_model(p.get("model"))]["model_id"]
    else:
        # Project objects are cached between jobs — a model picked for an
        # earlier chat must not silently carry into a flat-priced job.
        proj.ai_model_id = None
    try:
        if kind == "chat":
            from bizzmind.agent import set_chat_scope
            set_chat_scope(proj, p.get("scope", "dashboard"))
            proj.add_chat("user", p["message"])
            return await core.dispatch_agent(proj, p["message"], p.get("images") or [])
        if kind == "review":
            return await core.run_review(proj, p.get("tables") or [], p.get("context", ""), p.get("goal", ""))
        if kind == "app":
            from bizzmind.agent import run_app
            return await run_app(proj, p.get("brief") or "")
        if kind == "app_plan":
            from bizzmind.agent import run_app_proposal
            return await run_app_proposal(proj)
        if kind == "ingest":
            from bizzmind.routes.projects import run_ingest
            return await run_ingest(proj, p.get("filenames") or [])
        if kind == "deck":
            return await core.run_deck(proj)
        if kind == "translate":
            return await core.run_translate(proj)
        raise ValueError(f"unknown job kind '{kind}'")
    finally:
        proj.job_id = None
        core.PROJECTS.pop(proj.id, None)   # API processes reload from DB; don't keep stale copies here either


async def main(once: bool = False):
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)
    n = jobs.requeue_stale()
    if n:
        log.info(f"worker: re-queued {n} stale job(s)")
    log.info(f"worker: online (backend={core.AI_BACKEND})")
    idle = 0.0
    while not _stop:
        try:
            job = jobs.claim()
        except Exception as e:
            log.info(f"worker: db connection hiccup — {core._short(e, 120)}; reconnecting…")
            try:
                db.close()
            except Exception:
                pass
            await asyncio.sleep(2)
            continue
        if not job:
            if once:
                return
            await asyncio.sleep(min(2.0, 0.5 + idle))
            idle = min(idle + 0.25, 1.5)
            continue
        idle = 0.0
        t0 = time.monotonic()
        log.info(f"[{job['project_id']}] job {job['id']} start: {job['kind']}")
        try:
            result = await run_job(job)
            jobs.finish(job["id"], result)
            from bizzmind.routes.projects import _settle_job
            _settle_job(job["project_id"], job["id"], job["kind"], job["payload"] or {},
                        getattr(proj_ref[0], "app_touched", False) if proj_ref else False)
            log.info(f"[{job['project_id']}] job {job['id']} done in {time.monotonic() - t0:.1f}s")
        except core.CancelledByUser:
            jobs.cancel(job["id"])
            log.info(f"[{job['project_id']}] job {job['id']} cancelled by user — nothing charged")
            continue
        except Exception as e:
            log.info(f"[{job['project_id']}] job {job['id']} FAILED — {core._short(e, 200)}\n{traceback.format_exc()[-800:]}")
            jobs.fail(job["id"], str(e))
            log.info(f"[{job['project_id']}] failed {job['kind']} — nothing charged")
        if once:
            return


if __name__ == "__main__":
    asyncio.run(main(once="--once" in sys.argv))
