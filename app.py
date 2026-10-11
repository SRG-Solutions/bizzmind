"""Bizzmind — prototype backend.

Multi-project: every project is an isolated environment (own PostgreSQL schema,
chat transcript, knowledge notes, filters, dashboard, uploaded files,
PROGRESS.md) living under data/projects/<id>/.

Pipeline per project: Excel/CSV upload -> PostgreSQL (Supabase) -> natural-language chat ->
Claude interviews the user + generates SQL/filters/chart specs via tool use ->
frontend renders a live, filterable dashboard.

This module only assembles the FastAPI application from the `bizzmind` package
and re-exports the names worker.py and tools/ rely on.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from bizzmind.config import (  # noqa: F401  (re-exports)
    AI_BACKEND, DATA_DIR, GAMMA_API_KEY, INLINE_JOBS, MAX_CHART_ROWS, MAX_PREVIEW_ROWS,
    MAX_SERIES, MODEL, NO_CACHE, PROJECTS_DIR, PUBLIC_BASE_URL, ROOT, SUB_TIMEOUT_S,
    _short, log,
)
from bizzmind.i18n import LANGS, LANG_NAMES, MSG, T, req_lang  # noqa: F401
from bizzmind.project import (  # noqa: F401
    PROJECTS, Project, backfill_file_map, get_project, require_project_access, write_progress,
)
from bizzmind.data import (  # noqa: F401
    FORBIDDEN_SQL, apply_filters_to_sql, clean_frame, describe_schema, filters_with_options,
    frame_from_raw, frame_to_records, load_frames_from_upload, pg_compat, resolve_filter_options,
    run_readonly_sql, sanitize_identifier, verify_dashboard,
)
from bizzmind.brand import (  # noqa: F401
    brand_colors, brand_dir, brand_excerpt, brand_files, brand_logo_path, brand_theme,
    extract_brand_assets,
)
from bizzmind.localization import content_lang, localized_content, translatable_items  # noqa: F401
from bizzmind.agent import (  # noqa: F401
    TOOLS, CancelledByUser, build_system_prompt, client, dispatch_agent, execute_tool, run_agent_api,
    run_agent_subscription, run_deck, run_review, run_translate,
)
from bizzmind.auth_middleware import auth_middleware
from bizzmind.routes import auth_routes, brand_routes, demo_routes, export_routes, pages, projects

app = FastAPI(title="Bizzmind")

app.middleware("http")(auth_middleware)
# outermost: restore the real path behind the Vercel rewrite BEFORE auth looks at it
from bizzmind.path_restore import PathRestoreMiddleware  # noqa: E402
app.add_middleware(PathRestoreMiddleware)

app.include_router(auth_routes.router)
app.include_router(pages.router)
app.include_router(projects.router)
app.include_router(brand_routes.router)
app.include_router(export_routes.router)
app.include_router(demo_routes.router)

app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
