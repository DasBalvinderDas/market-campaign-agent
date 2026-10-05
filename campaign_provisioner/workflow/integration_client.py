"""Run an Application Integration API trigger directly (REST), outside the ADK tool loop.

Used where code, not the model, must start a workflow: sending the approval email with its links, and creating the
purchase orders after an approver clicked a link. Authenticates as whoever the process runs as (the service account).
"""
from .. import config


class IntegrationError(RuntimeError):
    pass


def _typed(value):
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": "" if value is None else str(value)}


class IntegrationExecutor:
    def _session(self):
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        if not config.PROJECT:
            raise IntegrationError("GOOGLE_CLOUD_PROJECT is not set")
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        return AuthorizedSession(creds)

    @staticmethod
    def _base():
        return (f"https://integrations.googleapis.com/v1/projects/{config.PROJECT}/locations/"
                f"{config.APP_INTEGRATION_LOCATION}/integrations/{config.APP_INTEGRATION_NAME}")

    def start(self, trigger_id: str, inputs: dict) -> dict:
        """Run a trigger and return the whole response (executionId, outputParameters, executionFailed)."""
        resp = self._session().post(
            f"{self._base()}:execute",
            json={"triggerId": trigger_id, "inputParameters": {k: _typed(v) for k, v in inputs.items()}}, timeout=90)
        if resp.status_code != 200:
            raise IntegrationError(f"Application Integration returned HTTP {resp.status_code}: {resp.text[:300]}")
        body = resp.json()
        if body.get("executionFailed"):
            raise IntegrationError(f"the workflow {trigger_id} failed: {str(body)[:300]}")
        return body

    def execute(self, trigger_id: str, inputs: dict) -> dict:
        return self.start(trigger_id, inputs).get("outputParameters") or {}

    def list_suspensions(self, execution_id: str) -> list:
        """Approval (suspension) records of an execution: state PENDING / LIFTED / REJECTED."""
        resp = self._session().get(f"{self._base()}/executions/{execution_id}/suspensions", timeout=60)
        if resp.status_code != 200:
            raise IntegrationError(f"Application Integration returned HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json().get("suspensions", [])

    def get_execution(self, execution_id: str) -> dict:
        """State and response parameters of a (possibly suspended) execution."""
        resp = self._session().get(f"{self._base()}/executions/{execution_id}", timeout=60)
        if resp.status_code != 200:
            raise IntegrationError(f"Application Integration returned HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()
