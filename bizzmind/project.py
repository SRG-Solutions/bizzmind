"""Project — one isolated analytics environment — and the process-wide cache."""

import json
import re
import shutil
import time

import db
import jobs
import storage
import auth as sb_auth
from fastapi import HTTPException

from bizzmind.config import DATA_DIR, PROJECTS_DIR, _short, log
from bizzmind.i18n import T
from bizzmind.data import describe_schema, load_frames_from_upload
from bizzmind.brand import extract_brand_assets


def require_project_access(proj, admin: bool = False):
    """Tenancy check: the current user must belong to the project's organisation."""
    u = sb_auth.current_user()
    if u is None:
        return  # background/tool contexts (worker, tests) run trusted
    ok = u.can_admin(proj.org_id) if admin else u.can_read(proj.org_id)
    if not ok:
        raise HTTPException(403, T(getattr(proj, "lang", "bg"), "forbidden"))


# ---------------------------------------------------------------- projects

class Project:
    """One isolated analytics environment."""

    def __init__(self, pid: str):
        self.id = pid
        # files (uploads, brand assets, PROGRESS.md for the agent) still live on disk;
        # all structured state lives in public.projects (Supabase)
        self.dir = PROJECTS_DIR / pid
        self.dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir = self.dir / "uploads"
        self.uploads_dir.mkdir(exist_ok=True)
        self.db_path = self.dir / "project.duckdb"   # legacy DuckDB file (migration only)
        self.progress_p = self.dir / "PROGRESS.md"

        row = db.project_load(pid)
        if row is None:
            row = self._import_legacy_files(pid)
        self.org_id = row.get("org_id")
        self.meta = row.get("meta") or {}
        self.meta.setdefault("name", row.get("name") or pid)
        self.meta.setdefault("created", row["created_at"].strftime("%Y-%m-%d") if row.get("created_at") else time.strftime("%Y-%m-%d"))
        self.meta.setdefault("files", {})
        self.chat = row.get("chat") or []
        self.notes = row.get("notes") or []
        self.filters = row.get("filters") or []
        self.dashboard = row.get("dashboard") or []
        self.app = row.get("app") or {}
        self.i18n = row.get("i18n") or {}
        self.chart_seq = max((c["id"] for c in self.dashboard), default=0)
        # local dirs are a cache of Supabase Storage. Brand assets are needed by
        # /state (logo, colours) → sync now; uploads only when a file route asks.
        storage.sync_down(pid, "brand", self.dir / "brand")
        self._uploads_synced = False

        self.messages: list = []          # API-backend conversation (in-memory)
        self.sub_client = None
        self.ai_model_id = None       # chosen per request/job: plans.MODELS[...]["model_id"]
        self.app_touched = False      # the turn edited the mini-app (billed as such)            # Agent SDK session
        self.new_charts: list = []        # charts created during current turn
        self.new_questions: list = []     # interview questions from current turn
        self.activity: list = []
        self.act_seq = 0
        self.lang = "bg"                  # UI language of the request driving this turn
        self.job_id: str | None = None    # set by the worker while a job runs
        self.sub_lang: str | None = None  # language the SDK session's prompt was built for

    def ensure_uploads(self):
        if not self._uploads_synced:
            storage.sync_down(self.id, "uploads", self.uploads_dir)
            self._uploads_synced = True

    # ---- persistence (public.projects)
    def _import_legacy_files(self, pid: str) -> dict:
        """First run after the move to Supabase: lift the old per-project JSON
        files into the projects table (and i18n_<lang>.json into the i18n column)."""
        def _load(name, default):
            p = self.dir / name
            try:
                return json.loads(p.read_text()) if p.exists() else default
            except Exception:
                return default
        meta = _load("meta.json", {"name": pid, "created": time.strftime("%Y-%m-%d"), "files": {}})
        i18n = {}
        for p in self.dir.glob("i18n_*.json"):
            try:
                i18n[p.stem.split("_", 1)[1]] = json.loads(p.read_text())
            except Exception:
                pass
        progress = self.progress_p.read_text() if self.progress_p.exists() else None
        db.project_create(pid, meta.get("name", pid), org_id=db.default_org(),
                          meta=meta, dashboard=_load("dashboard.json", []), filters=_load("filters.json", []),
                          notes=_load("notes.json", []), chat=_load("chat.json", []), i18n=i18n, progress=progress)
        log.info(f"[{pid}] metadata imported from legacy JSON files into public.projects")
        return db.project_load(pid)

    def save_meta(self):    db.project_save(self.id, meta=self.meta, name=self.meta.get("name", self.id))
    def save_chat(self):    db.project_save(self.id, chat=self.chat)
    def save_notes(self):   db.project_save(self.id, notes=self.notes)
    def save_filters(self): db.project_save(self.id, filters=self.filters)
    def save_dash(self):    db.project_save(self.id, dashboard=self.dashboard)
    def save_i18n(self):    db.project_save(self.id, i18n=self.i18n)

    def add_chat(self, role: str, text: str, questions: list | None = None):
        if not text and not questions:
            return
        entry = {"role": role, "text": text, "ts": time.strftime("%Y-%m-%d %H:%M"), "scope": getattr(self, "chat_scope", "dashboard")}
        if questions:
            entry["questions"] = questions
        self.chat.append(entry)
        self.save_chat()

    def log_activity(self, kind: str, text: str):
        self.act_seq += 1
        self.activity.append({"seq": self.act_seq, "kind": kind, "text": text,
                              "ts": time.strftime("%H:%M:%S")})
        del self.activity[:-200]
        if self.job_id:
            jobs.log_event(self.job_id, kind, text)

    def save_app(self):
        db.project_save(self.id, app=self.app)

    def reload(self):
        """Refresh structured state from public.projects (another process — the
        worker — may have changed it)."""
        row = db.project_load(self.id)
        if not row:
            return
        self.meta = row.get("meta") or self.meta
        self.chat = row.get("chat") or []
        self.notes = row.get("notes") or []
        self.filters = row.get("filters") or []
        self.dashboard = row.get("dashboard") or []
        self.app = row.get("app") or {}
        self.i18n = row.get("i18n") or {}
        self.chart_seq = max((c["id"] for c in self.dashboard), default=0)
PROJECTS: dict = {}


def backfill_file_map(proj: Project):
    """Uploads made before per-file tracking existed: rebuild filename->tables
    from the stored originals (runs once, then persists)."""
    if proj.meta["files"]:
        return
    uploads = [f for f in sorted(proj.uploads_dir.iterdir())
               if f.suffix.lower() in (".xlsx", ".xls", ".csv")] if proj.uploads_dir.exists() else []
    if not uploads:
        return
    for f in uploads:
        try:
            frames = load_frames_from_upload(f.name, f.read_bytes())
            proj.meta["files"][f.name] = list(frames.keys())
        except Exception as e:
            log.info(f"[{proj.id}] backfill: could not parse '{f.name}' — {_short(e)}")
    proj.save_meta()
    log.info(f"[{proj.id}] backfill: file map rebuilt for {len(proj.meta['files'])} file(s)")


def get_project(pid: str) -> Project:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", pid):
        raise HTTPException(404, f"Unknown project '{pid}'")
    if pid not in PROJECTS and not db.project_exists(pid) and not (PROJECTS_DIR / pid / "meta.json").exists():
        raise HTTPException(404, f"Unknown project '{pid}'")
    if pid not in PROJECTS:
        PROJECTS[pid] = Project(pid)
        backfill_file_map(PROJECTS[pid])
        try:
            extract_brand_assets(PROJECTS[pid])   # backfill for older uploads
        except Exception as e:
            log.info(f"[{pid}] brand backfill failed — {_short(e)}")
    else:
        PROJECTS[pid].reload()
    require_project_access(PROJECTS[pid])
    return PROJECTS[pid]


def migrate_legacy_project():
    """Move the old single-project layout into data/projects/sidaya-pharma."""
    legacy_db = DATA_DIR / "project.duckdb"
    if not legacy_db.exists():
        return
    pid = "sidaya-pharma"
    pdir = PROJECTS_DIR / pid
    if pdir.exists():
        return
    pdir.mkdir(parents=True)
    for src, dst in [(legacy_db, "project.duckdb"), (DATA_DIR / "chat.json", "chat.json"),
                     (DATA_DIR / "notes.json", "notes.json"),
                     (DATA_DIR / "filters.json", "filters.json"),
                     (DATA_DIR / "dashboard.json", "dashboard.json"),
                     (DATA_DIR / "PROGRESS.md", "PROGRESS.md")]:
        if src.exists():
            shutil.move(str(src), str(pdir / dst))
    if (DATA_DIR / "uploads").exists():
        shutil.move(str(DATA_DIR / "uploads"), str(pdir / "uploads"))
    (pdir / "meta.json").write_text(json.dumps(
        {"name": "Sidaya Pharma", "created": time.strftime("%Y-%m-%d"), "files": {}},
        ensure_ascii=False))
    log.info(f"migrated legacy single-project data into projects/{pid}")
migrate_legacy_project()


def write_progress(proj: Project):
    try:
        parts = [f"# {proj.meta['name']} — progress",
                 f"_Updated: {time.strftime('%Y-%m-%d %H:%M')}_", "",
                 "## Data (tables)"]
        parts += [f"- **{t['table']}** — {t['rows']} rows: "
                  f"{', '.join(c['name'] for c in t['columns'])}"
                  for t in describe_schema(proj)] or ["- (none)"]
        parts += ["", "## Knowledge (what the AI knows)"] + (
            [f"- {n}" for n in proj.notes] or ["- (nothing yet)"])
        parts += ["", "## Filters"] + (
            [f"- `{f['id']}` — {f['label']} ({f['type']})" for f in proj.filters] or ["- (none)"])
        parts += ["", "## Dashboard charts"] + (
            [f"- #{c['id']} **{c['title']}** ({c['chart_type']}) — {c['insight']}"
             for c in proj.dashboard] or ["- (none)"])
        proj.progress_p.write_text("\n".join(parts))
        db.project_save(proj.id, progress="\n".join(parts))
    except Exception as e:
        log.info(f"progress: could not write PROGRESS.md — {_short(e)}")
