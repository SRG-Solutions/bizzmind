"""Strict API compatibility must not remove our own tool input safeguards."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import anthropic
import pytest

from bizzmind import agent
from bizzmind.i18n import T


def schema_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from schema_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from schema_nodes(child)


@pytest.fixture
def api_project(monkeypatch, fake_project):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only-not-a-key")
    monkeypatch.setattr(agent, "build_system_prompt", lambda p: "Synthetic test only.")
    monkeypatch.setattr(agent, "describe_schema", lambda p: [])
    return fake_project(messages=[], chat=[], new_charts=[], job_id=None,
                        new_questions=[], chat_scope="dashboard")


@pytest.mark.parametrize("scope", ["dashboard", "app"])
def test_api_request_uses_compatible_schemas_and_preserves_originals(monkeypatch, api_project, scope):
    original = deepcopy(agent.TOOLS)
    api_project.chat_scope = scope
    create = Mock(return_value=SimpleNamespace(
        stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Ready.")]))
    monkeypatch.setattr(agent, "client", SimpleNamespace(beta=SimpleNamespace(
        messages=SimpleNamespace(create=create))))

    assert agent.run_agent_api(api_project, "Hello")["reply"] == "Ready."
    sent = create.call_args.kwargs["tools"]
    expected = {t["name"] for t in agent.TOOLS
                if scope != "app" or t["name"] in agent.APP_CHAT_TOOLS}
    assert {t["name"] for t in sent} == expected
    assert all(t["strict"] is True for t in sent)
    for tool in sent:
        for node in schema_nodes(tool["input_schema"]):
            assert "maxItems" not in node
            assert "pattern" not in node
            assert node.get("minItems", 0) in (0, 1)
    assert agent.TOOLS == original
    questions = next(t for t in sent if t["name"] == "present_questions")
    options = questions["input_schema"]["properties"]["questions"]["items"]["properties"]["options"]
    assert "minItems: 2" in options["description"]
    assert "maxItems: 6" in options["description"]


@pytest.mark.parametrize("count", [0, 1, 7])
def test_question_limits_are_enforced_before_changing_project(fake_project, count):
    old = [{"question": "Existing question"}]
    proj = fake_project(new_questions=old)
    result, error = agent.execute_tool(proj, "present_questions", {
        "questions": [{"question": "Choose", "options": [str(n) for n in range(count)], "multi": False}]})
    assert error and "options" in result
    assert proj.new_questions == old
    assert proj.activity[-1] == ("error", T(proj.lang, "act_tool_error"))


def test_question_count_and_valid_boundaries(fake_project):
    question = {"question": "Choose", "options": ["A", "B"], "multi": False}
    proj = fake_project(new_questions=[])
    for questions in ([], [question] * 5):
        _, error = agent._execute_tool_inner(proj, "present_questions", {"questions": questions})
        assert error and proj.new_questions == []
    questions = [dict(question, options=[str(i) for i in range(6)])] * 4
    _, error = agent._execute_tool_inner(proj, "present_questions", {"questions": questions})
    assert not error and proj.new_questions == questions


@pytest.mark.parametrize("name", ["create_chart", "update_chart"])
@pytest.mark.parametrize("count", [0, 9])
def test_chart_limits_are_enforced_before_querying(monkeypatch, fake_project, name, count):
    query = Mock(side_effect=AssertionError("Invalid input must not reach the database"))
    monkeypatch.setattr(agent, "run_readonly_sql", query)
    args = dict(title="Test", chart_type="bar", sql="SELECT 1", x_field="x",
                y_fields=[f"y{n}" for n in range(count)], insight="Synthetic test")
    if name == "update_chart":
        args["id"] = 1
    result, error = agent._execute_tool_inner(fake_project(), name, args)
    assert error and "y_fields" in result
    query.assert_not_called()


@pytest.mark.parametrize("name,args,db_function", [
    ("define_view", {"name": "bad_name", "sql": "SELECT 1", "description": "Test"}, "create_view"),
    ("drop_view", {"name": "bad_name"}, "drop_view"),
])
def test_name_patterns_are_enforced_before_database_changes(monkeypatch, fake_project, name, args, db_function):
    mutation = Mock(side_effect=AssertionError("Invalid name must not reach the database"))
    monkeypatch.setattr(agent.db, db_function, mutation)
    result, error = agent._execute_tool_inner(fake_project(), name, args)
    assert error and "Invalid name" in result
    mutation.assert_not_called()


@pytest.mark.parametrize("lang", ["bg", "en"])
def test_provider_error_is_logged_but_not_shown_to_user(monkeypatch, api_project, caplog, lang):
    api_project.lang = lang
    diagnostic = "tools.3.custom: For array type, maxItems is not supported"
    response = SimpleNamespace(status_code=400, request=SimpleNamespace(),
                               headers={"request-id": "test-request-id"})
    failure = anthropic.BadRequestError(diagnostic, response=response,
                                       body={"error": {"type": "invalid_request_error", "message": diagnostic}})
    create = Mock(side_effect=failure)
    monkeypatch.setattr(agent, "client", SimpleNamespace(beta=SimpleNamespace(
        messages=SimpleNamespace(create=create))))

    with pytest.raises(RuntimeError) as exc:
        agent.run_agent_api(api_project, "Hello")
    assert str(exc.value) == T(lang, "err_ai_failed")
    assert "maxItems" not in str(exc.value) and "400" not in str(exc.value)
    assert diagnostic in caplog.text and "test-request-id" in caplog.text
    assert api_project.messages == []
