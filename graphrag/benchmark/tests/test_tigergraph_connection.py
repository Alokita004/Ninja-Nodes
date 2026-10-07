from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def _config() -> dict:
    root = Path(__file__).resolve().parents[2]
    path = Path(os.getenv("SERVER_CONFIG", root / "configs" / "server_config.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def test_tigergraph_config_has_non_secret_connection_fields() -> None:
    db = _config()["db_config"]
    assert db["hostname"].startswith(("http://", "https://"))
    assert db["graph_name"]
    assert db["restppPort"]
    assert db["gsPort"]
    assert db.get("secret") or db.get("apiToken") or db.get("password")


def test_tigergraph_read_only_connection() -> None:
    """Run only when explicitly enabled; never prints credentials or responses."""
    if os.getenv("RUN_TIGERGRAPH_INTEGRATION") != "1":
        pytest.skip("Set RUN_TIGERGRAPH_INTEGRATION=1 to test the configured graph")

    from pyTigerGraph import TigerGraphConnection

    db = _config()["db_config"]
    connection = TigerGraphConnection(
        host=db["hostname"],
        graphname=db["graph_name"],
        gsqlSecret=db.get("secret", ""),
        username=db.get("username", "tigergraph"),
        tgCloud=True,
        restppPort=db.get("restppPort", "9000"),
        gsPort=db.get("gsPort", "14240"),
    )
    assert connection.getToken()
    result = connection.gsql("USE GRAPH " + db["graph_name"])
    assert result is not None