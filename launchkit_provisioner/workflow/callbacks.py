"""ADK callbacks shared by the agents."""
import logging


def on_tool_error(tool, args, tool_context, error):
    """A tool that raises (BigQuery table missing, permission denied, ...) must not end the run silently: hand the
    error text to the model so it tells the user what to fix."""
    logging.getLogger(__name__).exception("tool %s failed", getattr(tool, "name", tool))
    return {"status": "error", "tool": getattr(tool, "name", str(tool)),
            "message": f"{type(error).__name__}: {str(error)[:500]}",
            "next_step": "Tell the user this tool failed, quote the message, and stop. Do not retry or invent data."}
