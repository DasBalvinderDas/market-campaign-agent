"""Shared helpers for the setup scripts: project resolution and friendly error messages.

The scripts assume the Google Cloud APIs are already enabled. If one is not, they stop and tell
you exactly which API to enable instead of printing a stack trace.
"""
import os
import re
import subprocess
import sys

REQUIRED_APIS = {
    "BigQuery API": "bigquery.googleapis.com",
    "Application Integration API": "integrations.googleapis.com",
    "Vertex AI API": "aiplatform.googleapis.com",
}


def resolve_project(cli_value=None) -> str:
    """--project, else GOOGLE_CLOUD_PROJECT, else the active gcloud project."""
    project = cli_value or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project:
        try:
            out = subprocess.run(["gcloud", "config", "get-value", "project"], capture_output=True,
                                 text=True, timeout=20).stdout.strip()
            project = out if out and out != "(unset)" else None
        except Exception:
            project = None
    if not project:
        sys.exit("No project id found. Run:  export GOOGLE_CLOUD_PROJECT=<your-project-id>")
    return project


def explain(message: str, project: str) -> str | None:
    """Turn a Google API error message into an actionable hint, or None if it is not a known case."""
    m = message.lower()
    if "service_disabled" in m or "has not been used in project" in m or "is disabled" in m \
            or "accessnotconfigured" in m or "api has not been enabled" in m:
        apis = [a for a in dict.fromkeys(re.findall(r"([a-z0-9-]+\.googleapis\.com)", message))]
        apis = [a for a in apis if a not in ("console.developers.google.com", "console.cloud.google.com")] \
            or ["<the API named in the error>"]
        lines = [f"A required Google Cloud API is not enabled in project '{project}'.", "Please enable:"]
        for a in apis:
            lines.append(f"  - {a}")
            lines.append(f"      gcloud services enable {a} --project {project}")
            lines.append(f"      or https://console.cloud.google.com/apis/library/{a}?project={project}")
        lines.append("Wait about a minute after enabling, then run this script again.")
        return "\n".join(lines)
    if "default credentials" in m or "could not automatically determine credentials" in m \
            or "reauthentication" in m or "invalid_grant" in m:
        return "No usable credentials. Run:  gcloud auth application-default login"
    if "quota project" in m:
        return (f"Your credentials need a quota project. Run:  "
                f"gcloud auth application-default set-quota-project {project}")
    if "permission" in m or "access denied" in m or "403" in m or "forbidden" in m:
        return (f"Your account lacks a permission in project '{project}'. Ask for these roles:\n"
                "  - BigQuery Data Editor (roles/bigquery.dataEditor) and BigQuery Job User (roles/bigquery.jobUser)\n"
                "  - Application Integration Invoker + Viewer (roles/integrations.integrationInvoker, roles/integrations.viewer)\n"
                "  - Vertex AI User (roles/aiplatform.user)\n"
                f"Original error: {message[:300]}")
    return None


def guarded(fn):
    """Run ``fn(project)`` style mains; print a friendly message for known Google API errors."""
    def wrapper(*args, project="", **kwargs):
        try:
            return fn(*args, project=project, **kwargs)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 - we want one clean message for any API failure
            hint = explain(str(exc), project)
            if hint:
                sys.exit(f"\n{hint}")
            raise
    return wrapper
