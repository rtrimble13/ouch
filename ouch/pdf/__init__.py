"""PDF form ingestion (spec §11). Assistive, never authoritative: every
extracted value is presented for confirmation before it is written to a
profile. Extraction never sends document content to a network service.

The heavy dependencies are optional — import them lazily so a missing extra
produces a clear message rather than an ImportError at startup (spec §3.3).
"""

from ouch.errors import PDFError


def require_pdf_support():
    try:
        import pdfplumber  # noqa: F401
        import pypdf  # noqa: F401
    except ImportError as e:
        raise PDFError(
            "PDF support is not installed.",
            hint='pip install "ouch[pdf]"',
        ) from e
