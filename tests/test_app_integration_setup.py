import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import setup_application_integration as sai  # noqa: E402


def test_version_definition_is_consistent():
    v = sai.build_version()
    task_ids = {t["taskId"] for t in v["taskConfigs"]}
    declared = {p["key"] for p in v["integrationParameters"]}
    assert [t["triggerId"] for t in v["triggerConfigs"]] == [sai.PO_TRIGGER, sai.TRANSFER_TRIGGER, sai.APPROVAL_TRIGGER, sai.UPDATE_TRIGGER]
    for t in v["triggerConfigs"]:
        assert {s["taskId"] for s in t["startTasks"]} <= task_ids
        assert set(t["inputVariables"]["names"]) | set(t["outputVariables"]["names"]) <= declared
        assert t["properties"]["Trigger name"] == t["triggerId"].split("/", 1)[1]
    # the contract the agent's code relies on (execution.py, decision_flow.py)
    assert {"request_id", "plan_line_id", "sku", "quantity", "vendor_id", "total_amount", "destination_region",
            "depot_id", "launch_id", "recipient_email", "email_subject", "email_body"} <= declared
    assert {"po_number", "transfer_number", "execution_id", "status", "decision", "approval_message"} <= declared


def test_mapping_configs_are_valid_json_and_set_the_outputs():
    v = sai.build_version()
    tasks = {t["taskId"]: t for t in v["taskConfigs"]}
    for tid, outputs, prefix in (("1", ["$po_number$", "$execution_id$"], "PO-"), ("4", ["$transfer_number$", "$execution_id$"], "TR-")):
        cfg = json.loads(tasks[tid]["parameters"]["FieldMappingConfigTaskParameterKey"]["value"]["jsonValue"])
        assert cfg["@type"].endswith("FieldMappingConfig")
        assert [m["outputField"]["referenceKey"] for m in cfg["mappedFields"]] == outputs
        first = cfg["mappedFields"][0]["inputField"]["transformExpression"]
        assert first["initialValue"]["literalValue"]["stringValue"] == prefix
        assert first["transformationFunctions"][0]["parameters"][0]["initialValue"]["referenceValue"] == "$plan_line_id$"


class Resp:
    def __init__(self, code=200, body=None, text=""):
        self.status_code, self._b, self.text = code, body or {}, text or json.dumps(body or {})
    def json(self): return self._b


class FakeHttp:
    def __init__(self, existing=False):
        self.existing, self.calls, self.published = existing, [], existing

    def get(self, url):
        self.calls.append(("GET", url, None))
        if not self.existing:
            return Resp(404)
        trig = [{"triggerId": t} for t in (sai.PO_TRIGGER, sai.TRANSFER_TRIGGER, sai.APPROVAL_TRIGGER, sai.UPDATE_TRIGGER)] if self.published else []
        return Resp(200, {"integrationVersions": [{"state": "ACTIVE" if self.published else "DRAFT", "triggerConfigs": trig}]})

    def post(self, url, json=None, params=None):
        self.calls.append(("POST", url, params))
        if url.endswith("/versions"):
            self.existing = True
            return Resp(200, {"name": "projects/p/locations/l/integrations/i/versions/v1"})
        if url.endswith(":publish"):
            self.published = True
            return Resp(200, {})
        if url.endswith(":execute"):
            return Resp(200, {"executionFailed": False, "outputParameters": {"po_number": "PO-X"}})
        return Resp(200, {})


def args(**kw):
    return types.SimpleNamespace(**{"test": False, "check_only": False, "provision_region": False, "no_email": False, "test_email": "me@example.com", **kw})


def test_creates_and_publishes_when_missing():
    h = FakeHttp(existing=False)
    sai.run_with(h, args(), "p")
    posts = [(u.split("/")[-1], p) for m, u, p in h.calls if m == "POST"]
    assert posts[0] == ("versions", {"newIntegration": "true"}) and posts[1][0].endswith(":publish")


def test_idempotent_when_already_published():
    h = FakeHttp(existing=True)
    sai.run_with(h, args(), "p")
    assert not [c for c in h.calls if c[0] == "POST"]


def test_check_only_does_not_create():
    with pytest.raises(SystemExit) as e:
        sai.run_with(FakeHttp(existing=False), args(check_only=True), "p")
    assert "Not set up yet" in str(e.value)


def test_api_disabled_names_the_api():
    class Disabled(FakeHttp):
        def get(self, url):
            return Resp(403, text="SERVICE_DISABLED: Application Integration API has not been used in project 1 "
                                  "https://console.developers.google.com/apis/api/integrations.googleapis.com/overview")
    with pytest.raises(SystemExit) as e:
        sai.run_with(Disabled(), args(), "p")
    assert "gcloud services enable integrations.googleapis.com" in str(e.value)


def test_test_flag_executes_the_order_triggers_and_the_update():
    h = FakeHttp(existing=True)
    sai.run_with(h, args(test=True), "p")
    assert len([c for c in h.calls if c[1].endswith(":execute")]) == 3          # PO, transfer, update email


def test_update_trigger_sends_one_email_using_only_trigger_inputs():
    v = sai.build_version()
    tasks = {t["taskId"]: t for t in v["taskConfigs"]}
    email = tasks["2"]
    assert email["task"] == "EmailTask"
    p = email["parameters"]
    assert p["To"]["value"]["stringArray"]["stringValues"] == ["$recipient_email$"]
    assert p["Subject"]["value"]["stringValue"] == "$email_subject$" and p["TextBody"]["value"]["stringValue"] == "$email_body$"
    # only trigger INPUT variables are referenced (the pattern in Google's published email sample)
    declared = {x["key"]: x for x in v["integrationParameters"]}
    for ref in ("recipient_email", "email_subject", "email_body"):
        assert declared[ref]["inputOutputType"] == "IN" and declared[ref]["dataType"] == "STRING_VALUE"
    assert [n["taskId"] for n in email["nextTasks"]] == ["3"]
    assert [t["startTasks"][0]["taskId"] for t in v["triggerConfigs"]] == ["1", "4", "10", "2"]
    assert not any(k in declared for k in ("recipient_list", "approver_emails", "approver_email"))


def test_no_email_variant_has_no_email_task():
    assert all(t["task"] != "EmailTask" for t in sai.build_version(email=False)["taskConfigs"])


def test_native_approval_task_branches_on_the_decision():
    v = sai.build_version(approver_emails=["a@x.com", "b@x.com"])
    tasks = {t["taskId"]: t for t in v["taskConfigs"]}
    a = tasks["10"]
    assert a["task"] == "SuspensionTask" and a["successPolicy"] == {"finalState": "SUSPENDED"}
    notes = json.loads(a["parameters"]["notifications"]["value"]["jsonValue"])["protoValues"]
    assert [n["emailAddress"]["email"] for n in notes] == ["a@x.com", "b@x.com"]
    assert a["parameters"]["customMessage"]["value"]["stringValue"] == "$approval_message$"
    assert {n["taskId"]: n["condition"] for n in a["nextTasks"]} == {
        "11": "$`Task_10_isApproved`$ = true", "12": "$`Task_10_isApproved`$ = false"}
    outs = {}
    for tid in ("11", "12"):
        cfg = json.loads(tasks[tid]["parameters"]["FieldMappingConfigTaskParameterKey"]["value"]["jsonValue"])
        outs[tid] = cfg["mappedFields"][0]["inputField"]["transformExpression"]["initialValue"]["literalValue"]["stringValue"]
    assert outs == {"11": "APPROVED", "12": "REJECTED"}


def test_approver_addresses_are_taken_from_role_specs():
    got = sai.approver_addresses(["VP Product Marketing=md@x.com,md2@x.com", "CMO=vp@x.com;md@x.com"])
    assert got == ["md@x.com", "md2@x.com", "vp@x.com"]


def test_update_email_is_html_by_default_and_text_on_request():
    def fmt(v):
        task = next(t for t in v["taskConfigs"] if t["task"] == "EmailTask")
        return task["parameters"]["BodyFormat"]["value"]["stringValue"]
    assert fmt(sai.build_version()) == "html"
    assert fmt(sai.build_version(email_format="text")) == "text"
