"""An app tool submission and the agent's final summary are separate outputs."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bizzmind import agent
from bizzmind.i18n import MSG, T


@pytest.fixture
def app_spec():
    return {"title": "Sales planner", "start_view": 0, "views": [{
        "type": "scenario", "title": "Sales plan", "hint": "Synthetic QA assumptions",
        "scenario": {
            "inputs": [{"id": "price", "label": "Price", "value": 10, "min": 0, "max": 100, "step": 1}],
            "periods": 3, "period_label": "Month",
            "outputs": [{"id": "revenue", "label": "Revenue", "formula": ["mul", "price", 20]}],
            "metrics": [{"output": "revenue", "aggregate": "sum", "label": "Total revenue"}],
            "charts": [{"title": "Revenue", "chart_type": "line", "y_fields": ["revenue"]}],
        },
    }]}


@pytest.fixture
def project(monkeypatch, fake_project, tmp_path):
    monkeypatch.setattr(agent, "AI_BACKEND", "api")
    monkeypatch.setattr(agent, "describe_schema", lambda p: [])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only-not-a-key")
    return fake_project(
        app={"title": "Existing app", "views": [{"type": "table", "title": "Existing"}]},
        app_touched=False, app_build_draft=None, save_app=Mock(), job_id=None, dir=tmp_path,
        messages=[{"role": "user", "content": "Unrelated dashboard chat"}],
        chat=[{"role": "user", "text": "Unrelated conversation"}], chat_scope="dashboard",
        sub_client=SimpleNamespace(disconnect=AsyncMock()), sub_lang="bg",
        new_charts=[{"id": 9}], new_questions=[{"question": "Existing question"}],
    )


def submit(project, spec):
    content, error = agent.execute_tool(project, "update_app", {
        "spec": json.dumps(spec), "summary": "Built a sales planner"})
    assert not error, content
    return json.loads(content)


def test_real_api_loop_accepts_tool_submission_followed_by_summary(monkeypatch, project, app_spec):
    old_app, old_messages = project.app, project.messages
    old_client = project.sub_client
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        assert {t["name"] for t in kwargs["tools"]} == agent.APP_BUILD_TOOLS
        assert "Unrelated" not in str(kwargs["messages"])
        project.save_app.assert_not_called()
        assert project.app is old_app
        if len(calls) == 1:
            return SimpleNamespace(stop_reason="tool_use", content=[SimpleNamespace(
                type="tool_use", id="app-call", name="update_app",
                input={"spec": json.dumps(app_spec), "summary": "Built a sales planner"})])
        assert json.loads(kwargs["messages"][-1]["content"][0]["content"])["status"] == "validated_draft"
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(
            type="text", text="Your interactive sales planner is ready.")])

    monkeypatch.setattr(agent, "client", SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create))))
    result = asyncio.run(agent.run_app(project, "Build a sales scenario"))
    assert result["app"]["views"] == app_spec["views"]
    assert len(calls) == 2 and project.app_touched
    project.save_app.assert_called_once()
    assert project.messages is old_messages and project.sub_client is old_client
    old_client.disconnect.assert_not_called()
    assert project.new_charts == [{"id": 9}] and project.app_build_draft is None


@pytest.mark.parametrize("backend", ["api", "subscription"])
def test_direct_json_reply_and_chat_state_restoration(monkeypatch, project, app_spec, backend):
    monkeypatch.setattr(agent, "AI_BACKEND", backend)
    old_client = project.sub_client
    build_client = SimpleNamespace(disconnect=AsyncMock())

    def respond(proj, prompt):
        assert not proj.messages and proj.sub_client is None
        if backend == "subscription":
            proj.sub_client = build_client
        return {"reply": "```json\n" + json.dumps(app_spec) + "\n```"}

    async def respond_async(proj, prompt):
        return respond(proj, prompt)

    monkeypatch.setattr(agent, "run_agent_api", respond)
    monkeypatch.setattr(agent, "run_agent_subscription", respond_async)
    assert asyncio.run(agent.run_app(project))["app"]["views"] == app_spec["views"]
    assert project.sub_client is old_client
    project.save_app.assert_called_once()
    if backend == "subscription":
        build_client.disconnect.assert_awaited_once()


@pytest.mark.parametrize("reply", ["Ready.", "{broken json}", '{"views": []}'])
@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_invalid_output_gets_one_repair_without_reusing_saved_app(monkeypatch, project, app_spec, reply, repair_succeeds):
    old_app = project.app

    def respond(proj, prompt):
        proj.save_app.assert_not_called()
        assert proj.app is old_app
        if run.call_count == 2 and repair_succeeds:
            submit(proj, app_spec)
        return {"reply": reply}

    run = Mock(side_effect=respond)
    monkeypatch.setattr(agent, "run_agent_api", run)
    if repair_succeeds:
        assert asyncio.run(agent.run_app(project))["app"]["views"] == app_spec["views"]
        project.save_app.assert_called_once()
    else:
        with pytest.raises(RuntimeError, match=T(project.lang, "err_app_invalid")):
            asyncio.run(agent.run_app(project))
        project.save_app.assert_not_called()
        assert project.app is old_app and not project.app_touched
    assert run.call_count == 2
    assert ("info", T(project.lang, "act_app_repairing")) in project.activity
    assert project.app_build_draft is None


@pytest.mark.parametrize("failure", ["cancel", "provider"])
def test_interrupted_build_does_not_save_valid_draft(monkeypatch, project, app_spec, failure):
    project.job_id = "qa-job"
    old_app, old_messages = project.app, project.messages
    cancelled = False
    monkeypatch.setattr(agent.jobs, "is_cancelled", lambda job_id: cancelled)

    def respond(proj, prompt):
        nonlocal cancelled
        submit(proj, app_spec)
        if failure == "provider":
            raise RuntimeError("Synthetic provider failure")
        cancelled = True
        return {"reply": "Ready"}

    monkeypatch.setattr(agent, "run_agent_api", respond)
    with pytest.raises(agent.CancelledByUser if failure == "cancel" else RuntimeError):
        asyncio.run(agent.run_app(project))
    project.save_app.assert_not_called()
    assert project.app is old_app and project.messages is old_messages
    assert project.app_build_draft is None and not project.app_touched


def test_build_cannot_change_dashboard_or_saved_context(project):
    project.app_build_draft = {}
    for name in ("create_chart", "record_data_context", "define_view", "present_questions"):
        _, error = agent.execute_tool(project, name, {})
        assert error
    assert project.notes == [] and project.dashboard == []


def test_app_chat_still_saves_immediately(project, app_spec):
    project.chat_scope = "app"
    assert submit(project, app_spec)["ok"]
    project.save_app.assert_called_once()
    assert project.app_touched and project.app["views"] == app_spec["views"]


def test_build_prompts_do_not_inherit_interview_rules(monkeypatch, project):
    project.app_build_draft = {}
    monkeypatch.setattr(agent, "ClaudeAgentOptions", lambda **kw: SimpleNamespace(**kw))
    options = agent.sub_options(project)
    assert options.system_prompt == agent.build_system_prompt(project)
    assert set(options.allowed_tools) == {"mcp__analytics__" + name for name in agent.APP_BUILD_TOOLS}
    assert "already complete" in options.system_prompt


@pytest.mark.parametrize("key", ["act_app_thinking", "act_app_designing", "act_app_ready", "act_app_repairing", "err_app_invalid"])
def test_app_build_messages_have_both_languages(key):
    assert key in MSG["bg"] and key in MSG["en"]
    assert MSG["bg"][key] != MSG["en"][key]
