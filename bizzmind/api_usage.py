"""Rate reported Messages API usage before the job settles its credits.

Rates verified 2026-10-11 for our configured models and their fallback:
https://platform.claude.com/docs/en/about-claude/pricing
https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback
Cache-credit adjustments are already reflected in the returned token counts.
"""
from decimal import Decimal
import re

# USD per million tokens: fresh input, output. Cache writes are 1.25x/2x
# for 5m/1h; reads are 0.1x for these models. Unknown rates must not become $0.
RATES = {
    "claude-sonnet-5": (2, 10),
    "claude-opus-5": (5, 25),
    "claude-opus-4-8": (5, 25),
}


def _dict(value):
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return vars(value) if value is not None else {}


def response_usage(response) -> tuple[int, int, float]:
    """Count each provider iteration once, using the model that actually ran."""
    message = _dict(response)
    usage = _dict(message.get("usage"))
    if not usage or "input_tokens" not in usage or "output_tokens" not in usage:
        raise ValueError("Missing API usage")
    parts = usage.get("iterations") or [dict(usage, model=message.get("model"))]
    tokens_in = tokens_out = 0
    total = Decimal(0)
    for index, value in enumerate(parts):
        part = _dict(value)
        model = re.sub(r"-\d{8}$", "", part.get("model") or message.get("model") or "")
        if model not in RATES:
            raise ValueError(f"No API billing rates configured for {model!r}")
        fresh = int(part.get("input_tokens") or 0)
        output = int(part.get("output_tokens") or 0)
        written = int(part.get("cache_creation_input_tokens") or 0)
        read = int(part.get("cache_read_input_tokens") or 0)
        tokens_in += fresh + written + read
        tokens_out += output
        # An ordinary refusal before output is not billed. Retain its usage
        # for diagnostics without charging it alongside the successful fallback.
        refused = index < len(parts) - 1 or message.get("stop_reason") == "refusal"
        details = _dict(part.get("stop_details") or message.get("stop_details"))
        if refused and not output and details.get("category") not in {"bio", "frontier_llm", "reasoning_extraction"}:
            continue
        cache = _dict(part.get("cache_creation"))
        hour = int(cache.get("ephemeral_1h_input_tokens") or 0)
        if min(fresh, output, written, read, hour) < 0 or hour > written:
            raise ValueError("Invalid API token counts")
        base, out_rate = map(Decimal, RATES[model])
        cost = (base * (fresh + Decimal("1.25") * (written - hour) + 2 * hour + Decimal("0.1") * read)
                + out_rate * output) / 1_000_000
        if usage.get("speed") == "fast":
            if model not in {"claude-opus-5", "claude-opus-4-8"}:
                raise ValueError(f"No fast-mode billing rate for {model}")
            cost *= 2
        if usage.get("inference_geo") == "us":
            cost *= Decimal("1.1")
        if usage.get("service_tier") == "batch":
            cost *= Decimal("0.5")
        total += cost
    return tokens_in, tokens_out, float(total)


def record_response(proj, response) -> None:
    if not proj.job_id:
        return
    import db
    from bizzmind.config import log
    incoming, outgoing, cost = response_usage(response)
    with db.pool().connection() as con:
        con.execute(
            "UPDATE public.jobs SET tokens_in = COALESCE(tokens_in,0) + %s, "
            "tokens_out = COALESCE(tokens_out,0) + %s, "
            "cost_usd = COALESCE(cost_usd,0) + %s WHERE id = %s",
            (incoming, outgoing, cost, proj.job_id))
    log.info("[%s] API usage: in=%s out=%s cost=$%.6f", proj.id, incoming, outgoing, cost)
