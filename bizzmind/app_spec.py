"""Validate the shared app format before either generation path persists it."""
def validate_app_spec(spec: object) -> None:
    if not isinstance(spec, dict) or not isinstance(spec.get('views'), list) or not spec['views']:
        raise ValueError("The spec needs a non-empty 'views' list.")
    for view in spec['views']:
        if not isinstance(view, dict) or view.get('type') not in {'kpi', 'entry', 'table', 'chart'}:
            raise ValueError('Supported view types: kpi, entry, table, chart.')
        kind = view['type']
        if kind == 'entry' and not (view.get('table') or view.get('tables')):
            raise ValueError("An entry view needs 'table' or 'tables'.")
        if kind == 'entry' and view.get('mode', 'insert') not in {'insert', 'edit'}:
            raise ValueError('Entry mode must be insert or edit.')
        if kind == 'entry' and view.get('mode') == 'edit':
            fields = view.get('fields')
            if not isinstance(fields, list) or not fields or any(not isinstance(f, dict) or not isinstance(f.get('column'), str) or not f['column'].strip() for f in fields):
                raise ValueError('An edit form needs real writable fields.')
        if kind == 'chart':
            if view.get('chart_type') not in {'bar', 'line', 'area', 'pie'}:
                raise ValueError('A chart needs chart_type: bar, line, area or pie.')
            if not isinstance(view.get('sql'), str) or not view['sql'].strip():
                raise ValueError('A chart needs a read-only data query.')
            if not isinstance(view.get('x_field'), str) or not view['x_field'].strip():
                raise ValueError('A chart needs x_field matching a returned column.')
            ys = view.get('y_fields')
            if not isinstance(ys, list) or not ys or not all(isinstance(y, str) and y.strip() for y in ys):
                raise ValueError('A chart needs non-empty y_fields matching returned numeric columns.')
