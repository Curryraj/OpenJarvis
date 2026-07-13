"""Computes summary stats for the dashboard's Vault Sphere panel.

Reads a graphify `graph.json` (see the graphify skill) and reduces it to
the three numbers the panel needs. Deliberately tolerant of a missing or
malformed file — the panel must render an idle/empty state, never a
broken dashboard, when the vault hasn't been graphed yet.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict


class VaultStats(TypedDict):
    node_count: int
    domain_count: int
    last_updated: str | None


_ZERO_STATS: VaultStats = {"node_count": 0, "domain_count": 0, "last_updated": None}


def compute_vault_stats(graph_path: Path) -> VaultStats:
    if not graph_path.exists():
        return dict(_ZERO_STATS)

    try:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_ZERO_STATS)

    nodes = data.get("nodes", [])
    if not isinstance(nodes, list):
        return dict(_ZERO_STATS)

    domains = {
        (node.get("community_name") if node.get("community_name") is not None else node.get("community"))
        for node in nodes
        if isinstance(node, dict)
        and (node.get("community_name") is not None or node.get("community") is not None)
    }

    mtime = graph_path.stat().st_mtime
    last_updated = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

    return {
        "node_count": len(nodes),
        "domain_count": len(domains),
        "last_updated": last_updated,
    }
