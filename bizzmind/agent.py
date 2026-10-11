"""AI agent: prompts, tool schema/execution, subscription (Agent SDK) and API
backends, and the long-running tasks built on them (review, deck, translate)."""

from __future__ import annotations

from bizzmind.app_spec import validate_app_spec

import asyncio
import json
import os
import re
import time

import db
import jobs


class CancelledByUser(Exception):
    """The user pressed stop while the agent was working."""

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from bizzmind.config import (AI_BACKEND, MAX_CHART_ROWS, MAX_PREVIEW_ROWS, MAX_SERIES, MODEL,
                             SUB_TIMEOUT_S, _short, log)
from bizzmind.i18n import LANG_NAMES, T
from bizzmind.project import Project, write_progress
from bizzmind.data import (invalidate, FORBIDDEN_SQL, apply_filters_to_sql, describe_schema, frame_to_records,
                           pg_compat, resolve_filter_options, run_readonly_sql, verify_dashboard)
from bizzmind.brand import brand_excerpt, brand_files
from bizzmind.localization import _h, _load_i18n, _save_i18n, content_lang, translatable_items

# The Claude Agent SDK (local subscription mode) is optional: production runs on
# the Anthropic API and the SDK — which bundles the Claude Code CLI — is not
# installed there (see requirements-dev.txt).
try:
    from claude_agent_sdk import (  # noqa: E402
        AssistantMessage,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        ResultMessage,
        TextBlock,
        create_sdk_mcp_server,
        tool,
    )
    SDK_AVAILABLE = True
except ImportError:  # pragma: no cover
    SDK_AVAILABLE = False
    AssistantMessage = ClaudeAgentOptions = ClaudeSDKClient = ResultMessage = TextBlock = None  # type: ignore

    def tool(*_a, **_k):  # type: ignore
        return lambda f: f

    def create_sdk_mcp_server(*_a, **_k):  # type: ignore
        return None


# One ceiling for both backends. A fix-check-fix loop is the expensive failure
# mode: one message reached 41 turns and $2.71 before the subscription cap
# stopped it, while the API path had no cap at all.
MAX_TURNS = 40
# Consecutive failed dashboard checks before the agent must stop repairing and
# tell the user what is still broken.
MAX_VERIFY_RETRIES = 3

_client = None


class _LazyClient:
    """anthropic.Anthropic() needs ANTHROPIC_API_KEY at construction (and the
    import costs ~0.3 s on a cold start) — create it on first use."""
    def __getattr__(self, name):
        global _client
        if _client is None:
            import anthropic
            _client = anthropic.Anthropic()
        return getattr(_client, name)


client = _LazyClient()


CALCULATOR_GUIDANCE = """
Optional scenario calculators are supported in the App tab. Offer one ONLY when
it serves a concrete decision in this project's data and the user's goal. Never
add a generic calculator to every app or default to mortgages. Select the relevant
model; do not offer a menu of unrelated calculator types inside the app.
View format: {"type":"calculator","title":"<specific business decision>",
"hint":"<where starting values came from and which are assumptions>",
"calculator":{"kind":"forecast|investment|demand|mortgage","currency":"EUR|USD|GBP|BGN",
"defaults":{...all inputs for the selected model...}}}.
Models and required numeric inputs:
- forecast: revenue (base annual revenue), growth (annual %, -100..200), margin
  (gross margin %, 0..100), costs (annual fixed costs), years (integer 1..10).
  Compounding revenue growth, fixed margin and annual fixed costs; no tax/financing.
- investment: initial, contribution (month-end amount), return (effective annual
  %, -50..100), years (integer 1..40). Monthly compounding; no tax/fees/inflation.
  This is an accumulation model, NOT project ROI/NPV/IRR. Do not promise unsupported models.
- demand: demand (units per 30-day month), growth (one-time adjustment %, -100..200),
  stock, incoming (units arriving in one delivery), lead (days until that delivery,
  integer 0..365), horizon (planning days, integer 1..365), safety (buffer days,
  integer 0..365). Uniform daily demand, stock trajectory and additional stock
  needed for horizon plus buffer; not a statistical or seasonal demand forecast.
- mortgage: price, down (0..price), rate (fixed nominal annual %, 0..30), years
  (integer 1..40), extra (additional monthly payment). Only for property financing.
Monetary/quantity inputs must be nonnegative. Required defaults must come from
observed data, confirmed business context or explicit user assumptions. Read data
with run_sql_query when available; ask focused questions when inputs or units are
missing. Never invent company figures, silently assume a currency, or present
illustrative assumptions as facts. Label source/period/units in hint. If the
available model does not fit, clarify instead of misrepresenting the calculation.
Optional calculator.charts customizes the LIVE accompanying charts. Omit it for
context-specific defaults (2-3 charts). Each chart: {"title":"<user language>",
"chart_type":"line|area|bar","y_fields":["<model output>"],"compare_baseline":true|false}.
Allowed output names: mortgage: balance, principal_paid, interest_paid (cumulative);
forecast: revenue, profit, expenses; investment: value, contributed, gain;
demand: stock (may be negative), shortage, demand (cumulative), receipts (cumulative).
IMPORTANT: demand and receipts ARE running totals from day 0, not daily flows.
Cumulative demand/receipts charts are supported directly; never claim otherwise.
Use 1-6 charts, at most 3 per row. Every chart uses the scenario's year/day axis.
To change calculator charts through chat, edit calculator.charts in the COMPLETE
app spec, preserving its inputs and unrelated views. Do NOT create SQL/dashboard
charts for this: calculator charts recalculate from the same live input state.
Calculators update instantly in the browser without another AI call. They support
a temporary comparison baseline; they do NOT write back to project records, save
scenarios across navigation, or automatically refresh their starting values from
spreadsheet data. Preserve existing views when adding one through update_app.
"""

SCENARIO_GUIDANCE = """
Build an INTERACTIVE decision workspace when the user asks for a calculator,
what-if model, sensitivity analysis or scenario planning. Static KPI/table/chart
views cannot fulfill that request. Prefer a custom scenario for business models
that do not match the four preset calculators. Never substitute an accumulation
calculator for project investment economics.
Custom view: {"type":"scenario","title":"<decision>","hint":"<source workbook,
period, units and explicit modeling assumptions/limitations>","scenario":{
"inputs":[{"id":"price","label":"Price","unit":"USD","value":10,"min":0,"max":100,"step":1}],
"periods":5,"period_label":"Year",
"outputs":[{"id":"revenue","label":"Revenue","unit":"USD","formula":["mul","price",100]},
{"id":"cash","label":"Cumulative cash","unit":"USD","initial":-1000,"formula":["add","prev.cash","revenue"]}],
"metrics":[{"output":"cash","aggregate":"last","label":"Closing cash"}],
"charts":[{"title":"Cash outlook","chart_type":"line","y_fields":["cash"],"compare_baseline":true}],
"presets":[{"name":"Illustrative higher price","values":{"price":12}}]}}.
This is a FORMAT EXAMPLE, not real company data. Read project data before building.
Use 1-16 bounded inputs, 1-24 ordered outputs, 1-6 metrics, 1-6 live charts and
0-5 clearly labeled hypothetical presets. Only propose a relevant model.
Formulas are prefix arrays, never JavaScript or SQL: add/mul/min/max (2-16 args),
sub/div/pow/gt/gte/lt/lte (2), abs (1), if (condition, true, false; lazy branches).
References are input ids, earlier output ids in the SAME period, "period" (1-based),
or "prev.<output>". Output initial defaults to zero and can use inputs only.
IDs: lowercase ASCII letters/digits/underscores, start with a letter, <=40 chars;
"period", "constructor", "prototype" are reserved. No cycles in same-period outputs.
periods is a number or input expression resolving to an integer 1-120. Use at most
12 expression levels and 1500 expression nodes. Guard zero denominators with if.
Metrics aggregate an output over periods using last/sum/min/max. Units are per output.
Keep input, output and chart labels concise (ideally under 40 characters); put
modeling details in hint. Keep hint to 3-5 short sentences so controls remain visible.
Match labels to the exact formula; distinguish operating cash, cumulative cash,
NPV, enterprise value and cash including terminal value. Do not imply a partial
sensitivity model recalculates every accounting dependency in the workbook.
Use current data for defaults; explain fixed vs variable costs and tax treatment.
Do not invent missing business assumptions: ask focused questions before building.
Changing inputs updates metrics and charts instantly with NO AI call. Users can
save named scenarios in THIS BROWSER only, apply them or compare them as baseline.
Saved scenarios are NOT shared, do not update source records, and starting data
is a snapshot. Changes to the model create a separate saved-scenario collection.
Use update_app with the complete spec to modify inputs, formulas or live charts.
Preserve unrelated sections when adding a module; put the new requested workflow
first or set the app's start_view (zero-based index) to it. A meaningful app may
contain just ONE scenario view: don't pad it with report tables or duplicate KPIs.
"""

APP_CHAT_TOOLS = {"run_sql_query", "update_app", "present_questions"}
APP_CHAT_RULES = SCENARIO_GUIDANCE + CALCULATOR_GUIDANCE + """You are the builder inside the App tab. Work ONLY on the app, never the dashboard.
The user describes operations they want to perform on spreadsheet data. Build usable entry/edit
forms, working lists and context-relevant scenario calculators via update_app, not dashboard charts or a narrative analysis.
For editing existing records use an entry view with mode="edit", table (or tables), and fields.
The UI lets the user find and select a record, review its values and explicitly save changes.
For adding records use mode="insert" (default). Each field must reference a real source column.
Only expose fields needed for the requested operation; preserve historical fields unless requested.
Do not claim that adding a form has changed any records. Do not write data through agent tools.
For a broad new workflow first ask 2-3 focused questions with present_questions and propose a
small concrete workflow; build after their choice. Apply clear small changes directly.
Use the current_app spec below as the starting point, preserve unrelated sections, and return
all user-facing labels, hints and generated query aliases in the request language.
Charts, if explicitly requested, belong inside the app spec. Dashboard tools are unavailable.
"""


def set_chat_scope(proj: Project, scope: str) -> None:
    if getattr(proj, "chat_scope", "dashboard") != scope:
        proj.messages = []
        proj.sub_lang = None  # reconnect: the old session may contain another workspace's goals
    proj.chat_scope = scope


def conversation_recap(proj: Project, limit: int = 14) -> str:
    if not proj.chat:
        return ""
    who = {"user": "User", "ai": "You (assistant)", "event": "Event"}
    lines = [f"{who.get(m['role'], m['role'])}: {_short(m['text'], 400)}" for m in [m for m in proj.chat if m.get("scope", "dashboard") == getattr(proj, "chat_scope", "dashboard")][-limit:]]
    return ("<conversation_recap>\nThe app restarted. This is the recent conversation — "
            "continue from here; do NOT restart the interview or re-ask answered questions:\n"
            + "\n".join(lines) + "\n</conversation_recap>\n\n")


# ------------------------------------------------------------------- tools

TOOLS = [
    {
        "name": "run_sql_query",
        "description": (
            "Run a read-only PostgreSQL query against the user's uploaded data to "
            "explore it or verify results. Returns up to 50 rows. Use double quotes "
            "around identifiers. ALWAYS fill `purpose`: a short, non-technical line "
            "in the user's language saying what you are finding out — it is shown "
            "live in the UI instead of the SQL (e.g. 'Сравнявам оборота по обекти', "
            "'Проверявам кои дни имат липсващи данни')."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string"},
                "purpose": {"type": "string",
                            "description": "Short human sentence in the user's language: what this query finds out."},
            },
            "required": ["sql", "purpose"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_data_context",
        "description": (
            "Permanently save a fact about the user's data so it is remembered in "
            "every future conversation: what a file/table represents, what a code or "
            "SKU means, units, currency, fiscal calendar, business definitions. Save "
            "each distinct fact as one short note, in the user's own terms. Use this "
            "immediately whenever the user explains something about their data."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"note": {"type": "string"}},
            "required": ["note"],
            "additionalProperties": False,
        },
    },
    {
        "name": "define_filter",
        "description": (
            "Define a dashboard filter. type 'multi' is a multi-select over data "
            "values: 'column' is the column name the filter constrains and "
            "'options_sql' returns its choices (SELECT DISTINCT ... ORDER BY); pass "
            "options as []. type 'single' is an exclusive toggle (e.g. '€ / boxes') "
            "whose selected option is substituted literally into chart SQL: pass the "
            "choices in 'options' as valid SQL fragments (e.g. column names), with "
            "options_sql '' and column ''. Charts opt in by placing the token "
            "{{filter_id}} in their SQL. Defining a filter with an existing id "
            "replaces it."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
                "label": {"type": "string"},
                "type": {"type": "string", "enum": ["multi", "single"]},
                "column": {"type": "string"},
                "options_sql": {"type": "string"},
                "options": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["id", "label", "type", "column", "options_sql", "options"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_chart",
        "description": (
            "Edit an existing dashboard chart by id: fix its SQL, wire it to "
            "filters via {{filter_id}} tokens, change type/fields/title/insight. "
            "Use this to keep ALL charts responding to the global filters — "
            "especially right after defining a new filter."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "title": {"type": "string"},
                "chart_type": {"type": "string", "enum": ["bar", "line", "area", "pie", "scatter", "table"]},
                "sql": {"type": "string"},
                "x_field": {"type": "string"},
                "y_fields": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 8},
                "insight": {"type": "string"},
            },
            "required": ["id", "title", "chart_type", "sql", "x_field", "y_fields", "insight"],
            "additionalProperties": False,
        },
    },
    {
        "name": "delete_chart",
        "description": "Remove a chart from the dashboard by id.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_app",
        "description": (
            SCENARIO_GUIDANCE + CALCULATOR_GUIDANCE + "Change the project's mini-app (the App tab): add, edit, remove or reorder its "
            "views. Pass the COMPLETE new spec — it replaces the old one, so start from the "
            "current app given in <current_app> and apply only what the user asked for. "
            "Every view also accepts optional layout: \"collapsible\":true makes it a fold-out "
            "panel, \"collapsed\":true starts it folded, \"width\":\"half\"|\"full\" sets how much "
            "of the row it takes. Use them when the user asks for a tidier screen. "
            "Views: {\"type\":\"kpi\",\"title\":str,\"items\":[{\"label\":str,\"sql\":str,\"unit\":str}]} | "
            "{\"type\":\"entry\",\"title\":str,\"hint\":str,\"table\":str or \"tables\":[{\"table\":str,\"label\":str}],"
            "\"fields\":[{\"column\":str,\"label\":str,\"type\":\"text|number|date|select\",\"required\":bool,\"options_sql\":str}]} | "
            "{\"type\":\"table\",\"title\":str,\"hint\":str,\"sql\":str}. "
            'Charts: {"type":"chart","title":str,"hint":str,"sql":str,"chart_type":"bar|line|area|pie","x_field":str,"y_fields":[str]}. '
            "Use charts for trends and comparisons; fields must exactly match query output columns. "
            "The app provides section navigation, searchable sortable tables and section-specific editing. "
            'Entry views accept "mode":"edit" to select and update existing records, or "mode":"insert" for new records. Only include writable fields needed for the task; never invent columns. '
            "SQL must be read-only SELECT over the real tables; KPI sql returns one row, one column. "
            "Titles and labels in the user's language. Use this whenever the user asks to change "
            "how their app looks or works."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "spec": {"type": "string",
                         "description": "The complete new app spec as a JSON string: {title, subtitle, views:[...]}"},
                "summary": {"type": "string",
                            "description": "One short sentence in the user's language: what changed."},
            },
            "required": ["spec", "summary"],
            "additionalProperties": False,
        },
    },
    {
        "name": "define_view",
        "description": (
            "Create or replace a semantic VIEW in the project database — the "
            "stable interface between raw uploaded tables and the dashboard. "
            "Views unify/unpivot/rename raw data into clean business columns "
            "(e.g. v_sales with month/rep/product/channel/revenue/units, named in the UI language). "
            "ALL charts and filters must query views, never raw tables — so when "
            "new files arrive you only update the view and everything keeps "
            "working. name must start with 'v_'; sql is the SELECT body."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "pattern": "^v_[a-z0-9_]+$"},
                "sql": {"type": "string"},
                "description": {"type": "string",
                                "description": "One line: what this view represents, in the UI language."},
            },
            "required": ["name", "sql", "description"],
            "additionalProperties": False,
        },
    },
    {
        "name": "drop_view",
        "description": "Remove a semantic view that nothing references any more.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "pattern": "^v_[a-z0-9_]+$"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "verify_dashboard",
        "description": (
            "Run the automated health-check of the whole dashboard: executes every "
            "chart under real filter selections, validates declared fields, detects "
            "duplicate/dead/unused filters. MANDATORY as your last tool call in any "
            "turn that created or changed charts or filters — fix every reported "
            "error and re-run until ok:true before writing your final reply."
        ),
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [],
                         "additionalProperties": False},
    },
    {
        "name": "present_questions",
        "description": (
            "Present your questions to the user as an interactive form with "
            "clickable suggested answers (plus a free-text 'other' option the UI "
            "adds automatically). ALWAYS use this instead of writing questions as "
            "plain text — whenever you need to ask the user anything: clarifying "
            "the data, what they want on the dashboard, choices between options. "
            "1-4 questions per call; each with 2-4 short, concrete suggested "
            "options drawn from what you actually see in their data. Keep your "
            "accompanying text reply short — the questions carry the detail."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "minItems": 1, "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "options": {"type": "array", "items": {"type": "string"},
                                        "minItems": 2, "maxItems": 6},
                            "multi": {
                                "type": "boolean",
                                "description": "true when several answers can apply at once (multi-select)",
                            },
                        },
                        "required": ["question", "options", "multi"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["questions"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_chart",
        "description": (
            "Add a chart to the user's dashboard. The SQL is executed server-side and "
            "its result rows feed the chart. x_field and y_fields must be column "
            "names (or aliases) produced by the SQL. Aggregate in SQL so the result "
            "has one row per x value (a few hundred rows max). For 'pie', y_fields "
            "has exactly one entry and there should be at most 6 slices — otherwise "
            "use a bar chart. For 'table', x_field and y_fields list the columns to "
            "display. Never create a chart with two different value scales; make two "
            "charts instead. The dashboard is dynamic: put {{filter_id}} tokens in "
            "the SQL (inside WHERE for multi filters; as the substituted fragment "
            "for single filters) so the chart responds to the dashboard filters — "
            "every filter change re-runs the SQL live."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "chart_type": {"type": "string", "enum": ["bar", "line", "area", "pie", "scatter", "table"]},
                "sql": {"type": "string"},
                "x_field": {"type": "string"},
                "y_fields": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 8},
                "insight": {
                    "type": "string",
                    "description": "One-sentence business takeaway from this chart, stated with the actual numbers.",
                },
            },
            "required": ["title", "chart_type", "sql", "x_field", "y_fields", "insight"],
            "additionalProperties": False,
        },
    },
]
TOOL_DESC = {t["name"]: t["description"] for t in TOOLS}


def execute_tool(proj: Project, name: str, tool_input: dict) -> tuple:
    """Returns (content, is_error)."""
    t0 = time.monotonic()
    content, is_error = _execute_tool_inner(proj, name, tool_input)
    ms = int((time.monotonic() - t0) * 1000)
    status = "ERROR" if is_error else "ok"
    detail = _short(tool_input.get("sql") or tool_input.get("note")
                    or tool_input.get("id") or "")
    log.info(f"[{proj.id}] tool {name} [{status}, {ms}ms] {detail}"
             + (f" -> {_short(content, 100)}" if is_error or name != "run_sql_query" else ""))
    L = proj.lang
    if name == "verify_dashboard":
        proj.log_activity("info", T(L, "act_verify",
                                    status=T(L, "act_verify_err" if is_error else "act_verify_ok")))
    elif is_error and name == "run_sql_query":
        proj.log_activity("sql", T(L, "act_sql_retry"))
    elif is_error:
        proj.log_activity("error", T(L, "act_tool_error", name=name, detail=_short(content, 90)))
    elif name == "run_sql_query":
        purpose = (tool_input.get("purpose") or "").strip()
        proj.log_activity("sql", T(L, "act_sql_purpose", what=_short(purpose, 90)) if purpose
                          else T(L, "act_sql_look", sql=_short(tool_input.get('sql', ''), 80)))
    elif name == "record_data_context":
        proj.log_activity("note", T(L, "act_note", note=_short(tool_input.get('note', ''), 80)))
    elif name == "define_filter":
        proj.log_activity("filter", T(L, "act_filter", label=tool_input.get('label', '')))
    elif name == "define_view":
        proj.log_activity("info", T(L, "act_view", name=tool_input.get('name', ''),
                                    desc=_short(tool_input.get('description', ''), 60)))
    elif name == "drop_view":
        proj.log_activity("info", T(L, "act_view_drop", name=tool_input.get('name', '')))
    elif name == "create_chart":
        proj.log_activity("chart", T(L, "act_chart", title=_short(tool_input.get('title', ''), 60)))
    elif name == "update_chart":
        proj.log_activity("chart", T(L, "act_chart_upd", title=_short(tool_input.get('title', ''), 60)))
    elif name == "delete_chart":
        proj.log_activity("chart", T(L, "act_chart_del", id=tool_input.get('id')))
    elif name == "present_questions":
        proj.log_activity("info", T(L, "act_questions", n=len(tool_input.get('questions', []))))
    return content, is_error


def _execute_tool_inner(proj: Project, name: str, tool_input: dict) -> tuple:
    try:
        if getattr(proj, "chat_scope", "dashboard") == "app" and name not in APP_CHAT_TOOLS:
            return json.dumps({"error": "This conversation can only build the app. Use update_app or ask a workflow question."}), True
        if name == "record_data_context":
            proj.notes.append(tool_input["note"])
            proj.save_notes()
            return "Saved.", False

        if name == "define_view":
            vname, body = tool_input["name"], tool_input["sql"].strip().rstrip(";")
            if FORBIDDEN_SQL.search(body):
                return "Error: the view body must be a plain SELECT.", True
            if not db.has_data(proj.id):
                return "Error: the project has no data yet.", True
            try:
                db.create_view(proj.id, vname, pg_compat(body))
                invalidate(proj.id)
            except Exception as e:
                return f"Error: the view could not be created — {str(e).splitlines()[0]}", True
            df = run_readonly_sql(proj, f'SELECT * FROM "{vname}" LIMIT 3', 3)
            proj.meta.setdefault("views", {})[vname] = tool_input["description"]
            proj.save_meta()
            return (f"View '{vname}' created: columns {list(df.columns)}, "
                    f"sample ok."), False

        if name == "drop_view":
            vname = tool_input["name"]
            try:
                db.drop_view(proj.id, vname)
                invalidate(proj.id)
            except Exception as e:
                return f"Error: {str(e).splitlines()[0]}", True
            proj.meta.get("views", {}).pop(vname, None)
            proj.save_meta()
            return f"View '{vname}' dropped.", False

        if name == "verify_dashboard":
            report = verify_dashboard(proj)
            if report["ok"]:
                proj.verify_fails = 0
                return json.dumps(report, ensure_ascii=False), False
            # Repairing one chart often breaks the check on another; left alone
            # the agent plays whack-a-mole until the turn ceiling stops it.
            proj.verify_fails = getattr(proj, "verify_fails", 0) + 1
            if proj.verify_fails >= MAX_VERIFY_RETRIES:
                report["stop"] = (
                    f"You have now failed this check {proj.verify_fails} times in a row. "
                    "STOP editing charts and do NOT call verify_dashboard again. "
                    "Either delete the one chart that still fails, or finish your reply "
                    "by telling the user in plain language which chart could not be made "
                    "to work and what you would need to fix it.")
                log.error(f"[{proj.id}] verify: {proj.verify_fails} consecutive failures — "
                          f"telling the agent to stop; {report.get('errors')}")
                proj.log_activity("error", T(proj.lang, "act_verify_giveup"))
            return json.dumps(report, ensure_ascii=False), True

        if name == "present_questions":
            proj.new_questions = tool_input["questions"]
            return ("Questions presented to the user as an interactive form. Now "
                    "finish your reply with a short intro text — do NOT repeat the "
                    "questions in it."), False

        if name == "run_sql_query":
            df = run_readonly_sql(proj, apply_filters_to_sql(proj, tool_input["sql"], {}),
                                  MAX_PREVIEW_ROWS)
            return json.dumps({"row_count": len(df), "rows": frame_to_records(df)}), False

        if name == "update_app":
            try:
                spec = json.loads(tool_input["spec"])
            except json.JSONDecodeError as e:
                return f"The spec is not valid JSON: {e}", True
            try:
                validate_app_spec(spec)
            except ValueError as e:
                return str(e), True
            views = spec["views"]
            spec["generated_at"] = time.strftime("%Y-%m-%d %H:%M")
            proj.app = spec
            proj.save_app()
            proj.app_touched = True
            proj.log_activity("info", T(proj.lang, "act_app_updated",
                                        what=_short(tool_input.get("summary", ""), 80)))
            return json.dumps({"ok": True, "views": len(views)}), False

        if name == "define_filter":
            f = {k: tool_input[k] for k in ("id", "label", "type", "column", "options_sql", "options")}
            opts = resolve_filter_options(proj, f)
            if not opts:
                return (f"Error: filter '{f['id']}' resolves to no options — check "
                        "options_sql/options."), True
            proj.filters[:] = [x for x in proj.filters if x["id"] != f["id"]] + [f]
            proj.save_filters()
            return f"Filter '{f['id']}' defined with {len(opts)} options: {opts[:12]}", False

        if name == "delete_chart":
            before = len(proj.dashboard)
            proj.dashboard[:] = [c for c in proj.dashboard if c["id"] != tool_input["id"]]
            if len(proj.dashboard) == before:
                return f"Error: no chart with id {tool_input['id']}.", True
            proj.save_dash()
            return f"Chart #{tool_input['id']} deleted.", False

        if name == "update_chart":
            chart = next((c for c in proj.dashboard if c["id"] == tool_input["id"]), None)
            if chart is None:
                return (f"Error: no chart with id {tool_input['id']}. Existing ids: "
                        f"{[c['id'] for c in proj.dashboard]}"), True
            df = run_readonly_sql(proj, apply_filters_to_sql(proj, tool_input["sql"], {}),
                                  MAX_CHART_ROWS)
            missing = [f for f in [tool_input["x_field"], *tool_input["y_fields"]]
                       if f not in df.columns]
            if missing:
                return (f"Error: field(s) {missing} not in query result. "
                        f"Available columns: {list(df.columns)}"), True
            chart.update({k: tool_input[k] for k in
                          ("title", "chart_type", "sql", "x_field", "y_fields", "insight")})
            chart["rows"] = frame_to_records(df)
            proj.save_dash()
            return f"Chart #{chart['id']} updated ({len(df)} rows).", False

        if name == "create_chart":
            df = run_readonly_sql(proj, apply_filters_to_sql(proj, tool_input["sql"], {}),
                                  MAX_CHART_ROWS)
            missing = [f for f in [tool_input["x_field"], *tool_input["y_fields"]]
                       if f not in df.columns]
            if missing:
                return (f"Error: field(s) {missing} not in query result. "
                        f"Available columns: {list(df.columns)}"), True
            proj.chart_seq += 1
            chart = {
                "id": proj.chart_seq,
                "title": tool_input["title"],
                "chart_type": tool_input["chart_type"],
                "sql": tool_input["sql"],
                "x_field": tool_input["x_field"],
                "y_fields": tool_input["y_fields"],
                "insight": tool_input["insight"],
                "rows": frame_to_records(df),
            }
            proj.new_charts.append(chart)
            proj.dashboard.append(chart)
            proj.save_dash()
            return f"Chart #{proj.chart_seq} '{chart['title']}' created with {len(df)} rows.", False

        return f"Unknown tool: {name}", True
    except Exception as e:  # surface DB/SQL errors to the model so it can retry
        return f"Error: {e}", True


# ------------------------------------------------------------- system prompt

PROMPT_INTRO = """You are the analytics copilot inside a dashboard product for non-technical
sales and business users. The user's uploaded spreadsheets live in a PostgreSQL
database (one schema per project; you only see this project's tables). You answer questions and build dashboard charts for them."""
PROMPT_INTERVIEW = """The interview (how a new dataset becomes a dashboard):

Step 1 — understand the data. When files are newly uploaded, first investigate
them yourself with run_sql_query: distinct values of categorical/code columns,
date ranges, row counts, obvious keys between tables. Then tell the user in
2-4 plain sentences what you believe the data represents. If (and only if)
something you genuinely could not figure out matters for analysis — cryptic
codes or SKUs, ambiguous columns, units/currency, how tables relate — ask
about it. Never ask about things that are obvious or already in memory.

Step 2 — understand what the user wants: what decisions or meetings the
dashboard is for; which metrics matter most; what comparisons they care about
(over time, by person, by product, vs target); any specific views they
imagine.

HOW to ask (steps 1 and 2, and any later question): ALWAYS use the
present_questions tool — never write questions as plain text. Combine the
data questions and the goal questions into ONE present_questions call (max 4
questions total). Give each question 2-6 short suggested options based on
what you actually see in THEIR data (your best guesses first — e.g. for
currency: "Euro (€)", "Lev (BGN)"); the UI automatically adds a free-text
"other answer" option. Questions and options are written in the UI language
(see the Output language rule). Set multi=true whenever several answers can
apply at once (e.g. "which comparisons matter to you", "which metrics to
track") — the
user then picks multiple; keep multi=false for exclusive choices (currency,
fiscal year). Your text reply should be only the short summary of
what you understood — the form carries the questions.

Step 3 — build. Once the user answers, save every durable fact AND every
stated preference/goal with record_data_context (one short note per fact, in
their terms), then build without asking for permission:
1. First build the semantic layer with define_view — clean v_* views over the
   raw tables (see the two-layer rule below).
2. Then define the dashboard filters with define_filter over the views — the
   dimensions the user will want to slice by (time period, person,
   product/group, channel, chain...), plus a 'single' metric toggle when both
   value and volume exist.
3. Then create the charts with create_chart querying ONLY the views, wiring
   every chart to the relevant filters via {{filter_id}} tokens so the whole
   dashboard responds to filter changes.
A good first dashboard follows the Dashboard UX standard below: the summary
table on top, 4-6 charts, 3-6 canonical filters. After building, offer 1-2
ideas for what could be added next.

The user's stated goal is a floor, not a ceiling: even when they told you
upfront what they want, still investigate the data yourself — and when you
discover something valuable beyond the brief (a trend, anomaly, risk or
opportunity), say it with the numbers and OFFER to add the view for it.
Propose, don't add unasked.

At any later point: if the user just asks a question or requests a chart,
answer/build directly — the interview is only for new or unclear situations.
Never ask the same thing twice; check memory first.

Memory is the project's knowledge base: record with record_data_context not
only the user's answers, but also YOUR OWN important discoveries from
investigating the data (how tables join, name mismatches between sources,
date quirks, canonical mappings, computed baselines worth reusing). This is
what lets any future session continue without re-analysis."""
PROMPT_RULES = f"""Data architecture — the two-layer rule (apply ALWAYS):
- Raw uploaded tables are a LANDING ZONE only. Before building any dashboard,
  create semantic VIEWS with define_view (names v_*): they unify, unpivot and
  rename the raw data into clean business columns in the UI language
  (e.g. v_sales: month, rep, product, channel, revenue, units — in __LANGUAGE__).
- ALL charts and filters query ONLY views, never raw tables. That is what
  keeps the dashboard alive when new files arrive.
- When new files are uploaded, FIRST update the affected view definitions so
  they include the new data (same view name, same columns), then run
  verify_dashboard — existing charts must keep working without edits.
- If a raw table is replaced or removed, fix the views, not the charts.
- Keep the semantic layer small: 1-4 views with clear one-line descriptions.

Dashboard UX standard — apply in EVERY project, without being asked:
- Composition: the FIRST chart is always a 'table' summary ("Summary:
  observations and recommendations", in __LANGUAGE__) whose rows carry theme / the actual number /
  observation / concrete recommendation, built from filter-aware SQL so it
  recalculates with the filters. Then 4-8 charts that together cover: trend
  over time, ranking of people/entities, structure (groups/channels/share),
  execution vs target when targets exist, and a detail table at the end.
- Filters: ONE canonical, minimal set — NEVER two filters for the same
  dimension. If a similar filter already exists, redefine it under the SAME id
  instead of creating a parallel one; a replaced or unused filter must not be
  left behind. Typical set: time period, person, product/group,
  channel/segment, plus a 'single' metric toggle when both value and volume
  exist.
- Labels: business language, in the UI language (__LANGUAGE__), everywhere — chart
  titles, SQL result aliases (they become axis/table labels), filter labels.
  Never expose raw column names. Months in chronological/fiscal order, never
  alphabetical.
- Label readability is non-negotiable: rankings and any category axis with
  long names (people, products) belong on BAR charts — the renderer flips
  them horizontal automatically so names never collide. Keep category counts
  chart-friendly: top-N (10-15) with the rest folded into 'Other' instead of
  50 unreadable slivers; short category values in SQL (e.g. 'Oct' not
  '2024-10-01 00:00:00').
- Insights: every chart's insight states the actual numbers and what to do
  about them — it is the sentence the user will paste into their report.
- Work incrementally: build and rewire in small batches (a few charts per
  response), keeping the dashboard consistent after every step — never a
  single giant rebuild that can be cut off half-way.
- VERIFY BEFORE DONE (mandatory): in every turn where you created or changed
  charts or filters, your LAST tool call must be verify_dashboard. If it
  reports errors — fix them (update_chart / define_filter / delete_chart) and
  run it again, until ok:true. Never tell the user the dashboard is ready
  without a clean verification; mention in one short line that the check
  passed.

Dynamic dashboards (filters):
- The dashboard is live: whenever the user changes a filter, every chart's SQL
  re-runs against the database with the new selections.
- 'multi' filters: the token {{{{filter_id}}}} expands to a boolean condition
  ("column" IN (...)), or TRUE when nothing is selected — so place it inside
  WHERE, e.g. WHERE {{{{months}}}} AND {{{{reps}}}}. The filter's declared
  column must exist under that exact name in the tables/subquery the chart
  queries (alias it if needed).
- 'single' filters: the token is replaced by the selected option text — use
  for metric toggles, e.g. SUM({{{{metric}}}}) with options ["revenue",
  "units_sold"]. Options must be valid SQL fragments.
- run_sql_query also accepts these tokens (expanded with default selections),
  so you can test a templated query before charting it.
- EVERY chart must be wired via {{tokens}} to ALL global filters that
  logically apply to its data (time period, person, product, channel, metric
  toggle...). A chart that ignores the dashboard filters is a bug.
- When you define a NEW filter, immediately wire it into every existing chart
  it should affect using update_chart. Use update_chart to fix charts and
  delete_chart to remove obsolete ones.

Rules:
- Write PostgreSQL SQL. Quote identifiers with double quotes. Aggregate in SQL —
  the chart receives at most {MAX_CHART_ROWS} rows, so group and order the data
  so each x value appears once.
- PostgreSQL specifics: every non-aggregated SELECT column must appear in GROUP BY
  (positional "GROUP BY 1, 2" is fine); cast explicitly ("col"::numeric,
  "col"::text, NULLIF(x, '')::double precision for text numbers); integer / integer
  truncates — cast to numeric first; ROUND(x::numeric, 1); text concatenation with
  ||; date_trunc('month', d), EXTRACT(year FROM d), to_char(d, 'YYYY-MM');
  string_agg(x, ', ' ORDER BY x); percentile_cont(0.5) WITHIN GROUP (ORDER BY x);
  mode() WITHIN GROUP (ORDER BY x); FILTER (WHERE …) on aggregates; no TRY_CAST
  (use CASE WHEN x ~ '^-?[0-9.]+$' THEN x::numeric END); no list_/struct functions;
  LIMIT/OFFSET as usual. One statement per query, SELECT/WITH only.
- Use run_sql_query first when you are unsure about values or need to explore;
  use create_chart to put results on the dashboard.
- Pick the chart form by the data's job: change over time -> line or area;
  comparing categories -> bar (sorted by value unless the x axis is ordered,
  e.g. months); share of a small whole (<= 6 slices) -> pie, otherwise bar;
  relationship between two measures -> scatter; detailed records -> table.
- Never mix two different value scales in one chart; create two charts instead.
- At most {MAX_SERIES} series per chart; fold small categories into 'Other'.
- The user is not technical: never show SQL or column jargon in your replies.
  Speak in plain business language, brief and concrete, and mention the actual
  numbers you found.
- Output language: the UI language is __LANGUAGE__. EVERYTHING you produce
  for the user — chat replies, interview questions and options, chart titles,
  insights, filter labels, view descriptions, SQL result aliases, notes and
  presentation content — must be in __LANGUAGE__, regardless of the language
  of the source data or of the user's message, unless the user explicitly
  asks for another language. Data VALUES stay exactly as they are in the data.
- If the request is ambiguous, make a sensible choice and state it in one line
  rather than asking questions.
- If there is no uploaded data yet, tell the user to upload a file first."""


def prompt_rules(lang: str) -> str:
    """PROMPT_RULES with the UI language name filled in."""
    return PROMPT_RULES.replace("__LANGUAGE__", LANG_NAMES.get(lang, LANG_NAMES["bg"]))


def build_system_prompt(proj: Project) -> str:
    schema = json.dumps(describe_schema(proj), default=str)
    notes = "\n".join(f"- {n}" for n in proj.notes) or "(nothing recorded yet)"
    if getattr(proj, "chat_scope", "dashboard") == "app":
        return APP_CHAT_RULES + "\nSchema: " + schema + "\nKnown facts: " + notes + "\n" + prompt_rules(proj.lang)
    return f"""{PROMPT_INTRO}

Current database schema (tables, column types, sample rows):
{schema}

What you have learned about this data from the user (permanent memory):
{notes}

{PROMPT_INTERVIEW}

{prompt_rules(proj.lang)}"""
# The SDK MCP tool functions are module-level, so the project a turn operates
# on is bound here. AGENT_LOCK serializes all agent turns process-wide, which
# both prevents interleaving on one SDK session and keeps this binding safe.
CURRENT_PROJECT: Project | None = None
AGENT_LOCK: asyncio.Lock | None = None


def _mcp_result(content: str, is_error: bool) -> dict:
    prefix = "Error: " if is_error and not content.startswith("Error") else ""
    return {"content": [{"type": "text", "text": prefix + content}]}


@tool("run_sql_query", TOOL_DESC["run_sql_query"], {"sql": str, "purpose": str})
async def sdk_run_sql(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "run_sql_query", args))


@tool("record_data_context", TOOL_DESC["record_data_context"], {"note": str})
async def sdk_record_note(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "record_data_context", args))


@tool("define_filter", TOOL_DESC["define_filter"], {
    "id": str, "label": str, "type": str,
    "column": str, "options_sql": str, "options": list,
})


async def sdk_define_filter(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "define_filter", args))


@tool("create_chart", TOOL_DESC["create_chart"], {
    "title": str, "chart_type": str, "sql": str,
    "x_field": str, "y_fields": list, "insight": str,
})


async def sdk_create_chart(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "create_chart", args))


@tool("update_chart", TOOL_DESC["update_chart"], {
    "id": int, "title": str, "chart_type": str, "sql": str,
    "x_field": str, "y_fields": list, "insight": str,
})


async def sdk_update_chart(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "update_chart", args))


@tool("delete_chart", TOOL_DESC["delete_chart"], {"id": int})
async def sdk_delete_chart(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "delete_chart", args))


@tool("update_app", TOOL_DESC["update_app"], {"spec": str, "summary": str})
async def sdk_update_app(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "update_app", args))


@tool("define_view", TOOL_DESC["define_view"], {"name": str, "sql": str, "description": str})
async def sdk_define_view(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "define_view", args))


@tool("drop_view", TOOL_DESC["drop_view"], {"name": str})
async def sdk_drop_view(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "drop_view", args))


@tool("verify_dashboard", TOOL_DESC["verify_dashboard"], {})
async def sdk_verify_dashboard(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "verify_dashboard", args or {}))


@tool("present_questions", TOOL_DESC["present_questions"], {"questions": list})
async def sdk_present_questions(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "present_questions", args))
ANALYTICS_SERVER = create_sdk_mcp_server(
    name="analytics",
    tools=[sdk_run_sql, sdk_record_note, sdk_define_filter, sdk_create_chart,
           sdk_update_chart, sdk_delete_chart, sdk_define_view, sdk_drop_view,
           sdk_update_app, sdk_verify_dashboard, sdk_present_questions],
)


def sub_options(proj: Project) -> ClaudeAgentOptions:
    # Static rules only — the live schema and learned facts are injected at the
    # top of every user message, since a persistent session's system prompt
    # cannot change after connect.
    rules = f"""{PROMPT_INTRO}

The current database schema and everything you have learned about the data are
provided in a <data_context> block at the top of every user message — always
use the latest one. Use ONLY the analytics tools (run_sql_query,
record_data_context, define_view, drop_view, define_filter, create_chart,
update_chart, delete_chart, update_app, verify_dashboard, present_questions).
When the user asks to change their app (the App tab) — add a field, drop a view,
add a list or a metric — use update_app with the COMPLETE new spec, starting
from <current_app> in the context. Apply EVERY part of the request in that one
call: additions AND removals AND reorderings. Never silently skip a part; if
something cannot be done, say so in your reply.
chart_type must be one of: bar, line, area, pie, scatter, table; y_fields is
a list of column names (max 8). define_filter's type is 'multi' or 'single';
pass unused fields as '' / []. present_questions takes
{{"questions": [{{"question": str, "options": [str, ...]}}]}}.

{PROMPT_INTERVIEW}

{prompt_rules(proj.lang)}"""
    return ClaudeAgentOptions(
        system_prompt=(APP_CHAT_RULES + "\n" + prompt_rules(proj.lang)) if getattr(proj, "chat_scope", "dashboard") == "app" else rules,
        mcp_servers={"analytics": ANALYTICS_SERVER},
        allowed_tools=(["mcp__analytics__" + name for name in sorted(APP_CHAT_TOOLS)] if getattr(proj, "chat_scope", "dashboard") == "app" else [
            "mcp__analytics__run_sql_query",
            "mcp__analytics__record_data_context",
            "mcp__analytics__define_filter",
            "mcp__analytics__update_app",
            "mcp__analytics__create_chart",
            "mcp__analytics__update_chart",
            "mcp__analytics__delete_chart",
            "mcp__analytics__define_view",
            "mcp__analytics__drop_view",
            "mcp__analytics__verify_dashboard",
            "mcp__analytics__present_questions",
            "Read",
        ]),
        disallowed_tools=[
            "Bash", "Write", "Edit", "Glob", "Grep", "WebSearch",
            "WebFetch", "NotebookEdit", "Task", "TodoWrite",
        ],
        permission_mode="bypassPermissions",
        setting_sources=[],
        max_turns=MAX_TURNS,
        cwd=str(proj.dir),
    )


def _record_usage(proj: Project, message) -> None:
    """API-equivalent cost accounting: tokens (incl. cache) + the SDK's own
    cost estimate, accumulated on the current job row."""
    try:
        u = getattr(message, "usage", None) or {}
        if not isinstance(u, dict):
            u = getattr(u, "__dict__", {}) or {}
        fresh = u.get("input_tokens") or 0
        cw = u.get("cache_creation_input_tokens") or 0
        cr = u.get("cache_read_input_tokens") or 0
        tout = u.get("output_tokens") or 0
        cost = getattr(message, "total_cost_usd", None) or 0
        log.info(f"[{proj.id}] usage: in={fresh}+cache_w{cw}+cache_r{cr}, out={tout}, api_cost=${cost:.4f}")
        if proj.job_id:
            from db import pool
            with pool().connection() as con:
                con.execute(
                    "UPDATE public.jobs SET tokens_in = COALESCE(tokens_in,0) + %s, "
                    "tokens_out = COALESCE(tokens_out,0) + %s, "
                    "cost_usd = COALESCE(cost_usd,0) + %s WHERE id = %s",
                    (fresh + cw + cr, tout, cost, proj.job_id))
    except Exception as e:
        log.info(f"[{proj.id}] usage record failed — {e}")


async def run_agent_subscription(proj: Project, user_content: str, images: list | None = None):
    if not SDK_AVAILABLE:
        log.error("agent: subscription mode selected but the Claude Agent SDK is "
                  "not installed here — set AI_BACKEND=api with ANTHROPIC_API_KEY")
        raise RuntimeError(T(proj.lang, "err_ai_offline"))
    global CURRENT_PROJECT, AGENT_LOCK
    if AGENT_LOCK is None:
        AGENT_LOCK = asyncio.Lock()

    async with AGENT_LOCK:
        CURRENT_PROJECT = proj
        proj.new_charts.clear()
        proj.new_questions = []
        recap = ""
        if proj.sub_client is not None and proj.sub_lang != proj.lang:
            # the system prompt (incl. output language) is fixed at connect time
            log.info(f"[{proj.id}] agent[subscription]: UI language changed "
                     f"{proj.sub_lang} -> {proj.lang}, reconnecting SDK session")
            try:
                await proj.sub_client.disconnect()
            except Exception:
                pass
            proj.sub_client = None
        if proj.sub_client is None:
            proj.sub_client = ClaudeSDKClient(options=sub_options(proj))
            await proj.sub_client.connect()
            proj.sub_lang = proj.lang
            recap = conversation_recap(proj)
            log.info(f"[{proj.id}] agent[subscription]: new SDK session connected"
                     + (" (with conversation recap)" if recap else ""))
            proj.log_activity("info", T(proj.lang, "act_new_session")
                              + (T(proj.lang, "act_session_recap") if recap else ""))

        ctx: dict = {"schema": describe_schema(proj), "known_facts": proj.notes}
        if proj.app and proj.app.get("views"):
            ctx["current_app"] = proj.app
        bf = brand_files(proj)
        if bf:
            ctx["brand"] = {"files": bf, "brandbook_excerpt": brand_excerpt(proj, 1500)}
        context = json.dumps(ctx, default=str, ensure_ascii=False)
        shots = _save_shots(proj, images)
        if shots:
            user_content += ("\n\n<screenshots>\nThe user attached screenshots of what they mean. "
                             "Read them with the Read tool before answering:\n"
                             + "\n".join(str(p) for p in shots) + "\n</screenshots>")
        try:
            async with asyncio.timeout(SUB_TIMEOUT_S):
                await proj.sub_client.query(
                    f"{recap}<data_context>\n{context}\n</data_context>\n\n{user_content}"
                )
                reply = ""
                async for message in proj.sub_client.receive_response():
                    if proj.job_id and jobs.is_cancelled(proj.job_id):
                        log.info(f"[{proj.id}] agent: cancelled by user — stopping")
                        raise CancelledByUser()
                    if isinstance(message, AssistantMessage):
                        text = "".join(b.text for b in message.content if isinstance(b, TextBlock))
                        if text.strip():
                            reply = text  # keep the last non-empty assistant text
                    elif isinstance(message, ResultMessage):
                        _record_usage(proj, message)
                        if message.is_error and not reply:
                            raise HTTPException(502, T(proj.lang, "err_ai_sub_failed",
                                                       detail=message.result))
                        break
        except (TimeoutError, asyncio.TimeoutError):
            # Session state unknown — drop it so the next turn starts fresh
            try:
                await proj.sub_client.disconnect()
            except Exception:
                pass
            proj.sub_client = None
            raise HTTPException(504, T(proj.lang, "err_ai_timeout"))
        return {"reply": reply, "charts": list(proj.new_charts),
                "questions": list(proj.new_questions),
                "tables": describe_schema(proj), "notes": proj.notes}


def run_agent_api(proj: Project, user_content: str, images: list | None = None):
    import anthropic  # lazy: heavy import, only needed in API mode
    """Production path: Anthropic API with a manual tool loop."""
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        # Deployment is misconfigured; the SDK's own error is unreadable and
        # would be shown verbatim to the user by jobs.fail().
        log.error("agent: AI_BACKEND=api but ANTHROPIC_API_KEY is not set — "
                  "no AI work can run on this deployment")
        raise RuntimeError(T(proj.lang, "err_ai_offline"))
    if not proj.messages:  # fresh process: continue from the stored transcript
        user_content = conversation_recap(proj) + user_content
    if images:
        blocks: list = []
        for src in images[:3]:
            head, _, b64 = str(src).partition(",")
            media = head.split(";")[0].replace("data:", "") or "image/png"
            if b64:
                blocks.append({"type": "image",
                               "source": {"type": "base64", "media_type": media, "data": b64}})
        blocks.append({"type": "text", "text": user_content})
        proj.messages.append({"role": "user", "content": blocks})
    else:
        proj.messages.append({"role": "user", "content": user_content})
    proj.new_charts.clear()
    proj.new_questions = []

    turns = 0
    while True:
        if proj.job_id and jobs.is_cancelled(proj.job_id):
            log.info(f"[{proj.id}] agent: cancelled by user — stopping")
            raise CancelledByUser()
        turns += 1
        if turns > MAX_TURNS:
            # The subscription path has always had this ceiling; without it here
            # a fix-check-fix loop runs until the money runs out.
            log.error(f"[{proj.id}] agent: hit the {MAX_TURNS}-turn ceiling — stopping")
            proj.log_activity("error", T(proj.lang, "act_turn_limit"))
            break
        try:
            response = client.beta.messages.create(
                model=getattr(proj, "ai_model_id", None) or MODEL,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=[{
                    "type": "text",
                    "text": build_system_prompt(proj),
                    "cache_control": {"type": "ephemeral"},
                }],
                tools=[t for t in TOOLS if getattr(proj, "chat_scope", "dashboard") != "app" or t["name"] in APP_CHAT_TOOLS],
                messages=proj.messages,
            )
        except anthropic.APIStatusError as e:
            if proj.messages and proj.messages[-1]["role"] == "user":
                proj.messages.pop()
            raise HTTPException(502, T(proj.lang, "err_ai_failed", detail=e.message))
        except anthropic.APIConnectionError:
            raise HTTPException(502, T(proj.lang, "err_ai_unreachable"))

        # Keep full content blocks (incl. thinking) so multi-step turns replay correctly
        proj.messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "refusal":
            reply = T(proj.lang, "err_ai_refusal")
            return {"reply": reply, "charts": list(proj.new_charts), "questions": [],
                    "tables": describe_schema(proj), "notes": proj.notes}

        if response.stop_reason == "pause_turn":
            continue

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    content, is_error = execute_tool(proj, block.name, block.input)
                    result = {"type": "tool_result", "tool_use_id": block.id, "content": content}
                    if is_error:
                        result["is_error"] = True
                    tool_results.append(result)
            proj.messages.append({"role": "user", "content": tool_results})
            continue

        reply = "".join(b.text for b in response.content if b.type == "text")
        return {"reply": reply, "charts": list(proj.new_charts),
                "questions": list(proj.new_questions),
                "tables": describe_schema(proj), "notes": proj.notes}


def _save_shots(proj: Project, images: list | None) -> list:
    """Screenshots the user pasted, written next to the project so the SDK
    session can open them with its Read tool."""
    import base64

    if not images:
        return []
    out = []
    shots_dir = proj.dir / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    for i, src in enumerate(list(images)[:3]):
        head, _, b64 = str(src).partition(",")
        if not b64:
            continue
        ext = "png" if "png" in head else ("jpg" if "jpeg" in head or "jpg" in head else "webp")
        p = shots_dir / f"shot-{int(time.time())}-{i}.{ext}"
        try:
            p.write_bytes(base64.b64decode(b64))
            out.append(p)
        except Exception as e:
            log.info(f"[{proj.id}] screenshot {i} skipped — {e}")
    if out:
        log.info(f"[{proj.id}] chat: {len(out)} screenshot(s) attached")
    return out


async def dispatch_agent(proj: Project, user_content: str, images: list | None = None):
    if getattr(proj, "chat_scope", "dashboard") == "app":
        user_content = APP_CHAT_RULES + "\n<current_app>" + json.dumps(proj.app, ensure_ascii=False) + "</current_app>\nUser request: " + user_content
    t0 = time.monotonic()
    log.info(f"[{proj.id}] agent[{AI_BACKEND}]: turn start — {_short(user_content, 120)}")
    proj.log_activity("info", T(proj.lang, "act_thinking"))
    try:
        result = (await run_agent_subscription(proj, user_content, images)
                  if AI_BACKEND == "subscription"
                  else await run_in_threadpool(run_agent_api, proj, user_content, images))
    except Exception as e:
        log.info(f"[{proj.id}] agent[{AI_BACKEND}]: turn FAILED after "
                 f"{time.monotonic() - t0:.1f}s — {_short(e, 160)}")
        raise
    log.info(f"[{proj.id}] agent[{AI_BACKEND}]: turn done in {time.monotonic() - t0:.1f}s — "
             f"{len(result['charts'])} new chart(s), {len(proj.filters)} filter(s), "
             f"{len(proj.notes)} note(s) in memory; reply: {_short(result['reply'], 110)}")
    proj.add_chat("ai", result["reply"], questions=result.get("questions") or None)
    write_progress(proj)
    return result
TRANSLATE_PROMPT = """[Task: translate the user-facing texts of this dashboard into {language}.
These are chart titles, insights, filter labels, field names, category values and
analyst notes from the current project — use the project context you know for
correct business terminology. Rules: keep numbers, units, currency codes, product
and company names, SKUs and abbreviations exactly as they are; keep the tone and
length (a field name stays a short field name); translate category values
consistently (the same source text always gets the same translation); never add
commentary; do not run tools. Return ONLY valid JSON: an object mapping each key
to its translation, with exactly the same keys as the input.

Input:
{payload}]"""


async def run_translate(proj: Project):
    lang = proj.lang
    pid = proj.id
    src = content_lang(proj)
    if lang == src:
        return {"translated": 0, "content_lang": src}
    tr = _load_i18n(proj, lang)
    items = translatable_items(proj, lang)
    missing = {k: v for k, v in items.items() if k not in tr}
    if not missing:
        return {"translated": 0, "content_lang": src}
    log.info(f"[{pid}] i18n: translating {len(missing)} texts -> {lang}")
    proj.log_activity("info", T(lang, "act_translating", n=len(missing)))
    done = 0
    keys = list(missing)
    # chunks keep each model answer comfortably parseable
    for i in range(0, len(keys), 80):
        chunk = {k: missing[k] for k in keys[i:i + 80]}
        prompt = TRANSLATE_PROMPT.format(language=LANG_NAMES[lang],
                                         payload=json.dumps(chunk, ensure_ascii=False))
        result = (await run_agent_subscription(proj, prompt)
                  if AI_BACKEND == "subscription"
                  else await run_in_threadpool(run_agent_api, proj, prompt))
        raw = result["reply"].strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            log.info(f"[{pid}] i18n: chunk {i // 80 + 1} — no JSON in reply")
            continue
        try:
            got = json.loads(m.group(0))
        except Exception:
            log.info(f"[{pid}] i18n: chunk {i // 80 + 1} — invalid JSON")
            continue
        for k, v in got.items():
            if k in chunk and isinstance(v, str) and v.strip():
                tr[k] = v.strip()
                done += 1
        _save_i18n(proj, lang, tr)
    # drop entries whose source text no longer exists (keeps the file small)
    tr = {k: v for k, v in tr.items() if k in items}
    _save_i18n(proj, lang, tr)
    log.info(f"[{pid}] i18n: done — {done}/{len(missing)} translated")
    proj.log_activity("info", T(lang, "act_translated", n=done))
    return {"translated": done, "missing": len(missing) - done, "content_lang": src,
            "reply": T(lang, "act_translated", n=done)}


async def run_review(proj: Project, tables: list, context: str = "", goal: str = ""):
    lang = proj.lang
    proj.add_chat("event", T(lang, "chat_files_loaded", tables=', '.join(tables)))
    upfront = ""
    if context.strip() or goal.strip():
        parts = []
        if context.strip():
            parts.append(T(lang, "chat_context", text=context.strip()))
        if goal.strip():
            parts.append(T(lang, "chat_goal", text=goal.strip()))
        user_text = "\n".join(parts)
        proj.add_chat("user", user_text)
        upfront = (f"\nThe user provided this upfront — treat it as answered "
                   f"interview ground truth, record every durable fact and goal "
                   f"with record_data_context, and do NOT re-ask about any of it:\n"
                   f"{user_text}\n")
    return await dispatch_agent(
        proj,
        f"[The user just uploaded file(s) loaded as: {', '.join(tables)}.{upfront}"
        "Follow your interview-mode instructions: investigate the new data, "
        "say briefly what you understood, and ask only the clarifying "
        "questions you really need (skip anything already answered above). "
        "Address the user directly.]"
    )


# ------------------------------------------------------- presentation deck

DECK_PROMPT = """[Task: write the content of a presentation about the current
dashboard, the way an experienced business analyst would write it for a live
audience.

Language: write ALL titles, headlines, narratives, agenda items, section
headings and takeaways in __LANGUAGE__ (the UI language). Keep data values as
they appear in the data.

Style (important):
- Every slide title is the MESSAGE with the number, not a description of the
  chart ("Growth comes entirely from the wholesale channel: 50% share vs 27% a
  year ago", not "Chart of channels").
- Under every title: 2-3 short human sentences that tell what is visible, why
  it happened and what follows from it. Write like a person: no long dashes, no
  bureaucratic language, no bullet lists inside the narrative.
- Group the slides into 2-4 logical sections with clear headings that together
  tell a story (big picture -> details -> people/products -> conclusions).
- Every dashboard chart is used EXACTLY once.
- Final slide "Key takeaways and recommendations": 3-5 concrete recommendations
  with numbers.

Use the project knowledge and the numbers from the charts. If you need a
specific figure, verify it with run_sql_query.

Finally, also write a BRIEF for the design tool (Gamma) that will lay out the
slides. Derive it from the project knowledge (who the client is, what the goal
of the analysis is, who it is for), from the brand book (if present — the tone
of the brand) and from the charts we have:
- "audience": who the presentation is for (short, concrete).
- "tone": how it should sound (2-5 words).
- "emphasis": 2-4 things that must stand out (with numbers).
- "instructions": the brief itself IN ENGLISH (always English, whatever the UI
  language), 3-6 sentences, for Gamma: audience, tone, what to emphasise, how
  to order (e.g. summary first, next steps last), never change the numbers and
  keep the charts large and unmodified.
  Say WHAT matters and in WHAT ORDER — never how it should be typeset. Never ask
  for big, large, huge, bold, oversized or "visual" numbers or text: the renderer
  sizes type to fill the card, so asking for large figures produces slides with
  three enormous words on them. Emphasis is placement and order, not type size.
- "text_mode": "preserve" if your narratives are complete enough, "generate" if
  you want Gamma to expand them, "condense" if they are long.
- "image_source": "noImages" for a strict report (only our charts),
  "themeAccent" for a more visual presentation for a broad audience.
- "num_cards": recommended number of slides (sections + slides + cover + takeaways).

Return ONLY valid JSON (no markdown, no comments) in this format:
{"title": "...", "subtitle": "...",
 "agenda": ["...", "..."],
 "sections": [{"heading": "...",
               "slides": [{"chart_id": 1, "headline": "...", "narrative": "..."}]}],
 "takeaways": [{"title": "...", "text": "..."}],
 "gamma": {"audience": "...", "tone": "...", "emphasis": ["...", "..."],
           "instructions": "...", "text_mode": "preserve", "image_source": "noImages",
           "num_cards": 10}}

Brand book (excerpt): __BRAND__

Dashboard charts:
__CHARTS__]"""


async def run_deck(proj: Project):
    lang = proj.lang
    pid = proj.id
    charts_brief = [{"id": c["id"], "title": c["title"], "type": c["chart_type"],
                     "insight": c["insight"], "sample_rows": c["rows"][:3]}
                    for c in proj.dashboard]
    t0 = time.monotonic()
    log.info(f"[{pid}] deck: writing presentation content…")
    proj.log_activity("info", T(lang, "act_deck_writing"))
    prompt = (DECK_PROMPT
              .replace("__LANGUAGE__", LANG_NAMES[lang])
              .replace("__BRAND__", brand_excerpt(proj, 1500) or T(lang, "deck_no_brand"))
              .replace("__CHARTS__", json.dumps(charts_brief, ensure_ascii=False, default=str)))
    result = (await run_agent_subscription(proj, prompt)
              if AI_BACKEND == "subscription"
              else await run_in_threadpool(run_agent_api, proj, prompt))
    raw = result["reply"].strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise RuntimeError(T(lang, "err_deck_invalid"))
    try:
        spec = json.loads(m.group(0))
    except Exception:
        raise RuntimeError(T(lang, "err_deck_json"))
    log.info(f"[{pid}] deck: done in {time.monotonic() - t0:.1f}s — "
             f"{sum(len(s.get('slides', [])) for s in spec.get('sections', []))} слайда, "
             f"{len(spec.get('sections', []))} секции")
    g = spec.get("gamma") or {}
    if g.get("audience"):
        log.info(f"[{pid}] deck: brief — аудитория: {_short(g.get('audience'), 80)} | тон: {_short(g.get('tone'), 60)}")
    proj.add_chat("ai", T(lang, "chat_deck_ready"))
    return {"spec": spec}


# ------------------------------------------------------------------ app builder

APP_PROMPT = SCENARIO_GUIDANCE + CALCULATOR_GUIDANCE + """You turn a spreadsheet-backed project into a small internal APP.

The user's data already lives in Postgres tables (schema below). Instead of a
dashboard, design the day-to-day WORKING SURFACE that replaces the spreadsheet:
where they enter new records, watch the current state and spot problems.

Return ONE json object, no prose, no markdown fences:

{
  "title": "<app name in __LANGUAGE__>",
  "subtitle": "<one line: what this app is for>",
  "views": [
    {"type": "kpi", "title": "...", "items": [
        {"label": "...", "sql": "SELECT ... single value ...", "unit": "лв|бр|%|"}]},
    {"type": "entry", "title": "...",
     "table": "<single table>",            // use ONE of table / tables
     "tables": [{"table": "<table>", "label": "<site name in __LANGUAGE__>"}],
     "hint": "...", "fields": [
        {"column": "<real column>", "label": "<human label>",
         "type": "text|number|date|select", "required": true,
         "options_sql": "SELECT DISTINCT col FROM t ORDER BY 1"   // select only
        }]},
    {"type": "chart", "title": "...", "hint": "...", "sql": "SELECT ...",
     "chart_type": "line", "x_field": "month", "y_fields": ["revenue"]},
    {"type": "table", "title": "...", "sql": "SELECT ... ORDER BY ... LIMIT 50",
     "hint": "...", "editable_table": "<table>"   // omit if read-only
    }
  ]
}

Any view may also carry layout hints: "collapsible": true (fold-out panel),
"collapsed": true (starts folded — good for entry forms that are not needed
every minute) and "width": "half" | "full".

Rules:
- Design a coherent workspace around daily decisions, with a concise purpose in the subtitle.
- The UI includes section navigation, table search/sort and a natural-language edit composer.
- Charts support bar, line, area and pie; x_field and y_fields must match query output columns.
  Use a chart when trends or comparisons help the decision. Never invent data or projections.
- Put the primary user workflow first and set start_view to its zero-based index.
- Use 1 to 4 purposeful views. Entry forms, KPI rows and report tables are OPTIONAL.
  For planning, build an interactive scenario with business levers, live results,
  comparison and named scenarios. For record management, build usable entry/edit
  forms. Every section must serve a concrete action or decision.
- CRITICAL — many tables of the same shape (one sheet per site/store/month) are
  ONE entry view with the "tables" list: every table becomes a picker option
  with its human label, and the fields are shared. NEVER build the app around a
  single site while the rest of the business is left out, and never emit one
  entry view per table.
- SQL must be plain read-only SELECT for Postgres, referencing the real tables
  and columns from the schema, quoted with double quotes when non-ASCII.
- KPI sql returns exactly one row, one column.
- "entry" fields: only columns a human would actually type; skip computed ones.
- For changing existing records use entry views with mode="edit"; the user searches, selects, reviews and saves one record. Default mode="insert" adds new records. Never describe an insert form as an update form.
- Labels and titles in __LANGUAGE__, business language, no technical jargon.
- Think about what this business needs daily — not what is easy to query.

<schema>__SCHEMA__</schema>
<known_facts>__FACTS__</known_facts>
"""


def _compact_schema(proj: Project) -> list:
    """Tables sharing a column signature are described once — a 47-sheet
    workbook otherwise burns the whole context on repetition."""
    schema = describe_schema(proj)
    groups: dict = {}
    for t in schema:
        key = tuple(c["name"] for c in t.get("columns", []))
        groups.setdefault(key, []).append(t)
    out = []
    for _key, tabs in groups.items():
        head = dict(tabs[0])
        if len(tabs) > 1:
            head["same_shape_tables"] = [x["table"] for x in tabs]
            head["note"] = (f"{len(tabs)} tables share this exact structure — one per site. "
                            "Build ONE entry view listing them all in \"tables\".")
        out.append(head)
    log.info(f"[{proj.id}] app: schema {len(schema)} tables -> {len(out)} shape group(s)")
    return out


async def run_app(proj: Project, brief: str = ""):
    """Design the project's mini-app from its data (one AI turn, no tools)."""
    lang = proj.lang
    pid = proj.id
    t0 = time.monotonic()
    log.info(f"[{pid}] app: designing…")
    proj.log_activity("info", T(lang, "act_app_designing"))
    compact = _compact_schema(proj)
    prompt = (APP_PROMPT
              .replace("__LANGUAGE__", LANG_NAMES[lang])
              .replace("__SCHEMA__", json.dumps(compact, ensure_ascii=False, default=str))
              .replace("__FACTS__", json.dumps(proj.notes, ensure_ascii=False)))
    if brief:
        prompt += f"\n\n<what_the_user_asked_for>\n{brief}\n</what_the_user_asked_for>\n" \
                  "Build exactly this, using the rules above."
    result = (await run_agent_subscription(proj, prompt)
              if AI_BACKEND == "subscription"
              else await run_in_threadpool(run_agent_api, proj, prompt))
    raw = re.sub(r"^```(?:json)?|```$", "", result["reply"].strip(), flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise RuntimeError(T(lang, "err_app_invalid"))
    spec = json.loads(m.group(0))
    try:
        validate_app_spec(spec)
    except ValueError as exc:
        raise RuntimeError(T(lang, "err_app_invalid")) from exc
    spec["generated_at"] = time.strftime("%Y-%m-%d %H:%M")
    proj.app = spec
    proj.save_app()
    log.info(f"[{pid}] app: done in {time.monotonic() - t0:.1f}s — "
             f"{len(spec.get('views', []))} view(s): {[v.get('type') for v in spec.get('views', [])]}")
    proj.log_activity("info", T(lang, "act_app_ready"))
    return {"app": spec}


APP_PROPOSE_PROMPT = SCENARIO_GUIDANCE + CALCULATOR_GUIDANCE + """You are a product person looking at a company's spreadsheets.

Study the schema and known facts below and propose 2-3 DIFFERENT internal apps
that would take this работа out of Excel — each one a concrete working surface
this business would use daily, not a generic dashboard.

Return ONE json object, no prose, no fences:

{
  "reading": "<2-3 sentences in __LANGUAGE__: what this data actually is and how
              the team most likely works with it today>",
  "proposals": [
    {"id": "a",
     "title": "<short app name in __LANGUAGE__>",
     "pitch": "<one sentence: what it replaces and why it is better>",
     "does": ["<3-5 concrete things it lets a person do>"],
     "for_whom": "<who uses it daily>",
     "effort": "small|medium|large"}
  ],
  "questions": [
    {"question": "<what you must know to build the right app, in __LANGUAGE__>",
     "options": ["<2-4 concrete answers>"]}
  ]
}

Rules:
- Proposals must differ in PURPOSE (e.g. daily entry vs. weekly review vs.
  problem-hunting), not in colour.
- Ground every proposal in the real columns and tables you see; name the actual
  entities (sites, products, people) where it helps.
- 2-3 questions maximum, the ones that would change what you build.
- Everything user-facing in __LANGUAGE__, business words only.

<schema>__SCHEMA__</schema>
<known_facts>__FACTS__</known_facts>
"""


async def run_app_proposal(proj: Project):
    """Read the data and propose apps worth building (cheap, no tools)."""
    lang, pid = proj.lang, proj.id
    t0 = time.monotonic()
    proj.log_activity("info", T(lang, "act_app_thinking"))
    prompt = (APP_PROPOSE_PROMPT
              .replace("__LANGUAGE__", LANG_NAMES[lang])
              .replace("__SCHEMA__", json.dumps(_compact_schema(proj), ensure_ascii=False, default=str))
              .replace("__FACTS__", json.dumps(proj.notes, ensure_ascii=False)))
    result = (await run_agent_subscription(proj, prompt)
              if AI_BACKEND == "subscription"
              else await run_in_threadpool(run_agent_api, proj, prompt))
    raw = re.sub(r"^```(?:json)?|```$", "", result["reply"].strip(), flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise RuntimeError(T(lang, "err_app_invalid"))
    plan = json.loads(m.group(0))
    log.info(f"[{pid}] app proposal: {len(plan.get('proposals', []))} option(s) in {time.monotonic() - t0:.1f}s")
    return {"plan": plan}
