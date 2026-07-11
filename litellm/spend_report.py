#!/usr/bin/env python3
"""Aggregate litellm/logs/spend.jsonl into a per-model spend summary.

Postgres-free stand-in for the LiteLLM admin UI. Usage:
    .venv/bin/python litellm/spend_report.py [path-to-spend.jsonl]
"""
import json
import os
import sys
from collections import defaultdict

path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
    "OJ_LITELLM_SPEND_LOG",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "spend.jsonl"),
)

agg = defaultdict(lambda: {"calls": 0, "ok": 0, "fail": 0, "cost": 0.0,
                           "ptok": 0, "ctok": 0})
total_cost = 0.0
with open(path) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        g = r.get("model_group") or r.get("model") or "?"
        a = agg[g]
        a["calls"] += 1
        a["ok"] += 1 if r.get("status") == "success" else 0
        a["fail"] += 1 if r.get("status") == "failure" else 0
        a["cost"] += float(r.get("cost_usd") or 0)
        a["ptok"] += int(r.get("prompt_tokens") or 0)
        a["ctok"] += int(r.get("completion_tokens") or 0)
        total_cost += float(r.get("cost_usd") or 0)

hdr = f"{'model':<24}{'calls':>7}{'ok':>5}{'fail':>6}{'p_tok':>9}{'c_tok':>9}{'cost_usd':>12}"
print(hdr)
print("-" * len(hdr))
for g, a in sorted(agg.items(), key=lambda kv: -kv[1]["cost"]):
    print(f"{g:<24}{a['calls']:>7}{a['ok']:>5}{a['fail']:>6}"
          f"{a['ptok']:>9}{a['ctok']:>9}{a['cost']:>12.6f}")
print("-" * len(hdr))
print(f"{'TOTAL':<24}{'':>7}{'':>5}{'':>6}{'':>9}{'':>9}{total_cost:>12.6f}")
