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


class _Proc:
    def __init__(self, code=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def test_grant_roles_ok_and_member(monkeypatch):
    calls = []

    def fake_run(cmd, **k):
        calls.append(cmd)
        return _Proc(0, "123456\n")
    monkeypatch.setattr(dep.subprocess, "run", fake_run)
    member = dep.runtime_member("p", None)
    assert member == "serviceAccount:service-123456@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
    assert dep.runtime_member("p", "sa@p.iam.gserviceaccount.com") == "serviceAccount:sa@p.iam.gserviceaccount.com"
    assert dep.grant_runtime_roles("p", member) == "ok"
    bound = [c[-3].split("=")[1] for c in calls if "add-iam-policy-binding" in c]
    assert bound == dep.RUNTIME_ROLES


def test_grant_roles_reports_problems_instead_of_raising(monkeypatch, capsys):
    monkeypatch.setattr(dep.subprocess, "run",
                        lambda cmd, **k: _Proc(1, "", "ERROR: Service account service-1@x does not exist."))
    assert dep.grant_runtime_roles("p", "serviceAccount:service-1@x") == "missing_identity"
    monkeypatch.setattr(dep.subprocess, "run",
                        lambda cmd, **k: _Proc(1, "", "PERMISSION_DENIED: caller does not have permission"))
    assert dep.grant_runtime_roles("p", "serviceAccount:service-1@x") == "denied"
    out = capsys.readouterr().out
    assert "does not exist yet" in out and "Ask an admin to grant" in out
    assert dep.grant_runtime_roles("p", None) == "error"


def test_env_setup_script_is_valid_bash_and_refuses_to_run_unsourced():
    import subprocess
    script = str(Path(__file__).resolve().parent.parent / "scripts" / "env_setup.sh")
    assert subprocess.run(["bash", "-n", script]).returncode == 0
    r = subprocess.run(["bash", script], capture_output=True, text=True)
    assert r.returncode == 1 and "source scripts/env_setup.sh" in r.stdout


def test_integration_tools_are_built_lazily_and_fail_soft(monkeypatch):
    import asyncio
    from campaign_provisioner import config
    from campaign_provisioner.workflow import integration as wi

    monkeypatch.setattr(config, "WORKFLOW_BACKEND", "app_integration")
    monkeypatch.setattr(config, "PROJECT", "")  # no project: building would fail, importing must not
    tool = wi.build_po_tool()  # nothing built, no network
    assert isinstance(tool, wi.LazyIntegrationToolset)
    tools = asyncio.run(tool.get_tools())  # building fails -> a stub tool, not an exception
    assert [t.name for t in tools] == ["create_purchase_order_unavailable"]
    assert "could not be loaded" in wi.create_purchase_order_unavailable("R", "S", 1, "V")["error"]
    assert [t.name for t in asyncio.run(wi.build_notify_tool().get_tools())] == ["notify_approver_unavailable"]


def test_log_filter_targets_the_deployment():
    import agent_engine_logs as logs
    f = logs.build_filter("projects/1/locations/us-central1/reasoningEngines/987", errors_only=True)
    assert 'reasoning_engine_id="987"' in f and "severity>=ERROR" in f
