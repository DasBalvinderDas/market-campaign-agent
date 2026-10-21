"""Attach a file to the chat (an ADK artifact). Never raises: no artifact service means no attachment."""


async def attach_pdf(tool_context, name: str, data: bytes) -> bool:
    if tool_context is None:
        return False
    try:
        from google.genai import types
        await tool_context.save_artifact(name, types.Part.from_bytes(data=data, mime_type="application/pdf"))
        return True
    except Exception:  # noqa: BLE001 - the answer must never fail because a PDF could not be attached
        return False
