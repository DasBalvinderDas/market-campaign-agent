#!/usr/bin/env python3
"""Talk to the deployed agent on Vertex AI Agent Engine, including the human Confirm / Reject.

  python scripts/query_agent_engine.py "NEXT27-MAIN needs 1 booth LED video wall."
  python scripts/query_agent_engine.py            # interactive chat

When the agent needs a human decision it returns an `adk_request_confirmation` call. This client shows the
request and asks you to Confirm or Reject, then sends your answer back, exactly what the adk web chat does.

Needs AGENT_ENGINE_RESOURCE (written to .env by deploy_agent_engine.py) or --resource.
"""
import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import guarded, resolve_project  # noqa: E402

CONFIRM_CALL = "adk_request_confirmation"


def _get(d, *names, default=None):
    """Read a key that may be snake_case or camelCase."""
    for n in names:
        if isinstance(d, dict) and n in d and d[n] is not None:
            return d[n]
    return default


def parse_event(event: dict):
    """Returns (texts, confirmation_requests) from one streamed event dict."""
    texts, confirmations = [], []
    content = _get(event, "content", default={}) or {}
    for part in _get(content, "parts", default=[]) or []:
        if _get(part, "text") and _get(content, "role", default="model") != "user":
            texts.append(part["text"])
        call = _get(part, "function_call", "functionCall")
        if call and _get(call, "name") == CONFIRM_CALL:
            args = _get(call, "args", default={}) or {}
            original = _get(args, "originalFunctionCall", "original_function_call", default={}) or {}
            confirmation = _get(args, "toolConfirmation", "tool_confirmation", default={}) or {}
            confirmations.append({"id": call.get("id"), "tool": _get(original, "name"),
                                  "args": _get(original, "args", default={}),
                                  "hint": _get(confirmation, "hint", default="")})
    return texts, confirmations


def confirmation_reply(request_id: str, confirmed: bool) -> dict:
    return {"role": "user", "parts": [{"function_response": {
        "id": request_id, "name": CONFIRM_CALL, "response": {"confirmed": confirmed}}}]}


def ask_human(req: dict) -> bool:
    print("\n  *** HUMAN APPROVAL NEEDED ***")
    print(f"  tool: {req['tool']}")
    for k, v in (req["args"] or {}).items():
        print(f"    {k}: {v}")
    if req["hint"]:
        print(f"  note: {req['hint']}")
    return input("  Confirm? [y/N] ").strip().lower() in ("y", "yes")


async def converse(remote, user_id, session_id, message):
    """Send a message, print the answer, and whenever the agent asks for a human decision, ask and send it back."""
    queue = [message]
    while queue:
        msg = queue.pop(0)
        pending = []
        async for event in remote.async_stream_query(user_id=user_id, session_id=session_id, message=msg):
            texts, confirmations = parse_event(event)
            for t in texts:
                print(t)
            pending += confirmations
        for req in pending:  # ask after the stream has finished, then let the agent continue
            queue.append(confirmation_reply(req["id"], ask_human(req)))


@guarded
def run(args, project=""):
    try:
        import agentplatform as sdk  # newer name of the SDK
        sdk.Client
    except (ImportError, AttributeError):
        import vertexai as sdk
        import warnings
        warnings.filterwarnings("ignore", category=FutureWarning)

    resource = args.resource or os.getenv("AGENT_ENGINE_RESOURCE")
    if not resource:
        env = ROOT / ".env"
        for line in env.read_text().splitlines() if env.exists() else []:
            if line.startswith("AGENT_ENGINE_RESOURCE="):
                resource = line.split("=", 1)[1].strip()
    if not resource:
        sys.exit("No deployed agent known. Run scripts/deploy_agent_engine.py first, or pass --resource "
                 "projects/<p>/locations/<region>/reasoningEngines/<id>")
    region = resource.split("/")[3]
    client = sdk.Client(project=project, location=region)
    remote = client.agent_engines.get(name=resource)

    async def go():
        user_id = args.user or f"demo-{uuid.uuid4().hex[:6]}"
        session = await remote.async_create_session(user_id=user_id)
        session_id = _get(session, "id")
        print(f"Session {session_id} on {resource}\n")
        if args.message:
            await converse(remote, user_id, session_id, args.message)
            return
        while True:
            try:
                text = input("\nyou> ").strip()
            except EOFError:
                return
            if text.lower() in ("exit", "quit", ""):
                return
            await converse(remote, user_id, session_id, text)

    try:
        asyncio.run(go())
    except Exception as exc:  # noqa: BLE001 - show the problem and the deployment's logs instead of a stack trace
        from agent_engine_logs import recent_logs
        print(f"\nThe deployed agent returned an error:\n  {str(exc)[:600]}\n")
        print("Recent logs of the deployment (newest last):\n")
        print(recent_logs(project, resource, limit=40, errors_only=False))
        print("\nMore: python scripts/agent_engine_logs.py --limit 100 --errors-only")
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("message", nargs="?", default=None)
    ap.add_argument("--project", default=None)
    ap.add_argument("--resource", default=None, help="projects/<p>/locations/<r>/reasoningEngines/<id>")
    ap.add_argument("--user", default=None)
    args = ap.parse_args()
    run(args, project=resolve_project(args.project))


if __name__ == "__main__":
    main()
