"""Record operations exposed by an app's explicitly configured edit forms."""
from psycopg import sql
import db


class RecordConflict(ValueError):
    pass


def editable_form(proj, view_index: int, table: str) -> dict:
    views = proj.app.get('views', [])
    if not 0 <= view_index < len(views):
        raise ValueError('Unknown form')
    view = views[view_index]
    tables = [v['table'] for v in view.get('tables', [])] or [view.get('table')]
    if view.get('type') != 'entry' or view.get('mode') != 'edit' or table not in tables:
        raise ValueError('Not an edit form')
    columns = {c for c, _ in db.columns(proj.id, table)}
    fields = view.get('fields', [])
    if not fields or any(f['column'] not in columns for f in fields):
        raise ValueError('Invalid form fields')
    return view


def update_record(pid: str, table: str, rowid: str, version: str, values: dict) -> None:
    """Atomically update exactly one unchanged row. xmin prevents stale ctid reuse."""
    with db.connect(pid) as con:
        assignments = sql.SQL(', ').join(sql.SQL('{} = %s').format(sql.Identifier(c)) for c in values)
        query = sql.SQL('UPDATE {}.{} SET {} WHERE ctid = %s::tid AND xmin::text = %s').format(
            sql.Identifier(db.schema_for(pid)), sql.Identifier(table), assignments)
        cur = con.execute(query, [*values.values(), rowid, version])
        if cur.rowcount != 1:
            raise RecordConflict('The record changed; reload before saving')
