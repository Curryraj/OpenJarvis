"""Tests for compute_vault_stats — powers the dashboard's Vault Sphere panel."""

from __future__ import annotations

import json
from pathlib import Path

from openjarvis.server.vault_stats import compute_vault_stats


def _write_graph(tmp_path: Path, nodes: list[dict]) -> Path:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps({"nodes": nodes, "links": []}), encoding="utf-8")
    return graph_path


class TestComputeVaultStats:
    def test_missing_file_returns_zeroed_stats(self, tmp_path: Path) -> None:
        result = compute_vault_stats(tmp_path / "does-not-exist.json")
        assert result == {"node_count": 0, "domain_count": 0, "last_updated": None}

    def test_counts_nodes_and_distinct_communities(self, tmp_path: Path) -> None:
        graph_path = _write_graph(
            tmp_path,
            [
                {"id": "a", "community_name": "AI News"},
                {"id": "b", "community_name": "AI News"},
                {"id": "c", "community_name": "Career"},
            ],
        )
        result = compute_vault_stats(graph_path)
        assert result["node_count"] == 3
        assert result["domain_count"] == 2

    def test_nodes_without_community_name_fall_back_to_community_id(
        self, tmp_path: Path
    ) -> None:
        graph_path = _write_graph(
            tmp_path,
            [
                {"id": "a", "community": 1},
                {"id": "b", "community": 1},
                {"id": "c", "community": 2},
            ],
        )
        result = compute_vault_stats(graph_path)
        assert result["node_count"] == 3
        assert result["domain_count"] == 2

    def test_last_updated_reflects_file_mtime(self, tmp_path: Path) -> None:
        graph_path = _write_graph(tmp_path, [{"id": "a", "community": 1}])
        result = compute_vault_stats(graph_path)
        assert result["last_updated"] is not None
        # ISO 8601 — must be parseable.
        from datetime import datetime

        datetime.fromisoformat(result["last_updated"])

    def test_malformed_json_returns_zeroed_stats(self, tmp_path: Path) -> None:
        graph_path = tmp_path / "graph.json"
        graph_path.write_text("not valid json", encoding="utf-8")
        result = compute_vault_stats(graph_path)
        assert result == {"node_count": 0, "domain_count": 0, "last_updated": None}
