#!/usr/bin/env python3
"""Show the recent logs of the deployed agent (Vertex AI Agent Engine), to see why a request failed.

  python scripts/agent_engine_logs.py              # last 40 entries of the deployment saved in .env
  python scripts/agent_engine_logs.py --limit 100 --errors-only

Needs AGENT_ENGINE_RESOURCE (written to .env by deploy_agent_engine.py) or --resource. Uses `gcloud logging read`.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import resolve_project  # noqa: E402


def engine_id(resource: str) -> str:
    return resource.rstrip("/").split("/")[-1]


def build_filter(resource: str, errors_only: bool = False) -> str:
    f = ('resource.type="aiplatform.googleapis.com/ReasoningEngine" '
         f'AND resource.labels.reasoning_engine_id="{engine_id(resource)}"')
    return f + (" AND severity>=ERROR" if errors_only else "")


def read_resource(explicit=None):
    resource = explicit or os.getenv("AGENT_ENGINE_RESOURCE")
    env = ROOT / ".env"
    if not resource and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("AGENT_ENGINE_RESOURCE="):
                resource = line.split("=", 1)[1].strip()
    return resource


KEY_WORDS = ("error", "exception", "forbidden", "denied", "permission", "not found", "unavailable", "running as")


def key_lines(lines: list[str]) -> str:
    """The lines that explain a failure (exception messages), without the stack-trace noise; duplicates removed."""
    seen, out = set(), []
    for ln in lines:
        low = ln.lower()
        text = ln.strip()
        if text.startswith(("File ", "^", "raise ", "return ", "await ", "response", "result", "spec")) or text.endswith("^"):
            continue
        if any(k in low for k in KEY_WORDS):
            core = text.split("\t")[-1] if "\t" in text else text
            if core not in seen:
                seen.add(core)
                out.append(text)
    return "\n".join(out) if out else "\n".join(lines[-15:])


def recent_logs(project: str, resource: str, limit: int = 40, errors_only: bool = False, full: bool = False) -> str:
    cmd = ["gcloud", "logging", "read", build_filter(resource, errors_only), f"--project={project}",
           f"--limit={limit}", "--freshness=1d", "--order=desc",
           "--format=value(timestamp,severity,textPayload,jsonPayload.message,jsonPayload.error)"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return f"(could not read the logs: {r.stderr.strip()[:300]})"
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    if not lines:
        return "(no log entries found for this deployment yet)"
    lines.reverse()
    if full:
        return "\n".join(lines)
    return key_lines(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    ap.add_argument("--resource", default=None)
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--errors-only", action="store_true")
    ap.add_argument("--full", action="store_true", help="show every log line instead of the key lines")
    args = ap.parse_args()
    resource = read_resource(args.resource)
    if not resource:
        sys.exit("No deployed agent known. Run scripts/deploy_agent_engine.py first, or pass --resource.")
    print(recent_logs(resolve_project(args.project), resource, args.limit, args.errors_only, args.full))


if __name__ == "__main__":
    main()
