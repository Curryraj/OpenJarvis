"""Custom LiteLLM callback that appends per-request cost/usage to a JSONL file.

This is the spend-tracking fallback used when no Postgres is available for the
LiteLLM admin UI. Every successful (and failed) proxy request writes one line to
$OJ_LITELLM_SPEND_LOG. Aggregate with `litellm/spend_report.py`.
"""

from __future__ import annotations

import datetime
import json
import os
import threading

from litellm.integrations.custom_logger import CustomLogger

LOG_PATH = os.environ.get(
    "OJ_LITELLM_SPEND_LOG",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "spend.jsonl"),
)
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

_lock = threading.Lock()


def _write(kwargs, response_obj, start_time, end_time, status: str) -> None:
    try:
        cost = kwargs.get("response_cost")
        litellm_params = kwargs.get("litellm_params") or {}
        metadata = litellm_params.get("metadata") or {}
        usage = None
        try:
            usage = getattr(response_obj, "usage", None) or (
                response_obj.get("usage") if isinstance(response_obj, dict) else None
            )
        except Exception:
            usage = None

        def _u(field):
            if usage is None:
                return None
            return getattr(usage, field, None) if not isinstance(usage, dict) else usage.get(field)

        dur = None
        try:
            if start_time and end_time:
                dur = (end_time - start_time).total_seconds()
        except Exception:
            dur = None

        rec = {
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
            "status": status,
            "model": kwargs.get("model"),
            "model_group": metadata.get("model_group"),
            "call_type": kwargs.get("call_type"),
            "cost_usd": cost,
            "prompt_tokens": _u("prompt_tokens"),
            "completion_tokens": _u("completion_tokens"),
            "total_tokens": _u("total_tokens"),
            "duration_s": dur,
            "key_alias": metadata.get("user_api_key_alias"),
            "exception": str(kwargs.get("exception")) if status == "failure" else None,
        }
        line = json.dumps(rec)
        with _lock:
            with open(LOG_PATH, "a") as f:
                f.write(line + "\n")
    except Exception as exc:  # never let logging break a request
        print(f"[spend_logger] error: {exc}")


class SpendLogger(CustomLogger):
    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        _write(kwargs, response_obj, start_time, end_time, "success")

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        _write(kwargs, response_obj, start_time, end_time, "success")

    def log_failure_event(self, kwargs, response_obj, start_time, end_time):
        _write(kwargs, response_obj, start_time, end_time, "failure")

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        _write(kwargs, response_obj, start_time, end_time, "failure")


proxy_handler_instance = SpendLogger()
