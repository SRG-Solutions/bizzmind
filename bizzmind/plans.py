"""Plans, limits and the unified credit pool.

One credit currency for the whole product; different actions cost a different
number of credits. The per-action breakdown lives in public.credit_events so
usage can be reported split (analyses vs presentations) without separate pools.
Volume-first pricing (the Gamma model): credits are cheap in bulk, actions
draw visibly large amounts. Anchor: EUR 20 -> 4000 credits (~EUR 0.005/cr).
"""
from __future__ import annotations

import os
from contextlib import nullcontext

from fastapi import HTTPException

from bizzmind.i18n import T
from db import pool

PLANS = {
    "free":  {"label": "Free",  "price_eur": 0,   "projects": 1,  "files_per_project": 2,
              "max_file_mb": 5,   "credits": 1000,  "monthly": False},
    "pro":   {"label": "Pro",   "price_eur": 25,  "projects": 10, "files_per_project": 50,
              "max_file_mb": 25,  "credits": 4000,  "monthly": True},
    "ultra": {"label": "Ultra", "price_eur": 99, "projects": 50, "files_per_project": 200,
              "max_file_mb": 100, "credits": 20000, "monthly": True},
}

# The user picks the model per project; each burns credits differently.
MODELS = {
    "standard": {"label": "Standard", "model_id": "claude-sonnet-5", "min_plan": "free"},
    "max":      {"label": "Max",      "model_id": "claude-opus-5",   "min_plan": "pro"},
}

# During a free trial the plan's features apply but credits are capped: the
# full quota arrives with the first real payment (prevents trial-switch abuse).
TRIAL_CREDITS = 2000

COSTS = {
    "analysis":     {"standard": 500, "max": 1200},
    "chat":         {"standard": 40,  "max": 100},
    # Rendering the deck. Estimate only — the real charge comes from the number
    # of credits the engine reports it consumed (27 and 39 on the two decks
    # measured, ~30-50 of ours). We resell this at cost: nothing is added to
    # the engine's own output, so the margin lives in the price of a credit.
    "presentation": {"standard": 80, "max": 80},     # engine cost does not depend on the model
    # The AI that writes the deck content and design brief. Estimate only: the
    # job settles on real token spend. Every chart's data goes into the prompt,
    # so the prediction grows with the dashboard — measured at $0.475 (126k input
    # tokens) for 8 charts. Predictions only warn or block; they never bill.
    "deck":         {"standard": 300, "max": 300},   # deck runs on the default model
}

# (max charts, multiplier) — the deck prompt carries every chart's sample rows
DECK_TIERS = [(8, 1.0), (16, 1.6), (10**9, 2.4)]


def deck_cost(charts: int, model: str | None = None) -> int:
    """Estimated credits for writing a deck about `charts` charts."""
    base = COSTS["deck"][norm_model(model)]
    for limit, mult in DECK_TIERS:
        if charts <= limit:
            return int(round(base * mult / 10.0) * 10)
    return int(round(base * DECK_TIERS[-1][1] / 10.0) * 10)


def presentation_total(charts: int = 0, model: str | None = None) -> int:
    """A presentation costs the user two things: writing the deck and rendering
    it. Both settle on real spend; quote them as one — they always happen together."""
    return deck_cost(charts, model) + cost_of("presentation", model)


# Credits are settled from what an action ACTUALLY costs us in AI spend.
# 1 credit sells for ~EUR 0.005; CREDITS_PER_USD keeps a healthy margin over
# the API price while staying a round, explainable number.
CREDITS_PER_USD = 500

# What one presentation-engine credit costs us, in USD: their 3000-credit pack
# is EUR 6, i.e. EUR 0.002 each. Update when the pack price changes — every
# presentation is billed from this number, so a stale rate quietly moves the
# margin. Overridable without a deploy.
ENGINE_CREDIT_USD = float(os.environ.get("ENGINE_CREDIT_USD") or 0.00216)


def engine_cost_usd(engine_credits: int) -> float:
    """What the engine's own consumption cost us, in dollars."""
    return max(0, int(engine_credits or 0)) * ENGINE_CREDIT_USD

# The prediction shown BEFORE the run (a warning or a block, never the bill):
# analysis price scales with how much data the AI has to read: a 45-sheet
# workbook costs us ~3x a 3-sheet one, so it costs the user more too.
ANALYSIS_TIERS = [(10, 1.0), (30, 1.6), (10**9, 2.4)]   # (max tables, multiplier)


def analysis_multiplier(tables: int) -> float:
    for limit, mult in ANALYSIS_TIERS:
        if tables <= limit:
            return mult
    return ANALYSIS_TIERS[-1][1]


def analysis_cost(tables: int, model: str | None = None) -> int:
    """Credits for analysing `tables` tables — rounded to a friendly 10."""
    base = COSTS["analysis"][norm_model(model)]
    return int(round(base * analysis_multiplier(tables) / 10.0) * 10)


def norm_model(model: str | None) -> str:
    return model if model in MODELS else "standard"


# What the user pays on top of our raw spend. The plan price already carries a
# margin per credit; this is the second lever, applied to every settled action.
# George's number to set — overridable without a deploy.
SPEND_MARKUP = float(os.environ.get("SPEND_MARKUP") or 1.5)

# A predicted spend at or above this share of the remaining balance gets a
# warning before the user commits (the balance not covering it blocks outright).
EXPENSIVE_SHARE = 0.25


def credits_from_usd(cost_usd: float) -> int:
    """Actual spend -> credits, marked up, rounded up to a friendly 10.
    Nothing spent, nothing charged."""
    import math
    if not cost_usd or cost_usd <= 0:
        return 0
    return max(10, int(math.ceil(cost_usd * CREDITS_PER_USD * SPEND_MARKUP / 10.0) * 10))


def expensive(estimate: int, remaining: int) -> bool:
    """Worth warning about before the run: the prediction eats a big bite of
    what is left. (Not affordable at all is a separate, blocking answer.)"""
    return remaining > 0 and estimate >= remaining * EXPENSIVE_SHARE


def cost_of(kind: str, model: str | None = None, tables: int = 0) -> int:
    if kind == "analysis" and tables:
        return analysis_cost(tables, model)
    return COSTS[kind][norm_model(model)]


def model_allowed(plan: str, model: str | None) -> bool:
    return MODELS[norm_model(model)]["min_plan"] == "free" or plan != "free"

# Paddle price ids per plan/interval (sandbox; swap for live ids at go-live)
PADDLE_PRICES = {
    ("pro", "month"):   "pri_01m0ypmaj7gejthhejwz3xp007",
    ("pro", "year"):    "pri_01m0ypmat13ejyjjaybs7skbw9",
    ("ultra", "month"): "pri_01m0ypmb7repkv0p3cdhcxebad",
    ("ultra", "year"):  "pri_01m0ypmbesr5ye6500ddp89sa3",
}

PACK_PADDLE_PRICES = {
    1000:  "pri_01m0ypmbwa6kam1zhhvmwtm5hc",
    4000:  "pri_01m0ypmc9a6dz56frqj8zbx87k",
    10000: "pri_01m0ypmcqvy68jfqtdbzgxbg15",
}

# top-up packs: the bigger the pack, the better the rate
PACKS = [
    {"credits": 1000,  "price_eur": 7},
    {"credits": 4000,  "price_eur": 20},
    {"credits": 10000, "price_eur": 40},
]


def org_of_project(pid: str):
    with pool().connection() as con:
        row = con.execute("SELECT org_id FROM public.projects WHERE id = %s", (pid,)).fetchone()
    return row[0] if row else None


def _renew_if_due(con, org_id) -> None:
    """Gamma-style rollover: on each monthly renewal the unused part of the
    plan allowance carries over, capped at 2x the monthly amount. Purchased
    top-ups (credits_extra) never expire. Lazy until a billing cycle exists."""
    row = con.execute(
        "SELECT plan, credits_quota, credits_used, credits_renewed_at "
        "FROM public.organizations WHERE id = %s "
        "AND credits_renewed_at < now() - interval '30 days'", (org_id,)).fetchone()
    if not row:
        return
    plan, quota, used, _ = row
    p = PLANS.get(plan, PLANS["free"])
    if not p["monthly"]:
        return
    monthly = p["credits"]
    new_quota = min(max(0, quota - used) + monthly, 2 * monthly)
    con.execute("UPDATE public.organizations SET credits_quota = %s, credits_used = 0, "
                "credits_renewed_at = now() WHERE id = %s", (new_quota, org_id))


def org_state(org_id) -> dict:
    with pool().connection() as con:
        _renew_if_due(con, org_id)
        row = con.execute(
            "SELECT plan, credits_quota, credits_extra, credits_used, auto_recharge, name "
            "FROM public.organizations WHERE id = %s", (org_id,)).fetchone()
    if not row:
        return {"plan": "free", "quota": 0, "extra": 0, "used": 0,
                "remaining": 0, "auto_recharge": False, "org_name": ""}
    plan, quota, extra, used, auto, name = row
    if plan not in PLANS:
        plan = "free"
    return {"plan": plan, "quota": quota, "extra": extra, "used": used,
            "remaining": max(0, quota + extra - used), "auto_recharge": auto, "org_name": name}


def limits_of(plan: str) -> dict:
    return PLANS.get(plan, PLANS["free"])


def project_count(org_id) -> int:
    with pool().connection() as con:
        return con.execute("SELECT count(*) FROM public.projects WHERE org_id = %s",
                           (org_id,)).fetchone()[0]


def ensure_can_afford(pid: str, kind: str, lang: str, model: str | None = None, tables: int = 0,
                      need: int | None = None) -> None:
    """Pre-flight check (no deduction) — used before spending on the engine.
    `need` overrides the price when one action bills in several parts."""
    org = org_of_project(pid)
    if org is None:
        return
    st = org_state(org)
    if not model_allowed(st["plan"], model):
        raise HTTPException(403, T(lang, "model_not_in_plan"))
    if need is None:
        need = cost_of(kind, model, tables)
    if st["remaining"] < need:
        raise HTTPException(402, T(lang, "no_credits_need", need=need, have=st["remaining"]))


def reserve(pid: str, kind: str, lang: str, model: str | None = None, tables: int = 0) -> int:
    """Pre-flight: refuse the action when the ESTIMATE does not fit the balance.
    Nothing is deducted here — the real charge happens on settle()."""
    est = cost_of(kind, model, tables)
    ensure_can_afford(pid, kind, lang, model, tables)
    return est


def settle(pid: str, kind: str, cost_usd: float, estimate: int = 0, model: str | None = None,
           *, connection=None) -> int:
    """Charge exactly what the action cost us, marked up. Returns the credits
    taken. The estimate is accepted so callers stay unchanged, but it no longer
    caps the charge: a cap made us absorb every overrun (one looping message
    cost $2.71 and billed 50 credits). Runaways are stopped by the turn ceiling
    and flagged before the run — not paid for by us afterwards."""
    credits = credits_from_usd(cost_usd)
    org = org_of_project(pid)
    if org is None or credits <= 0:
        return 0
    with (nullcontext(connection) if connection is not None else pool().connection()) as con:
        con.execute("UPDATE public.organizations SET credits_used = credits_used + %s WHERE id = %s",
                    (credits, org))
        con.execute("INSERT INTO public.credit_events (org_id, project_id, kind, credits) "
                    "VALUES (%s, %s, %s, %s)", (org, pid, kind, credits))
    return credits


def charge(pid: str, kind: str, lang: str, model: str | None = None, tables: int = 0) -> None:
    """Deduct the action's price atomically; 402 when the pool can't cover it."""
    org = org_of_project(pid)
    if org is None:
        return
    if not model_allowed(org_state(org)["plan"], model):
        raise HTTPException(403, T(lang, "model_not_in_plan"))
    cost = cost_of(kind, model, tables)
    with pool().connection() as con:
        row = con.execute(
            "UPDATE public.organizations SET credits_used = credits_used + %s "
            "WHERE id = %s AND credits_used + %s <= credits_quota + credits_extra "
            "RETURNING 1", (cost, org, cost)).fetchone()
        if not row:
            st = org_state(org)
            raise HTTPException(402, T(lang, "no_credits_need", need=cost, have=st["remaining"]))
        con.execute("INSERT INTO public.credit_events (org_id, project_id, kind, credits) "
                    "VALUES (%s, %s, %s, %s)", (org, pid, kind, cost))


def refund(pid: str, kind: str, model: str | None = None, tables: int = 0) -> None:
    """Reverse one charge (job failed — the user must not pay for nothing)."""
    cost = cost_of(kind, model, tables)
    org = org_of_project(pid)
    if org is None:
        return
    with pool().connection() as con:
        con.execute("UPDATE public.organizations SET credits_used = GREATEST(0, credits_used - %s) "
                    "WHERE id = %s", (cost, org))
        con.execute("DELETE FROM public.credit_events WHERE id = ("
                    "SELECT id FROM public.credit_events WHERE org_id = %s AND kind = %s "
                    "ORDER BY id DESC LIMIT 1)", (org, kind))


def usage_breakdown(org_id) -> list[dict]:
    with pool().connection() as con:
        rows = con.execute(
            "SELECT kind, count(*), sum(credits) FROM public.credit_events "
            "WHERE org_id = %s GROUP BY kind ORDER BY sum(credits) DESC", (org_id,)).fetchall()
    return [{"kind": k, "count": n, "credits": c} for k, n, c in rows]
