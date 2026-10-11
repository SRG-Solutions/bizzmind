"""Validate the shared app format before either generation path persists it."""
def validate_app_spec(spec: object) -> None:
    if not isinstance(spec, dict) or not isinstance(spec.get('views'), list) or not spec['views']:
        raise ValueError("The spec needs a non-empty 'views' list.")
    if 'start_view' in spec and (type(spec['start_view']) is not int or not 0 <= spec['start_view'] < len(spec['views'])):
        raise ValueError('start_view must identify an existing view.')
    for view in spec['views']:
        if not isinstance(view, dict) or view.get('type') not in {'kpi', 'entry', 'table', 'chart', 'calculator', 'scenario'}:
            raise ValueError('Supported view types: kpi, entry, table, chart, calculator, scenario.')
        kind = view['type']
        if kind == 'entry' and not (view.get('table') or view.get('tables')):
            raise ValueError("An entry view needs 'table' or 'tables'.")
        if kind == 'entry' and view.get('mode', 'insert') not in {'insert', 'edit'}:
            raise ValueError('Entry mode must be insert or edit.')
        if kind == 'entry' and view.get('mode') == 'edit':
            fields = view.get('fields')
            if not isinstance(fields, list) or not fields or any(not isinstance(f, dict) or not isinstance(f.get('column'), str) or not f['column'].strip() for f in fields):
                raise ValueError('An edit form needs real writable fields.')
        if kind == 'scenario':
            from bizzmind.scenario import validate_scenario
            if not isinstance(view.get('hint'), str) or not view['hint'].strip():
                raise ValueError('A scenario needs a readable explanation of its assumptions and sources.')
            validate_scenario(view.get('scenario'))
        if kind == 'calculator':
            validate_calculator(view)
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


# Keep ranges aligned with web/src/lib/financial-calculator.ts.
CALCULATOR_RANGES = {
    'mortgage': {'price': (0, 1e9), 'down': (0, 1e9), 'rate': (0, 30), 'years': (1, 40), 'extra': (0, 1e7)},
    'forecast': {'revenue': (0, 1e12), 'growth': (-100, 200), 'margin': (0, 100), 'costs': (0, 1e12), 'years': (1, 10)},
    'investment': {'initial': (0, 1e9), 'contribution': (0, 1e7), 'return': (-50, 100), 'years': (1, 40)},
    'demand': {'demand': (0, 1e9), 'growth': (-100, 200), 'stock': (0, 1e9), 'incoming': (0, 1e9), 'lead': (0, 365), 'horizon': (1, 365), 'safety': (0, 365)},
}


def validate_calculator(view: dict) -> None:
    import math
    config = view.get('calculator')
    if not isinstance(config, dict) or not isinstance(config.get('kind'), str) or config['kind'] not in CALCULATOR_RANGES:
        raise ValueError('A calculator needs kind: mortgage, forecast, investment or demand.')
    if not isinstance(view.get('hint'), str) or not view['hint'].strip():
        raise ValueError('Explain the starting assumptions and their source in hint.')
    ranges = CALCULATOR_RANGES[config['kind']]
    defaults = config.get('defaults')
    if not isinstance(defaults, dict) or set(defaults) != set(ranges):
        raise ValueError('Calculator defaults must contain exactly: ' + ', '.join(ranges))
    for key, (lo, hi) in ranges.items():
        value = defaults[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f'Calculator {key} must be a finite number between {lo} and {hi}.')
        if key in {'years', 'lead', 'horizon', 'safety'} and value != int(value):
            raise ValueError(f'Calculator {key} must be a whole number.')
    if config['kind'] == 'mortgage' and defaults['down'] > defaults['price']:
        raise ValueError('Down payment cannot exceed property price.')
    if config.get('currency', 'EUR') not in ('EUR', 'USD', 'GBP', 'BGN'):
        raise ValueError('Supported calculator currencies: EUR, USD, GBP, BGN.')

    charts = config.get('charts')
    series = {
        'mortgage': {'balance', 'principal_paid', 'interest_paid'},
        'forecast': {'revenue', 'profit', 'expenses'},
        'investment': {'value', 'contributed', 'gain'},
        'demand': {'stock', 'shortage', 'demand', 'receipts'},
    }[config['kind']]
    if charts is not None:
        if not isinstance(charts, list) or not 1 <= len(charts) <= 6:
            raise ValueError('A calculator supports 1 to 6 accompanying charts; omit charts for defaults.')
        for chart in charts:
            if not isinstance(chart, dict) or chart.get('chart_type') not in ('line', 'area', 'bar'):
                raise ValueError('Calculator chart_type must be line, area or bar.')
            fields = chart.get('y_fields')
            if not isinstance(fields, list) or not fields or not all(isinstance(f, str) and f in series for f in fields) or len(set(fields)) != len(fields):
                raise ValueError('Calculator y_fields must be unique model outputs: ' + ', '.join(sorted(series)))
            if 'title' in chart and (not isinstance(chart['title'], str) or not chart['title'].strip()):
                raise ValueError('Calculator chart title must be nonempty text.')
            if 'compare_baseline' in chart and not isinstance(chart['compare_baseline'], bool):
                raise ValueError('compare_baseline must be a boolean.')
