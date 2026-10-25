#!/usr/bin/env python3
"""Find out if the Gemini Enterprise workflow (the Inbox approval) can be created from a script. Safe by default: it only reads.

  python scripts/probe_workflow_api.py --inspect                  # does the API have a create method for workflow agents?
  python scripts/probe_workflow_api.py --inspect --schema Agent   # ...and what an agent looks like (fields and types)
  python scripts/probe_workflow_api.py --engine APP_ID --list     # the agents in your Gemini Enterprise app
  python scripts/probe_workflow_api.py --engine APP_ID --export "LaunchKit order approval" --out workflows/order_approval.json
  python scripts/probe_workflow_api.py --engine APP_ID --create workflows/order_approval.json            # dry run
  python scripts/probe_workflow_api.py --engine APP_ID --create workflows/order_approval.json --yes      # really create

Plan: build the workflow once in the console (docs/GEMINI_INBOX_WORKFLOW.md), --export it, then --create can rebuild it
anywhere. The Discovery Engine API for agents is v1alpha, so names can change: --inspect reads the live API description.
APP_ID is the id of your Gemini Enterprise app (Gemini Enterprise > Apps, the "ID" column). Location: --location (default global).
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import guarded, resolve_project  # noqa: E402

OUTPUT_ONLY = ("name", "createTime", "updateTime", "state", "revisionId", "currentRevision", "publishedRevision")


def host(location: str) -> str:
    return "discoveryengine.googleapis.com" if location in ("", "global") else f"{location}-discoveryengine.googleapis.com"


def agents_path(project: str, location: str, engine: str) -> str:
    return (f"v1alpha/projects/{project}/locations/{location}/collections/default_collection/engines/{engine}"
            "/assistants/default_assistant/agents")


def find_resource(doc: dict, name: str = "agents") -> dict | None:
    """The resource called `name` anywhere in a discovery document (resources nest inside resources)."""
    def walk(resources):
        for key, res in (resources or {}).items():
            if key == name:
                return res
            hit = walk(res.get("resources"))
            if hit:
                return hit
        return None
    return walk(doc.get("resources"))


def workflow_schemas(doc: dict) -> dict:
    """Schemas whose name mentions workflow: {name: [top level properties]}."""
    return {n: sorted((s.get("properties") or {}).keys()) for n, s in (doc.get("schemas") or {}).items() if "workflow" in n.lower()}


def verdict(doc: dict) -> tuple[bool, list[str]]:
    res = find_resource(doc, "agents")
    if not res:
        return False, ["No 'agents' resource in this API version. A script cannot create the workflow."]
    methods = sorted((res.get("methods") or {}).keys())
    schemas = workflow_schemas(doc)
    lines = [f"agents methods: {', '.join(methods) or 'none'}"]
    lines += [f"workflow schema: {n}: {', '.join(p) or '-'}" for n, p in schemas.items()] or ["no schema mentions 'workflow'"]
    ok = "create" in methods
    lines.append("RESULT: " + ("agents.create exists, so a script can probably create it. Next: --export a workflow you built, then --create."
                               if ok else "no create method for agents: the workflow can only be built in the console."))
    return ok, lines


def fetch_discovery(http, base: str) -> dict:
    """The API description is public: read it without your sign-in first (your account may lack the quota-project permission),
    then with it."""
    import requests
    url = f"{base}/$discovery/rest?version=v1alpha"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return _show(http.get(url))


def schema_lines(doc: dict, needle: str) -> list[str]:
    """Schemas whose name contains `needle` (case-insensitive) with every property and its type."""
    out = []
    for name, s in (doc.get("schemas") or {}).items():
        if needle.lower() in name.lower():
            out.append(name)
            for prop, spec in sorted((s.get("properties") or {}).items()):
                kind = spec.get("$ref") or spec.get("type") or "?"
                out.append(f"    {prop}: {kind}" + (f"  ({spec['description'][:70]})" if spec.get("description") else ""))
    return out or [f"no schema name contains '{needle}'"]


def clean_for_create(agent: dict) -> dict:
    return {k: v for k, v in agent.items() if k not in OUTPUT_ONLY}


def _session():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return AuthorizedSession(creds)


def _show(resp) -> dict:
    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text[:500]}
    if resp.status_code >= 300:
        sys.exit(f"HTTP {resp.status_code}: {json.dumps(body)[:1200]}")
    return body


@guarded
def run(args, project=""):
    http = _session()
    base = f"https://{host(args.location)}"
    did = False
    if args.inspect:
        did = True
        doc = fetch_discovery(http, base)
        for line in verdict(doc)[1]:
            print(line)
        if args.schema:
            print("\n".join(schema_lines(doc, args.schema)))
    if args.engine and (args.list or args.export):
        path = agents_path(project, args.location, args.engine)
        agents = _show(http.get(f"{base}/{path}")).get("agents", [])
        if args.list:
            did = True
            for a in agents:
                print(f"- {a.get('displayName', '?')}  [{a.get('state', '?')}]  {a.get('name', '')}")
            if not agents:
                print("No agents returned. (The list may show only workflow agents, or none exist yet.)")
        if args.export:
            did = True
            hit = next((a for a in agents if args.export in (a.get("displayName"), a.get("name", "").rsplit("/", 1)[-1])), None)
            if not hit:
                sys.exit(f"No agent called '{args.export}'. Run --list to see the names.")
            full = _show(http.get(f"{base}/v1alpha/{hit['name']}"))
            out = Path(args.out or "workflow_export.json")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(full, indent=2))
            print(f"Saved {out}. Check it before you share it: it may hold ids from your project.")
    if args.create:
        did = True
        if not args.engine:
            sys.exit("--create needs --engine APP_ID.")
        body = clean_for_create(json.loads(Path(args.create).read_text()))
        url = f"{base}/{agents_path(project, args.location, args.engine)}"
        if not args.yes:
            print(f"DRY RUN. Would POST to {url}\n{json.dumps(body, indent=2)[:1500]}\nAdd --yes to create it.")
        else:
            print(json.dumps(_show(http.post(url, json=body)), indent=2)[:2000])
    if not did:
        print(__doc__)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    ap.add_argument("--location", default=os.getenv("GE_LOCATION", "global"))
    ap.add_argument("--engine", default=os.getenv("GE_ENGINE_ID"), help="the Gemini Enterprise app id")
    ap.add_argument("--inspect", action="store_true", help="check the API description for a create method")
    ap.add_argument("--schema", metavar="NAME", help="with --inspect: print the schemas whose name contains NAME (for example Agent)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--export", metavar="NAME", help="save one agent's definition as JSON")
    ap.add_argument("--out", metavar="FILE")
    ap.add_argument("--create", metavar="FILE", help="create an agent from a saved JSON (dry run unless --yes)")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    run(a, project=resolve_project(a.project))
