import json
from types import SimpleNamespace
from contextlib import contextmanager
import pytest
from bizzmind import agent, app_records
from bizzmind.app_spec import validate_app_spec

@pytest.mark.parametrize('tool',['create_chart','update_chart','delete_chart','define_filter','define_view','drop_view'])
def test_app_scope_blocks_dashboard_mutations(fake_project,tool):
    result,error=agent._execute_tool_inner(fake_project(chat_scope='app'),tool,{})
    assert error and 'only build the app' in json.loads(result)['error']

def test_scope_separates_recap_and_resets_session(fake_project):
    proj=fake_project(messages=['old'],sub_lang='en',chat=[{'role':'user','text':'Make a dashboard','scope':'dashboard'},{'role':'user','text':'Edit quantities','scope':'app'}])
    agent.set_chat_scope(proj,'app')
    assert proj.messages==[] and proj.sub_lang is None
    assert 'Edit quantities' in agent.conversation_recap(proj)
    assert 'Make a dashboard' not in agent.conversation_recap(proj)

def test_only_configured_edit_fields_and_tables(monkeypatch,fake_project):
    monkeypatch.setattr(app_records.db,'columns',lambda *a:[('quantity','numeric')])
    proj=fake_project(app={'views':[{'type':'entry','mode':'edit','table':'items','fields':[{'column':'quantity'}]}]})
    assert app_records.editable_form(proj,0,'items')
    with pytest.raises(ValueError):app_records.editable_form(proj,0,'other')
    proj.app['views'][0]['mode']='insert'
    with pytest.raises(ValueError):app_records.editable_form(proj,0,'items')

@pytest.mark.parametrize('count',[0,2])
def test_failed_single_record_match_rolls_back(monkeypatch,count):
    rolled_back=[]
    @contextmanager
    def connect(pid):
        try:yield SimpleNamespace(execute=lambda *a:SimpleNamespace(rowcount=count))
        except Exception:
            rolled_back.append(True)
            raise
    monkeypatch.setattr(app_records.db,'connect',connect)
    with pytest.raises(app_records.RecordConflict):app_records.update_record('test','items','(0,1)','123',{'quantity':5})
    assert rolled_back==[True]

@pytest.mark.parametrize('view',[{'type':'entry','table':'items','mode':'delete'},{'type':'entry','table':'items','mode':'edit','fields':[]}])
def test_invalid_record_forms_are_rejected(view):
    with pytest.raises(ValueError):validate_app_spec({'views':[view]})
