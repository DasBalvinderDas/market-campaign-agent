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
        if "describe" in cmd and "roles" in cmd:
            return _Proc(1, "", "denied")
        if "get-iam-policy" in cmd:
            return _Proc(1, "", "no access")  # policy unreadable -> just try to grant everything
        return _Proc(0, "123456\n")
    monkeypatch.setattr(dep.subprocess, "run", fake_run)
    member = dep.runtime_member("p", None)
    assert member == "serviceAccount:service-123456@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
    assert dep.runtime_member("p", "sa@p.iam.gserviceaccount.com") == "serviceAccount:sa@p.iam.gserviceaccount.com"
    assert dep.grant_runtime_roles("p", member) == "ok"
    bound = [c[-3].split("=")[1] for c in calls if "add-iam-policy-binding" in c]
    assert bound == dep.BASE_ROLES + [dep.READ_ROLE_CANDIDATES[1]]  # lookup unavailable here -> safe fallback


def test_grant_roles_reports_problems_instead_of_raising(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(dep, "ROOT", tmp_path)
    monkeypatch.setattr(dep.subprocess, "run",
                        lambda cmd, **k: _Proc(1, "", "ERROR: Service account service-1@x does not exist."))
    assert dep.grant_runtime_roles("p", "serviceAccount:service-1@x") == "missing_identity"
    monkeypatch.setattr(dep.subprocess, "run",
                        lambda cmd, **k: _Proc(1, "", "PERMISSION_DENIED: caller does not have permission"))
    assert dep.grant_runtime_roles("p", "serviceAccount:service-1@x") == "denied"
    out = capsys.readouterr().out
    assert "does not exist yet" in out and "Send this file to an admin" in out
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


def test_read_role_is_chosen_by_looking_up_permissions(monkeypatch):
    perms = {"roles/integrations.integrationViewer": {"integrations.integrations.get"},
             "roles/integrations.integrationEditor": {"integrations.integrations.generateOpenApiSpec"},
             "roles/integrations.integrationAdmin": {"integrations.integrations.generateOpenApiSpec", "x"}}
    monkeypatch.setattr(dep, "role_permissions", lambda role: perms.get(role))
    assert dep.choose_runtime_roles() == dep.BASE_ROLES + ["roles/integrations.integrationEditor"]
    perms["roles/integrations.integrationViewer"] = {"integrations.integrations.generateOpenApiSpec"}
    assert dep.choose_runtime_roles() == dep.BASE_ROLES + ["roles/integrations.integrationViewer"]


def test_all_role_ids_used_exist_in_the_documented_form():
    assert "roles/integrations.viewer" not in dep.BASE_ROLES + dep.READ_ROLE_CANDIDATES
    assert all(r.startswith("roles/integrations.integration") for r in dep.READ_ROLE_CANDIDATES)


def test_log_key_lines_drop_stack_noise_and_duplicates():
    import agent_engine_logs as logs
    lines = ["2026 ERROR Traceback (most recent call last):", "  File \"/app/x.py\", line 1, in f",
             "requests.exceptions.HTTPError: 403 Client Error: Forbidden for url: https://x/generateOpenApiSpec",
             "    ^^^^^^^^", "requests.exceptions.HTTPError: 403 Client Error: Forbidden for url: https://x/generateOpenApiSpec",
             "RuntimeError: Application Integration was not found"]
    out = logs.key_lines(lines).splitlines()
    assert any("403 Client Error" in l for l in out) and len([l for l in out if "403" in l]) == 1
    assert not any("File " in l for l in out)


def test_redeploy_updates_the_saved_deployment_automatically():
    import argparse
    ns = lambda **k: argparse.Namespace(**{"update": None, "new": False, **k})  # noqa: E731
    saved = {"AGENT_ENGINE_RESOURCE": "projects/1/locations/us-central1/reasoningEngines/555"}
    assert dep.pick_update_id(ns(), saved) == "555"             # default: update what is saved
    assert dep.pick_update_id(ns(update="auto"), saved) == "555"  # `--update` with no value
    assert dep.pick_update_id(ns(update="777"), saved) == "777"
    assert dep.pick_update_id(ns(new=True), saved) is None
    assert dep.pick_update_id(ns(), {}) is None                  # nothing saved yet: create


def test_roles_already_granted_by_an_admin_are_not_a_problem(monkeypatch, capsys):
    import json as _json
    member = "serviceAccount:service-1@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
    roles = dep.BASE_ROLES + [dep.READ_ROLE_CANDIDATES[0]]
    policy = {"bindings": [{"role": r, "members": [member]} for r in roles]}

    def fake_run(cmd, **k):
        if "get-iam-policy" in cmd:
            return _Proc(0, _json.dumps(policy))
        raise AssertionError("must not try to grant anything")
    monkeypatch.setattr(dep.subprocess, "run", fake_run)
    assert dep.grant_runtime_roles("p", member, roles) == "ok"
    assert "already has all the roles" in capsys.readouterr().out


def test_denied_grant_writes_a_script_for_the_admin(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(dep, "ROOT", tmp_path)
    member = "serviceAccount:service-1@x"

    def fake_run(cmd, **k):
        if "get-iam-policy" in cmd:
            return _Proc(0, '{"bindings": []}')
        return _Proc(1, "", "PERMISSION_DENIED: Policy update access denied.")
    monkeypatch.setattr(dep.subprocess, "run", fake_run)
    assert dep.grant_runtime_roles("p", member, ["roles/a", "roles/b"]) == "denied"
    script = (tmp_path / "grant_agent_permissions.sh").read_text()
    assert script.count("add-iam-policy-binding p --member=serviceAccount:service-1@x") == 2 and "roles/b" in script
    assert "Send this file to an admin" in capsys.readouterr().out


def test_not_found_detection_for_a_deleted_deployment():
    assert dep.is_not_found("Failed to deploy: 404 NOT_FOUND. Reasoning Engine [..] is not found.")
    assert not dep.is_not_found("403 PERMISSION_DENIED")


def test_approval_service_staging_and_command(tmp_path):
    import deploy_approval_service as svc
    svc.stage(tmp_path)
    assert (tmp_path / "approval_service" / "main.py").exists() and (tmp_path / "campaign_provisioner" / "approval_flow.py").exists()
    assert "approval_service.main:app" in (tmp_path / "Procfile").read_text()
    assert "flask" in (tmp_path / "requirements.txt").read_text()
    env = svc.service_env("p", {"BQ_DATASET": "cp", "GOOGLE_API_KEY": "secret", "APPROVER_EMAILS": "a@x.com"}, "k")
    assert env == {"GOOGLE_CLOUD_PROJECT": "p", "APPROVAL_LINK_SECRET": "k", "BQ_DATASET": "cp"}  # no unrelated secrets
    assert 'APPROVAL_LINK_SECRET: "k"' in svc.env_yaml(env)
    cmd = svc.deploy_command("p", "us-central1", "/s", "/e.yaml", "app-svc@p.iam.gserviceaccount.com")
    assert "--allow-unauthenticated" in cmd and "--service-account=app-svc@p.iam.gserviceaccount.com" in cmd


def test_approval_service_failure_advice():
    import deploy_approval_service as svc
    assert "organisation" in svc.advice("ERROR: ... iam.allowedPolicyMemberDomains ...", "p", None)
    assert "Service Account User" in svc.advice("Permission 'iam.serviceaccounts.actAs' denied", "p", "sa@p")
    assert svc.advice("something else", "p", None) is None
