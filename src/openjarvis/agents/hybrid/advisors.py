"""AdvisorsAgent — inference-only port of advisor-models (Asawa et al., 2026).

Paper: arXiv:2510.02453. A small open-source advisor model writes feedback
that *steers* a black-box cloud executor. The paper trains the advisor with
RL; we don't have a released checkpoint, so this agent is the **inference-
only lower bound**: an untrained Qwen advisor zero-shot prompted with the
paper's structure.

Pipeline (mirrors ``advisor_models/math/env.py``):

1. **Executor (cloud)** answers the question.
2. **Advisor (local)** reads question + initial response and writes
   critique / hint text.
3. **Executor (cloud)** re-answers given question + its own initial
   response + advisor feedback. This final answer is what we score.

Results from the hybrid harness (n=30 GAIA):
``advisors-gaia-qwen9b-opus-30`` = 0.533, $0.02/task — within 3pp of
baseline-cloud at 30× cheaper. The RL-trained variant would land higher.

Ported from ``hybrid-local-cloud-compute/adapters/advisors_adapter.py``.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict, Optional, Tuple

from openjarvis.agents._stubs import AgentContext
from openjarvis.agents.hybrid._base import LocalCloudAgent
from openjarvis.core.registry import AgentRegistry


# Prompts paraphrased from advisor-models/{math,template}/config.py.

EXECUTOR_INITIAL_SYS = (
    "You are a careful problem-solver. Read the question, reason step by step "
    "as needed, then commit to one best answer following any answer-format "
    "instructions in the question itself."
)

EXECUTOR_FINAL_SYS = (
    "You are a careful problem-solver. You previously gave an initial answer "
    "to a question and an advisor has reviewed it. Incorporate the advisor's "
    "feedback where it improves correctness; ignore it where it is wrong. "
    "Produce your best final answer, following any answer-format instructions "
    "in the question itself."
)

ADVISOR_TEMPLATE = """You are an expert advisor reviewing another model's draft answer to a user question. Your job is NOT to answer the question yourself; it is to give the answering model concrete, actionable feedback so it can improve its next attempt.

The user question was:
{question}

The answering model's initial response was:
{initial_response}

Provide feedback focused on:
1. Specific errors in reasoning, calculation, factual recall, or formatting.
2. Concrete corrections or alternative approaches it should consider.
3. What evidence or sub-step it should verify before committing.

Be concise (a short paragraph or a few bullet points). Do NOT restate the question. Do NOT provide a complete answer — only the feedback the model needs to improve its own next answer."""


def _resolve_local_model(endpoint: str, registry_model: str) -> str:
    """If the registry-listed model isn't being served by vLLM, fall back to
    whatever the server reports first. Avoids 404s when cell config names
    a model id (e.g. ``Qwen3.5-9B``) that's different from what's loaded.
    """
    try:
        with urllib.request.urlopen(
            endpoint.rstrip("/") + "/models", timeout=5
        ) as r:
            data = json.loads(r.read())
        served = [m["id"] for m in data.get("data", [])]
    except Exception:
        return registry_model
    if registry_model in served:
        return registry_model
    return served[0] if served else registry_model


@AgentRegistry.register("advisors")
class AdvisorsAgent(LocalCloudAgent):
    """Three-step executor ↔ advisor ↔ executor loop. See module docstring."""

    agent_id = "advisors"

    def _run_paradigm(
        self,
        input: str,
        context: Optional[AgentContext],
        **kwargs: Any,
    ) -> Tuple[str, Dict[str, Any]]:
        question = input
        cfg = self._cfg
        executor_max_tokens = int(cfg.get("executor_max_tokens", 4096))
        advisor_max_tokens = int(cfg.get("advisor_max_tokens", 1024))
        advisor_temperature = float(cfg.get("advisor_temperature", 0.2))

        # 1. Initial executor pass
        initial_resp, e1_in, e1_out = self._call_cloud(
            user=f"Question:\n{question}",
            system=EXECUTOR_INITIAL_SYS,
            max_tokens=executor_max_tokens,
            temperature=0.0,
        )

        # 2. Advisor pass (local)
        if not self._local_endpoint or not self._local_model:
            raise ValueError(
                "AdvisorsAgent needs local_model + local_endpoint; got "
                f"model={self._local_model!r} endpoint={self._local_endpoint!r}"
            )
        local_model = _resolve_local_model(self._local_endpoint, self._local_model)
        advisor_prompt = ADVISOR_TEMPLATE.format(
            question=question, initial_response=initial_resp,
        )
        advisor_text, adv_in, adv_out = self._call_vllm(
            local_model,
            self._local_endpoint,
            user=advisor_prompt,
            max_tokens=advisor_max_tokens,
            temperature=advisor_temperature,
            enable_thinking=False,
        )

        # 3. Final executor pass with advisor's hints folded in
        final_user = (
            f"Question:\n{question}\n\n"
            f"Your initial response was:\n{initial_resp}\n\n"
            f"Advisor feedback:\n{advisor_text}\n\n"
            f"Produce your best final answer now, respecting the question's "
            f"answer-format rules."
        )
        final_answer, e2_in, e2_out = self._call_cloud(
            user=final_user,
            system=EXECUTOR_FINAL_SYS,
            max_tokens=executor_max_tokens,
            temperature=0.0,
        )

        tokens_local = adv_in + adv_out
        tokens_cloud = e1_in + e1_out + e2_in + e2_out
        cost = self.cost_usd(self._cloud_model, e1_in + e2_in, e1_out + e2_out)

        meta: Dict[str, Any] = {
            "tokens_local": tokens_local,
            "tokens_cloud": tokens_cloud,
            "cost_usd": cost,
            "turns": 3,
            "traces": {
                "initial_response": initial_resp,
                "advisor_feedback": advisor_text,
                "note": "inference-only advisor (untrained); lower bound on the technique.",
            },
        }
        return final_answer, meta


__all__ = ["AdvisorsAgent"]
