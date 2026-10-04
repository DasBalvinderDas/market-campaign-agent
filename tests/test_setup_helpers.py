import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from _common import explain, guarded  # noqa: E402

BQ_DISABLED = ("403 BigQuery API has not been used in project 123456 before or it is disabled. Enable it by "
               "visiting https://console.developers.google.com/apis/api/bigquery.googleapis.com/overview?project=123456")
INT_DISABLED = "SERVICE_DISABLED: Application Integration API has not been used... integrations.googleapis.com"


def test_disabled_api_names_the_api_to_enable():
    hint = explain(BQ_DISABLED, "my-proj")
    assert "gcloud services enable bigquery.googleapis.com --project my-proj" in hint
    assert "console.developers" not in hint
    assert "integrations.googleapis.com" in explain(INT_DISABLED, "my-proj")


def test_permission_and_credential_hints():
    assert "roles/bigquery.dataEditor" in explain("403 Access Denied: User does not have bigquery.datasets.create permission", "p")
    assert "application-default login" in explain("Your default credentials were not found", "p")
    assert explain("some unrelated failure", "p") is None


def test_guarded_exits_with_message_not_traceback():
    @guarded
    def boom(project=""):
        raise RuntimeError(BQ_DISABLED)

    with pytest.raises(SystemExit) as e:
        boom(project="my-proj")
    assert "enable" in str(e.value).lower()


def test_guarded_reraises_unknown_errors():
    @guarded
    def boom(project=""):
        raise ValueError("bug")

    with pytest.raises(ValueError):
        boom(project="p")


def test_write_env_updates_and_preserves(tmp_path):
    import setup_all
    f = tmp_path / ".env"
    f.write_text("# comment\nGOOGLE_CLOUD_PROJECT=old\nGOOGLE_API_KEY=keep-me\n# DATA_BACKEND=memory\n")
    setup_all.ROOT = tmp_path  # no .env.example there
    setup_all.write_env(f, {"GOOGLE_CLOUD_PROJECT": "new", "DATA_BACKEND": "bigquery", "APPROVER_EMAILS": "a@x.com"})
    text = f.read_text()
    assert "GOOGLE_CLOUD_PROJECT=new" in text and "GOOGLE_API_KEY=keep-me" in text
    assert "DATA_BACKEND=bigquery" in text and "APPROVER_EMAILS=a@x.com" in text and "old" not in text


def test_preflight_reports_all_problems_at_once():
    import _common

    class R:
        def __init__(self, code, body): self.status_code, self._b = code, body
        def json(self): return self._b

    class Http:
        def get(self, url, timeout=0):
            return R(200, {"state": "DISABLED"}) if "integrations" in url or "bigquery" in url else R(200, {"state": "ENABLED"})
        def post(self, url, json=None, timeout=0): return R(200, {"permissions": []})

    import google.auth, google.auth.transport.requests as tr
    orig = (google.auth.default, tr.AuthorizedSession)
    google.auth.default = lambda scopes=None: (None, "p")
    tr.AuthorizedSession = lambda creds: Http()
    try:
        with pytest.raises(SystemExit) as e:
            _common.preflight("my-proj", ["bigquery.googleapis.com", "integrations.googleapis.com"])
    finally:
        google.auth.default, tr.AuthorizedSession = orig
    msg = str(e.value)
    assert "gcloud services enable bigquery.googleapis.com integrations.googleapis.com --project my-proj" in msg


def test_setup_all_runs_both_steps_and_writes_env(tmp_path, monkeypatch):
    import setup_all, setup_application_integration as ai, setup_bigquery as bq
    calls = []
    monkeypatch.setattr(setup_all, "ROOT", tmp_path)
    (tmp_path / "campaign_provisioner").mkdir()
    monkeypatch.setattr(setup_all, "preflight", lambda *a, **k: calls.append("preflight"))
    monkeypatch.setattr(bq, "run", lambda args, project="": calls.append(("bq", project, args.approver_email)))
    monkeypatch.setattr(ai, "run", lambda args, project="": calls.append(("ai", project, args.no_email)))
    monkeypatch.setattr(sys, "argv", ["setup_all.py", "--project", "p1", "--approver-email", "a@x.com"])
    setup_all.main()
    assert calls == ["preflight", ("bq", "p1", ["a@x.com"]), ("ai", "p1", False)]
    env = (tmp_path / ".env").read_text()
    assert "GOOGLE_CLOUD_PROJECT=p1" in env and "APPROVER_EMAILS=a@x.com" in env and "BACKEND" not in env


def test_setup_all_continues_after_a_failed_step_and_reports(tmp_path, monkeypatch, capsys):
    import setup_all, setup_application_integration as ai, setup_bigquery as bq
    monkeypatch.setattr(setup_all, "ROOT", tmp_path)
    monkeypatch.setattr(setup_all, "preflight", lambda *a, **k: None)

    def bq_fail(args, project=""):
        sys.exit("API not enabled: bigquery.googleapis.com")
    monkeypatch.setattr(bq, "run", bq_fail)
    monkeypatch.setattr(ai, "run", lambda args, project="": None)
    monkeypatch.setattr(sys, "argv", ["setup_all.py", "--project", "p1"])
    with pytest.raises(SystemExit) as e:
        setup_all.main()
    out = capsys.readouterr().out
    assert "API not enabled: bigquery.googleapis.com" in out and "Application Integration: OK" in out
    assert "need attention" in str(e.value) and not (tmp_path / ".env").exists()


def test_importing_the_package_does_not_build_agents_or_touch_the_cloud():
    """Regression: setup scripts import campaign_provisioner.* before the integration exists."""
    import os, subprocess
    env = {**os.environ, "WORKFLOW_BACKEND": "app_integration", "DATA_BACKEND": "bigquery"}
    env.pop("GOOGLE_CLOUD_PROJECT", None)
    code = ("import campaign_provisioner.approvers, campaign_provisioner.data.schema, "
            "campaign_provisioner.data.seed_data; import sys; "
            "assert 'campaign_provisioner.agent' not in sys.modules")
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                       cwd=str(Path(__file__).resolve().parent.parent))
    assert r.returncode == 0, r.stderr
