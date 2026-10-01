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
