"""Small, timeout-aware client boundary for verified graph operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class GraphQueryError(RuntimeError):
    def __init__(self, operation: str, message: str):
        self.operation = operation
        super().__init__(f"{operation} failed: {message}")


@dataclass(frozen=True)
class GraphClientConfig:
    timeout_seconds: int = 30


class TigerGraphClient:
    def __init__(self, connection: Any, config: GraphClientConfig | None = None):
        self.connection = connection
        self.config = config or GraphClientConfig()

    def document_count(self) -> int:
        try:
            result = self.connection.getVertexCount("Document", realtime=True)
            return int(result)
        except Exception as error:
            raise GraphQueryError("document_count", str(error)) from error

    def document_by_id(self, document_id: str) -> dict[str, Any] | None:
        if not isinstance(document_id, str) or not document_id:
            raise ValueError("document_id must be a non-empty string")
        try:
            rows = self.connection.getVertexDataFrameById("Document", document_id)
            if rows is None or len(rows.index) == 0:
                return None
            row = rows.iloc[0].to_dict()
            return {str(key): value.item() if hasattr(value, "item") else value for key, value in row.items()}
        except Exception as error:
            raise GraphQueryError("document_by_id", str(error)) from error

    def list_documents(self, limit: int = 20) -> list[dict[str, Any]]:
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        try:
            rows = self.connection.getVertices("Document", limit=limit, timeout=self.config.timeout_seconds, withId=True)
            return list(rows or [])
        except Exception as error:
            raise GraphQueryError("list_documents", str(error)) from error