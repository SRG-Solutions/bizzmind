import pytest
from bizzmind.app_spec import validate_app_spec


def test_existing_app_still_supported():
    validate_app_spec({'views': [{'type':'kpi','items':[]},{'type':'entry','table':'orders'},{'type':'table','sql':'select 1'}]})


def test_chart_contract_accepts_supported_types():
    for kind in ('bar','line','area','pie'):
        validate_app_spec({'views':[{'type':'chart','chart_type':kind,'sql':'select month,revenue from sales','x_field':'month','y_fields':['revenue']}]})


@pytest.mark.parametrize('patch',[{'chart_type':'html'},{'sql':''},{'x_field':None},{'y_fields':[]},{'y_fields':'revenue'}])
def test_invalid_chart_rejected_before_save(patch):
    chart={'type':'chart','chart_type':'line','sql':'select 1','x_field':'month','y_fields':['revenue']}
    with pytest.raises(ValueError):validate_app_spec({'views':[{**chart,**patch}]})


@pytest.mark.parametrize('spec',[None,[],{}, {'views':[]},{'views':[None]},{'views':[{'type':'entry'}]}])
def test_invalid_shape_rejected(spec):
    with pytest.raises(ValueError):validate_app_spec(spec)


@pytest.mark.parametrize('kind,defaults', [
    ('mortgage',dict(price=100000,down=20000,rate=4,years=25,extra=0)),
    ('forecast',dict(revenue=100000,growth=10,margin=40,costs=20000,years=5)),
    ('investment',dict(initial=1000,contribution=100,**{'return':5},years=10)),
    ('demand',dict(demand=300,growth=10,stock=100,incoming=50,lead=5,horizon=30,safety=7)),
])
def test_calculator_models(kind, defaults):
    validate_app_spec({'views':[{'type':'calculator','hint':'Confirmed planning assumptions','calculator':{'kind':kind,'defaults':defaults}}]})


@pytest.mark.parametrize('patch', [
    {'calculator': {'kind': 'arbitrary_code', 'defaults': {}}},
    {'hint': ''},
    {'calculator': {'kind': 'forecast', 'defaults': {}}},
    {'calculator': {'kind': 'forecast', 'defaults': dict(revenue=True,growth=10,margin=40,costs=20000,years=5)}},
    {'calculator': {'kind': 'forecast', 'defaults': dict(revenue=float('nan'),growth=10,margin=40,costs=20000,years=5)}},
    {'calculator': {'kind': 'forecast', 'defaults': dict(revenue=100000,growth=10,margin=140,costs=20000,years=5)}},
    {'calculator': {'kind': 'forecast', 'defaults': dict(revenue=100000,growth=10,margin=40,costs=20000,years=1.5)}},
    {'calculator': {'kind': 'mortgage', 'defaults': dict(price=100,down=101,rate=4,years=10,extra=0)}},
])
def test_invalid_calculator(patch):
    view={'type':'calculator','hint':'Confirmed assumptions','calculator':{'kind':'forecast','defaults':dict(revenue=100000,growth=10,margin=40,costs=20000,years=5)}}
    with pytest.raises(ValueError):
        validate_app_spec({'views': [{**view, **patch}]})


@pytest.mark.parametrize('charts', [[],[{'chart_type':'pie','y_fields':['profit']}],[{'chart_type':'line','y_fields':['invented']}],[{'chart_type':'line','y_fields':['profit','profit']}],[{'chart_type':'line','y_fields':['profit'],'compare_baseline':'yes'}]])
def test_invalid_calculator_charts(charts):
    with pytest.raises(ValueError):
        validate_app_spec({'views':[{'type':'calculator','hint':'Test assumptions','calculator':{'kind':'forecast','defaults':dict(revenue=100,growth=10,margin=40,costs=20,years=5),'charts':charts}}]})


def test_custom_calculator_charts():
    validate_app_spec({'views':[{'type':'calculator','hint':'Test assumptions','calculator':{'kind':'forecast','defaults':dict(revenue=100,growth=10,margin=40,costs=20,years=5),'charts':[{'title':'Revenue and profit','chart_type':'line','y_fields':['revenue','profit'],'compare_baseline':True}]}}]})
