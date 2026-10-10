"""Isolated, subscription-backed demo. Run with .venv/bin/python tools/local_demo.py.

Uses its own Postgres cluster over a private Unix socket, never the configured
Supabase database/storage. API binds only to loopback. Start the web UI with:
  cd web && API_URL=http://127.0.0.1:8000 npm run dev -- --hostname 127.0.0.1 --port 3001
No production authentication or billing code is changed by this entry point.
"""
from pathlib import Path
import os
import subprocess
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "local-hackathon-demo"
USER_ID = "00000000-0000-4000-8000-000000000001"
ORG_ID = "00000000-0000-4000-8000-000000000002"


def configure():
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Set empty values explicitly: the app's dotenv loader uses setdefault.
    for key in ("SUPABASE_DB_URL", "SUPABASE_URL", "SUPABASE_ANON_KEY",
                "SUPABASE_SERVICE_KEY", "GAMMA_API_KEY", "PUBLIC_BASE_URL",
                "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "PADDLE_API_KEY"):
        os.environ[key] = ""
    os.environ.update(AI_BACKEND="subscription", INLINE_JOBS="0",
                      DATA_DIR=str(STATE / "files"))
    socket_dir = Path("/private/tmp/bizzmind-demo-pg")
    socket_dir.mkdir(mode=0o700, exist_ok=True)
    socket_dir.chmod(0o700)
    os.environ["DATABASE_URL"] = f"postgresql:///bizzmind_local_demo?host={socket_dir}"
    return socket_dir


def bootstrap(socket_dir):
    bin_dir = Path(os.environ.get("DEMO_PG_BIN", "/opt/homebrew/opt/postgresql@16/bin"))
    cluster = STATE / "postgres"
    if not (cluster / "PG_VERSION").exists():
        subprocess.run([str(bin_dir / "initdb"), "-D", str(cluster),
                        "--auth-local=trust", "--auth-host=reject", "--encoding=UTF8"], check=True)
    status = subprocess.run([str(bin_dir / "pg_ctl"), "-D", str(cluster), "status"], capture_output=True)
    if status.returncode:
        subprocess.run([str(bin_dir / "pg_ctl"), "-D", str(cluster), "-l", str(STATE / "postgres.log"),
                        "-o", f"-k {socket_dir} -c listen_addresses=''", "start", "-w"], check=True)
    import psycopg
    with psycopg.connect(f"dbname=postgres host={socket_dir}", autocommit=True) as con:
        if not con.execute("SELECT 1 FROM pg_database WHERE datname='bizzmind_local_demo'").fetchone():
            con.execute("CREATE DATABASE bizzmind_local_demo")
    with psycopg.connect(os.environ["DATABASE_URL"]) as con:
        con.execute("CREATE SCHEMA IF NOT EXISTS auth")
        con.execute("CREATE TABLE IF NOT EXISTS auth.users (id uuid PRIMARY KEY, email text)")
        con.execute("CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$")
        for role in ("anon", "authenticated", "service_role"):
            if not con.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                con.execute(psycopg.sql.SQL("CREATE ROLE {} NOLOGIN").format(psycopg.sql.Identifier(role)))
        con.execute("CREATE TABLE IF NOT EXISTS public.local_demo_migrations (name text PRIMARY KEY)")
        for migration in sorted((ROOT / "supabase" / "migrations").glob("*.sql")):
            if not con.execute("SELECT 1 FROM public.local_demo_migrations WHERE name=%s", (migration.name,)).fetchone():
                con.execute(migration.read_text())
                con.execute("INSERT INTO public.local_demo_migrations VALUES (%s)", (migration.name,))
        con.execute("INSERT INTO auth.users VALUES (%s, 'demo@example.test') ON CONFLICT DO NOTHING", (USER_ID,))
        con.execute("INSERT INTO public.organizations (id,name,plan,credits_quota) VALUES (%s,'Bizzmind Demo','ultra',1000000000) ON CONFLICT DO NOTHING", (ORG_ID,))
        con.execute("INSERT INTO public.memberships (org_id,user_id,role) VALUES (%s,%s,'owner') ON CONFLICT DO NOTHING", (ORG_ID, USER_ID))


def build_app():
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, RedirectResponse
    import auth
    from bizzmind import plans
    from bizzmind.routes import projects, auth_routes, export_routes, brand_routes
    # Process-local limits only. Usage is still tracked in the isolated DB.
    plans.PLANS["ultra"] = {**plans.PLANS["ultra"], "projects": 1000000000,
                            "files_per_project": 1000000000, "monthly": False}
    app = FastAPI(title="Bizzmind local demo")
    @app.get("/api/local-demo/start")
    def start():
        response = RedirectResponse("/app")
        response.set_cookie("sb_access", "local-demo", httponly=True, samesite="strict")
        return response

    app.include_router(projects.router)
    app.include_router(brand_routes.router)
    # Only read-only account endpoints: no payments, invitations or auth writes.
    for router, paths in ((auth_routes.router, {"/api/auth/me", "/api/account", "/api/plans"}),
                          (export_routes.router, {"/api/p/{pid}/pres/credits"})):
        app.router.routes.extend(r for r in router.routes if r.path in paths)

    @app.middleware("http")
    async def local_user(request: Request, call_next):
        origin = request.headers.get("origin")
        if (request.client.host not in {"127.0.0.1", "::1", "testclient"}
                or request.url.hostname not in {"127.0.0.1", "localhost", "testserver"}
                or (origin and urlparse(origin).hostname not in {"127.0.0.1", "localhost"})):
            return JSONResponse({"detail": "Local demo only"}, status_code=403)
        token = auth.set_current_user(auth.User(USER_ID, "demo@example.test", [ORG_ID], {ORG_ID: "owner"}))
        try:
            return await call_next(request)
        finally:
            auth._current.reset(token)
    return app


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    bootstrap(configure())
    import uvicorn
    uvicorn.run(build_app(), host="127.0.0.1", port=8000, proxy_headers=False)
