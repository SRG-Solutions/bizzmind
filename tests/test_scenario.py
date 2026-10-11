from copy import deepcopy
import pytest
from bizzmind.app_spec import validate_app_spec
from bizzmind.scenario import validate_scenario


def model():
    return dict(inputs=[dict(id='price',label='Price',value=10,min=0,max=100,step=1)],periods=3,period_label='Year',
        outputs=[dict(id='revenue',label='Revenue',formula=['mul','price',20]),dict(id='cash',label='Cash',initial=-300,formula=['add','prev.cash','revenue'])],
        metrics=[dict(output='cash',aggregate='last',label='Closing cash')],
        charts=[dict(title='Cash',chart_type='line',y_fields=['cash'])])


def test_custom_scenario_is_a_complete_app():
    validate_app_spec(dict(start_view=0,views=[dict(type='scenario',hint='Synthetic planning assumptions',scenario=model())]))


@pytest.mark.parametrize('formula', [['div',1,0],['sub',1],['eval','price'],['add','missing',1],['add','cash',1],['pow',10,1000]])
def test_invalid_formulas_rejected_before_persistence(formula):
    spec=model(); spec['outputs'][0]['formula']=formula
    with pytest.raises(ValueError):validate_scenario(spec)


def test_lazy_zero_guard_and_preset_runtime_check():
    spec=model();spec['outputs'][0]['formula']=['if',['gt','price',0],['div',100,'price'],0]
    spec['presets']=[dict(name='No sales',values=dict(price=0))]
    validate_scenario(spec)
    spec['outputs'][0]['formula']=['div',100,'price']
    with pytest.raises(ValueError):validate_scenario(spec)


@pytest.mark.parametrize('periods',[0,121,1.5])
def test_invalid_horizon(periods):
    spec=model();spec['periods']=periods
    with pytest.raises(ValueError):validate_scenario(spec)


def test_dangerous_or_duplicate_identifiers():
    for key in ['period','constructor','__proto__','cash']:
        spec=model();spec['inputs'][0]['id']=key
        with pytest.raises(ValueError):validate_scenario(spec)


def test_invalid_start_view():
    with pytest.raises(ValueError):validate_app_spec(dict(start_view=2,views=[dict(type='scenario',hint='Test',scenario=model())]))
