"""Bounded declarative scenarios: arithmetic only, no executable generated code."""
import math
import re


def validate_scenario(spec):
    def fail(message):
        raise ValueError('Scenario: ' + message)
    def number(v):
        return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v) and abs(v) <= 1e15
    def label(v):
        return isinstance(v, str) and bool(v.strip()) and len(v) <= 500
    def identifier(v):
        return isinstance(v, str) and re.fullmatch(r'[a-z][a-z0-9_]{0,39}', v) and v not in {'period', 'constructor', 'prototype', '__proto__'}
    if not isinstance(spec, dict):
        fail('needs a configuration object.')
    inputs, outputs = spec.get('inputs'), spec.get('outputs')
    if not isinstance(inputs, list) or not 1 <= len(inputs) <= 16:
        fail('needs 1–16 inputs.')
    if not isinstance(outputs, list) or not 1 <= len(outputs) <= 24:
        fail('needs 1–24 outputs.')
    ids = set()
    for f in inputs:
        if not isinstance(f, dict) or not identifier(f.get('id')) or f['id'] in ids or not label(f.get('label')):
            fail('input ids must be unique and labels readable.')
        ids.add(f['id'])
        if not all(number(f.get(k)) for k in ('value', 'min', 'max', 'step')) or not f['min'] <= f['value'] <= f['max'] or f['min'] >= f['max'] or f['step'] <= 0:
            fail('input values need valid bounds and a positive step.')
        if 'unit' in f and not isinstance(f['unit'], str):
            fail('units must be text.')
    output_ids = set()
    for o in outputs:
        if not isinstance(o, dict) or not identifier(o.get('id')) or o['id'] in ids | output_ids or not label(o.get('label')):
            fail('output ids must be unique and labels readable.')
        if 'unit' in o and not isinstance(o['unit'], str):
            fail('units must be text.')
        output_ids.add(o['id'])
    budget = [0]
    def expression(e, refs, depth=0):
        budget[0] += 1
        if depth > 12 or budget[0] > 1500:
            fail('formulas are too complex.')
        if number(e):
            return
        if isinstance(e, str) and e in refs:
            return
        if not isinstance(e, list) or not e or not isinstance(e[0], str):
            fail('use numeric constants, known references, or arithmetic arrays.')
        op, args = e[0], e[1:]
        arities = {'sub':2, 'div':2, 'pow':2, 'abs':1, 'if':3, 'gt':2, 'gte':2, 'lt':2, 'lte':2}
        if op in {'add', 'mul', 'min', 'max'}:
            if not 2 <= len(args) <= 16:
                fail('variadic operations need 2–16 arguments.')
        elif op not in arities or len(args) != arities[op]:
            fail('unsupported operation or wrong number of arguments.')
        for arg in args:
            expression(arg, refs, depth+1)
    expression(spec.get('periods'), ids)
    if not label(spec.get('period_label')):
        fail('needs a period label.')
    refs = ids | {'period'} | {'prev.' + key for key in output_ids}
    for o in outputs:
        if 'initial' in o:
            expression(o['initial'], ids)
        expression(o.get('formula'), refs)
        refs.add(o['id'])
    metrics = spec.get('metrics')
    if not isinstance(metrics, list) or not 1 <= len(metrics) <= 6:
        fail('needs 1–6 decision metrics.')
    for m in metrics:
        if not isinstance(m, dict) or m.get('output') not in output_ids or m.get('aggregate') not in ('last','sum','min','max') or not label(m.get('label')):
            fail('metrics must reference an output and supported aggregation.')
    charts = spec.get('charts')
    if not isinstance(charts, list) or not 1 <= len(charts) <= 6:
        fail('needs 1–6 live charts.')
    for c in charts:
        if not isinstance(c, dict) or not label(c.get('title')) or c.get('chart_type') not in ('line','area','bar'):
            fail('charts need a title and line, area or bar type.')
        ys = c.get('y_fields')
        if not isinstance(ys, list) or not ys or not all(isinstance(y,str) and y in output_ids for y in ys) or len(set(ys)) != len(ys):
            fail('chart series must reference unique outputs.')
        if 'compare_baseline' in c and not isinstance(c['compare_baseline'], bool):
            fail('compare_baseline must be boolean.')
    presets = spec.get('presets', [])
    if not isinstance(presets, list) or len(presets) > 5:
        fail('supports up to five presets.')
    for p in presets:
        if not isinstance(p, dict) or not label(p.get('name')) or not isinstance(p.get('values'), dict) or not p['values']:
            fail('presets need a name and input values.')
        for key, value in p['values'].items():
            f = next((f for f in inputs if f['id']==key), None)
            if not f or not number(value) or not f['min'] <= value <= f['max']:
                fail('preset values must fit the input bounds.')
    # Reject models that already fail at their supplied defaults or presets.
    # User edits may still reach invalid combinations; the UI shows a clear error.
    defaults = {f['id']: f['value'] for f in inputs}
    for values in [defaults] + [{**defaults, **p['values']} for p in presets]:
        try:
            count = evaluate(spec['periods'], values)
            if int(count) != count or not 1 <= count <= 120:
                fail('the planning horizon must be an integer from 1 to 120.')
            previous = {o['id']: evaluate(o.get('initial', 0), values) for o in outputs}
            for period in range(1, int(count) + 1):
                context = {**values, 'period': period, **{'prev.' + k: v for k, v in previous.items()}}
                previous = {}
                for o in outputs:
                    context[o['id']] = previous[o['id']] = evaluate(o['formula'], context)
        except (ValueError, ZeroDivisionError, OverflowError, TypeError) as exc:
            fail('formulas must produce finite results at the baseline and presets: ' + str(exc))


def evaluate(expr, values):
    """Evaluate validated expressions with the same lazy branching as the browser."""
    if isinstance(expr, (int, float)):
        return expr
    if isinstance(expr, str):
        return values[expr]
    op, *args = expr
    if op == 'if':
        return evaluate(args[1] if evaluate(args[0], values) else args[2], values)
    a = [evaluate(arg, values) for arg in args]
    operations = {
        'add': lambda: sum(a), 'mul': lambda: math.prod(a),
        'sub': lambda: a[0]-a[1], 'div': lambda: a[0]/a[1],
        'pow': lambda: math.pow(a[0], a[1]), 'min': lambda: min(a), 'max': lambda: max(a),
        'abs': lambda: abs(a[0]), 'gt': lambda: int(a[0]>a[1]), 'gte': lambda: int(a[0]>=a[1]),
        'lt': lambda: int(a[0]<a[1]), 'lte': lambda: int(a[0]<=a[1]),
    }
    value = operations[op]()
    if not math.isfinite(value) or abs(value)>1e100:
        raise ValueError('calculation overflow')
    return value
