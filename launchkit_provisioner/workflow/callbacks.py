"""ADK callbacks shared by the agents."""
import logging


def on_tool_error(tool, args, tool_context, error):
    """A tool that raises (BigQuery table missing, permission denied, ...) must not end the run silently: hand the
    error text to the model so it tells the user what to fix."""
    logging.getLogger(__name__).exception("tool %s failed", getattr(tool, "name", tool))
    return {"status": "error", "tool": getattr(tool, "name", str(tool)),
            "message": f"{type(error).__name__}: {str(error)[:500]}",
            "next_step": "Tell the user this tool failed, quote the message, and stop. Do not retry or invent data."}


_GREETINGS = {"hi", "hello", "hey", "hi there", "hello there", "hey there", "hiya", "hola", "greetings", "good morning",
              "good afternoon", "good evening", "help", "what can you do", "what do you do", "who are you", "start"}


def _is_greeting(text: str) -> bool:
    import re
    return re.sub(r"[^a-z ]", "", (text or "").lower()).strip() in _GREETINGS


def greeting_shortcut(callback_context, llm_request):
    """A bare greeting always gets the full capabilities card, word for word: the model would shorten it. Anything that
    goes wrong here returns None, so the model answers as usual."""
    try:
        from google.adk.models import LlmResponse
        from google.genai import types

        from ..presentation import capabilities_card
        from ..repositories import get_repo
        last = (llm_request.contents or [None])[-1]
        parts = getattr(last, "parts", None) or []
        if getattr(last, "role", "user") != "user" or any(getattr(p, "function_response", None) for p in parts):
            return None
        text = " ".join(p.text for p in parts if getattr(p, "text", None))
        users = [c for c in llm_request.contents if getattr(c, "role", "") == "user"
                 and any(getattr(p, "text", None) for p in (c.parts or []))]
        if len(users) != 1 or not _is_greeting(text):          # only the very first message of a chat
            return None
        card = capabilities_card(get_repo().list_launches())
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=card)]))
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("greeting shortcut failed")
        return None


async def attach_pack_after_orders(tool, args, tool_context, tool_response):
    """When the orders are placed, put a fresh order pack PDF (now with the purchase order numbers) in the chat. Best effort:
    it never changes the answer."""
    try:
        import re

        from .. import order_pack
        from ..repositories import get_repo
        from ..tools.files import attach_pdf
        if getattr(tool, "name", "") != "fulfilment_agent":
            return None
        m = re.search(r"REQ-[A-Za-z0-9]+", str(args))
        if not m:
            return None
        repo = get_repo()
        if not repo.list_pos(m[0]):                 # nothing was ordered (blocked or failed): no pack
            return None
        await attach_pdf(tool_context, f"order-pack-{m[0]}-purchase-orders.pdf", order_pack.build_pdf(repo, m[0]))
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("could not attach the order pack after the orders")
    return None
