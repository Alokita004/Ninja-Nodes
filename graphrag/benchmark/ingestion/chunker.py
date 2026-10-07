"""Phase 5 document preservation boundary.

Configurable chunking is intentionally deferred to Phase 6. Ingestion keeps
the complete source text on the Document vertex and does not create chunks.
"""

from __future__ import annotations


def preserve_document_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return text