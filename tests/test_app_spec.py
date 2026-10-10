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
