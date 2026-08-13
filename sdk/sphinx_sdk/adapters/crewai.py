"""CrewAI adapter: a human-input callback that routes through Sphinx.

CrewAI lets agents hit a `human_input=True` stop on the `human_input` callback
per task. This adapter converts that hook into a Sphinx approval ticket.

Pattern:
    from sphinx.adapters.crewai import sphinx_human_input

    def run():
        crew = Crew(
            tasks=[...],
            process=Process.sequential,
            manager_agent=...,
            human_input=True,
            callbacks=[sphinx_human_input("finance-analyst")],
        )
"""
from __future__ import annotations

from typing import Any

from sphinx_sdk.adapters.langgraph import HITLGuard


def sphinx_human_input(agent_id: str, **client_kw) -> Any:
    """Build a CrewAI callback factory that guards each human-input step."""

    framework = client_kw.pop("framework", "crewai")
    guard = HITLGuard(agent_id, **client_kw)

    def _callback(caller: Any, step: str, **kw) -> dict:
        prompt = str(kw.get("prompt", "") or kw.get("message", "") or f"CrewAI {step}")
        payload = {"step": step, **{k: v for k, v in kw.items() if k not in ("prompt", "message", "agent")}}
        decision = guard.wait(guard.request(prompt, payload, framework=framework))
        return decision.get("decision_payload") if decision.get("approved") else {"_blocked": True, "reason": decision.get("reviewer_note")}

    _callback.__guard = guard  # keep reference alive
    return _callback
