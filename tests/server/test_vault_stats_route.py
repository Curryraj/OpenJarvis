"""Tests for GET /v1/vault/stats."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.server.routes import router  # noqa: E402


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


class TestVaultStatsRoute:
    def test_env_var_unset_returns_zeroed_stats(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENJARVIS_VAULT_GRAPH_PATH", raising=False)
        client = TestClient(_make_app())
        resp = client.get("/v1/vault/stats")
        assert resp.status_code == 200
        assert resp.json() == {"node_count": 0, "domain_count": 0, "last_updated": None}

    def test_reads_graph_from_env_var_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        graph_path = tmp_path / "graph.json"
        graph_path.write_text(
            json.dumps(
                {
                    "nodes": [
                        {"id": "a", "community_name": "AI News"},
                        {"id": "b", "community_name": "Career"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("OPENJARVIS_VAULT_GRAPH_PATH", str(graph_path))
        client = TestClient(_make_app())
        resp = client.get("/v1/vault/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["node_count"] == 2
        assert body["domain_count"] == 2
        assert body["last_updated"] is not None
