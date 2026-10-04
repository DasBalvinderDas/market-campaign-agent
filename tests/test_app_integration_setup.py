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
    assert [t["triggerId"] for t in v["triggerConfigs"]] == [sai.PO_TRIGGER, sai.NOTIFY_TRIGGER]
    for t in v["triggerConfigs"]:
        assert {s["taskId"] for s in t["startTasks"]} <= task_ids
        assert set(t["inputVariables"]["names"]) | set(t["outputVariables"]["names"]) <= declared
        assert t["properties"]["Trigger name"] == t["triggerId"].split("/", 1)[1]
    # the contract the agent's guard relies on
    assert {"request_id", "sku", "quantity", "vendor_id", "total_amount", "campaign_id"} <= declared
    assert {"po_number", "execution_id", "status"} <= declared


def test_mapping_config_is_valid_json_and_sets_outputs():
    v = sai.build_version()
    cfg = json.loads(v["taskConfigs"][0]["parameters"]["FieldMappingConfigTaskParameterKey"]["value"]["jsonValue"])
    assert cfg["@type"].endswith("FieldMappingConfig")
    assert [m["outputField"]["referenceKey"] for m in cfg["mappedFields"]] == ["$po_number$", "$execution_id$"]


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
        trig = [{"triggerId": sai.PO_TRIGGER}, {"triggerId": sai.NOTIFY_TRIGGER}] if self.published else []
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


def test_test_flag_executes_both_triggers():
    h = FakeHttp(existing=True)
    sai.run_with(h, args(test=True), "p")
    assert len([c for c in h.calls if c[1].endswith(":execute")]) == 2


def test_notify_trigger_sends_one_email_using_only_trigger_inputs():
    v = sai.build_version()
    tasks = {t["taskId"]: t for t in v["taskConfigs"]}
    email = tasks["2"]
    assert email["task"] == "EmailTask"
    p = email["parameters"]
    assert p["To"]["value"]["stringArray"]["stringValues"] == ["$approver_email$"]
    assert p["Subject"]["value"]["stringValue"] == "$email_subject$" and p["TextBody"]["value"]["stringValue"] == "$email_body$"
    # only trigger INPUT variables are referenced (the pattern in Google's published email sample)
    declared = {x["key"]: x for x in v["integrationParameters"]}
    for ref in ("approver_email", "email_subject", "email_body"):
        assert declared[ref]["inputOutputType"] == "IN" and declared[ref]["dataType"] == "STRING_VALUE"
    assert [n["taskId"] for n in email["nextTasks"]] == ["3"]
    assert [t["startTasks"][0]["taskId"] for t in v["triggerConfigs"]] == ["1", "2"]
    assert not any(k in declared for k in ("recipient_list", "approver_emails"))


def test_no_email_variant_has_no_email_task():
    assert all(t["task"] != "EmailTask" for t in sai.build_version(email=False)["taskConfigs"])
