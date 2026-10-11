from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import db
import jobs
from bizzmind import agent, plans
from bizzmind.api_usage import record_response, response_usage


def message(model="claude-sonnet-5", **usage):
    return {"model": model, "stop_reason": "end_turn", "usage": {
        "input_tokens": 1000, "output_tokens": 100, **usage}}


def test_actual_model_and_cache_categories_are_rated_separately():
    response = message("claude-opus-5-20261001", cache_creation_input_tokens=1000,
                       cache_read_input_tokens=3000,
                       cache_creation={"ephemeral_1h_input_tokens": 400, "ephemeral_5m_input_tokens": 600})
    incoming, outgoing, cost = response_usage(response)
    assert (incoming, outgoing) == (5000, 100)
    assert cost == pytest.approx((1000*5 + 100*25 + 400*10 + 600*6.25 + 3000*.5) / 1e6)


def test_legacy_cache_usage_defaults_to_five_minutes():
    assert response_usage(message(cache_creation_input_tokens=2000))[2] == pytest.approx(.008)


def test_fallback_iterations_are_counted_once_at_each_models_rate():
    response = message("claude-opus-4-8", input_tokens=999999, output_tokens=999999,
                       iterations=[
                           dict(model="claude-opus-5", type="message", input_tokens=1000, output_tokens=20),
                           dict(model="claude-opus-4-8", type="fallback_message", input_tokens=200, output_tokens=80,
                                cache_read_input_tokens=1000),
                       ])
    assert response_usage(response) == pytest.approx((2200, 100, .009))


def test_ordinary_refusal_before_output_is_not_billed_twice():
    response = message(iterations=[
        dict(model="claude-opus-5", type="message", input_tokens=1000, output_tokens=0),
        dict(model="claude-opus-4-8", type="fallback_message", input_tokens=1000, output_tokens=100),
    ])
    assert response_usage(response) == pytest.approx((2000, 100, .0075))
    response = message(output_tokens=0)
    response["stop_reason"] = "refusal"
    assert response_usage(response)[2] == 0


@pytest.mark.parametrize("model", ["unknown-model", "claude-opus-55"])
def test_unknown_prices_cannot_silently_create_a_free_job(model):
    with pytest.raises(ValueError, match="billing rates"):
        response_usage(message(model))


def test_missing_usage_is_not_treated_as_zero():
    with pytest.raises(ValueError, match="Missing API usage"):
        response_usage({"model": "claude-opus-5"})


def test_no_job_means_no_usage_write(monkeypatch, fake_project):
    pool = Mock(side_effect=AssertionError("No database write outside a job"))
    monkeypatch.setattr(db, "pool", pool)
    record_response(fake_project(job_id=None), {})
    pool.assert_not_called()


def test_api_records_every_tool_and_pause_round_before_final_reply(monkeypatch, fake_project, fake_pool):
    pool = fake_pool()
    monkeypatch.setattr(db, "pool", lambda: pool)
    monkeypatch.setattr(agent, "describe_schema", lambda p: [])
    monkeypatch.setattr(agent, "build_system_prompt", lambda p: "QA")
    monkeypatch.setattr(jobs, "is_cancelled", lambda job_id: False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only")
    project = fake_project(job_id="qa-job", messages=[], chat=[], new_charts=[], new_questions=[])
    responses = [
        SimpleNamespace(**message(cache_creation_input_tokens=2000), content=[SimpleNamespace(
            type="tool_use", id="tool-1", name="present_questions", input={"questions": [
                {"question": "Choose", "options": ["A", "B"], "multi": False}]})]),
        SimpleNamespace(**message(input_tokens=500, output_tokens=50, cache_read_input_tokens=2000), content=[]),
        SimpleNamespace(**message(input_tokens=500, output_tokens=50, cache_read_input_tokens=2000),
                        content=[SimpleNamespace(type="text", text="Ready")]),
    ]
    responses[0].stop_reason = "tool_use"
    responses[1].stop_reason = "pause_turn"
    create = Mock(side_effect=responses)
    monkeypatch.setattr(agent, "client", SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create))))
    assert agent.run_agent_api(project, "QA")["reply"] == "Ready"
    writes = [p for sql, p in pool.log if "UPDATE public.jobs" in sql]
    assert len(writes) == 3
    assert sum(p[0] for p in writes) == 8000
    assert sum(p[1] for p in writes) == 200
    assert sum(p[2] for p in writes) == pytest.approx(.0118)
    assert all(p[3] == "qa-job" for p in writes)
    assert not pool.sql_like("credit_events")  # settlement waits for job success


def test_usage_write_failure_cannot_publish_a_free_success(monkeypatch, fake_project):
    import bizzmind.api_usage as usage
    monkeypatch.setattr(usage, "record_response", Mock(side_effect=RuntimeError("Synthetic storage failure")))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only")
    monkeypatch.setattr(agent, "build_system_prompt", lambda p: "QA")
    monkeypatch.setattr(agent.jobs, "is_cancelled", lambda id: False)
    response = SimpleNamespace(**message(), content=[SimpleNamespace(type="text", text="Ready")])
    monkeypatch.setattr(agent, "client", SimpleNamespace(beta=SimpleNamespace(
        messages=SimpleNamespace(create=Mock(return_value=response)))))
    project = fake_project(job_id="qa", messages=[], chat=[], new_charts=[], new_questions=[])
    with pytest.raises(RuntimeError) as exc:
        agent.run_agent_api(project, "QA")
    assert "storage" not in str(exc.value)


@pytest.mark.parametrize("status", ["done", "cancelled", "failed"])
def test_finished_or_stopped_jobs_cannot_be_charged_again(monkeypatch, fake_pool, status):
    pool = fake_pool(lambda sql, p: ([(status,)], 1))
    monkeypatch.setattr(db, "pool", lambda: pool)
    settle = Mock()
    assert jobs.finish("qa-job", {}, settle=settle) == (status == "done")
    settle.assert_not_called()
    assert not any(sql.startswith("UPDATE ") for sql, _ in pool.log)


def test_job_success_is_published_only_after_settlement_on_same_connection(monkeypatch, fake_pool):
    pool = fake_pool(lambda sql, p: ([("running",)], 1))
    monkeypatch.setattr(db, "pool", lambda: pool)
    pool.conn.commit = Mock()

    def settle(con):
        assert con is pool.conn
        assert not pool.sql_like("SET status = 'done'")
        con.execute("UPDATE public.organizations SET credits_used = 10 WHERE id = %s", ("qa-org",))

    assert jobs.finish("qa-job", {"reply": "Ready"}, settle=settle)
    assert "FOR UPDATE" in pool.log[0][0]
    assert "credits_used" in pool.log[1][0]
    assert "status = 'done'" in pool.log[2][0]
    pool.conn.commit.assert_called_once()


def test_settlement_failure_does_not_mark_job_done(monkeypatch, fake_pool):
    pool = fake_pool(lambda sql, p: ([("running",)], 1))
    monkeypatch.setattr(db, "pool", lambda: pool)
    with pytest.raises(RuntimeError):
        jobs.finish("qa-job", {}, settle=Mock(side_effect=RuntimeError("failed")))
    assert not pool.sql_like("UPDATE public.jobs")


def test_credit_settlement_uses_the_callers_transaction(monkeypatch, fake_pool):
    pool = fake_pool()
    monkeypatch.setattr(plans, "org_of_project", lambda pid: "qa-org")
    monkeypatch.setattr(plans, "pool", Mock(side_effect=AssertionError("Must use the job transaction")))
    took = plans.settle("qa-project", "chat", .05, connection=pool.conn)
    assert took == plans.credits_from_usd(.05)
    assert pool.sql_like("UPDATE public.organizations") and pool.sql_like("INSERT INTO public.credit_events")
