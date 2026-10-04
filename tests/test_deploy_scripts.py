import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import deploy_agent_engine as dep  # noqa: E402
import query_agent_engine as qry  # noqa: E402


def test_runtime_env_only_carries_app_settings(monkeypatch):
    monkeypatch.delenv("BQ_DATASET", raising=False)
    env = dep.runtime_env({"BQ_DATASET": "cp", "GOOGLE_CLOUD_PROJECT": "p", "GOOGLE_API_KEY": "secret",
                           "APPROVER_EMAILS": "a@x.com", "APP_INTEGRATION_NAME": "wf"})
    assert env == {"BQ_DATASET": "cp", "APP_INTEGRATION_NAME": "wf"}  # no secrets, no project, no setup-only keys


def test_config_and_command():
    cfg = dep.build_config({"BQ_DATASET": "cp"}, "sa@p.iam.gserviceaccount.com")
    assert cfg["env_vars"] == {"BQ_DATASET": "cp"} and cfg["service_account"].startswith("sa@")
    cmd = dep.deploy_command("p", "us-central1", "/tmp/c.json", Path("/x/campaign_provisioner"), "123")
    assert cmd[:3] == ["adk", "deploy", "agent_engine"] and "--agent_engine_id=123" in cmd
    assert cmd[-1].endswith("campaign_provisioner") and "--project=p" in cmd


def test_resource_name_is_found_in_deploy_output():
    out = "Created a new instance: projects/123/locations/us-central1/reasoningEngines/987654\nDeployed to Agent Platform"
    assert dep.RESOURCE_RE.findall(out)[-1] == "projects/123/locations/us-central1/reasoningEngines/987654"


def test_confirmation_request_is_parsed_in_both_key_styles():
    ev = {"content": {"role": "model", "parts": [{"function_call": {
        "id": "adk-1", "name": "adk_request_confirmation",
        "args": {"originalFunctionCall": {"name": "approve_budget", "args": {"amount": 18000}},
                 "toolConfirmation": {"hint": "please confirm"}}}}]}}
    texts, conf = qry.parse_event(ev)
    assert texts == [] and conf == [{"id": "adk-1", "tool": "approve_budget", "args": {"amount": 18000},
                                     "hint": "please confirm"}]
    camel = {"content": {"parts": [{"functionCall": {"id": "2", "name": "adk_request_confirmation", "args": {}}}]}}
    assert qry.parse_event(camel)[1][0]["id"] == "2"
    assert qry.parse_event({"content": {"role": "model", "parts": [{"text": "hello"}]}})[0] == ["hello"]


def test_confirmation_reply_shape():
    r = qry.confirmation_reply("adk-1", True)
    fr = r["parts"][0]["function_response"]
    assert r["role"] == "user" and fr == {"id": "adk-1", "name": "adk_request_confirmation", "response": {"confirmed": True}}


def test_converse_asks_the_human_and_sends_the_answer(monkeypatch):
    import asyncio

    class Remote:
        def __init__(self):
            self.sent = []

        async def async_stream_query(self, *, user_id, session_id, message):
            self.sent.append(message)
            if len(self.sent) == 1:
                yield {"content": {"role": "model", "parts": [{"function_call": {
                    "id": "c1", "name": "adk_request_confirmation",
                    "args": {"originalFunctionCall": {"name": "approve_budget", "args": {"amount": 18000}}}}}]}}
            else:
                yield {"content": {"role": "model", "parts": [{"text": "Approved and ordered."}]}}

    monkeypatch.setattr(qry, "ask_human", lambda req: True)
    remote = Remote()
    asyncio.run(qry.converse(remote, "u", "s", "need a wall"))
    assert remote.sent[0] == "need a wall"
    assert remote.sent[1]["parts"][0]["function_response"]["response"] == {"confirmed": True}
