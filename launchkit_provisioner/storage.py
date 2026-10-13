"""Hand-off of the order pack PDF to the email workflow.

The Send Email task attaches a file from a Cloud Storage path, so the PDF is written to one private bucket (nobody gets a
link; the emails carry the PDF as an attachment). Never raises: no bucket or any error means "no attachment".
"""
import logging

from . import config

log = logging.getLogger(__name__)


def bucket_name() -> str:
    return config.ORDER_PACK_BUCKET


def upload_pack(request_id: str, pdf: bytes) -> str:
    """Write the PDF and return its gs:// path, or "" when no bucket is set or the upload fails."""
    name = bucket_name()
    if not name:
        return ""
    try:
        from google.cloud import storage
        obj = f"{request_id}/order-pack-{request_id}.pdf"
        storage.Client(project=config.PROJECT or None).bucket(name).blob(obj).upload_from_string(pdf, content_type="application/pdf")
        return f"gs://{name}/{obj}"
    except Exception as exc:  # noqa: BLE001
        log.warning("order pack upload failed: %s", exc)
        return ""


def pack_path(repo, request_id: str) -> str:
    """Build the order pack for a request and hand it to storage. "" when it cannot be done."""
    if not bucket_name():
        return ""
    try:
        from . import order_pack
        return upload_pack(request_id, order_pack.build_pdf(repo, request_id))
    except Exception as exc:  # noqa: BLE001
        log.warning("order pack not built: %s", exc)
        return ""
