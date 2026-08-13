"""Demo: a refund-ops agent guarded by Sphinx.

Exercises the full HITL lifecycle over REST or MCP transport:
  1. Agent proposes risky actions and requests approval.
  2. A simulated human (or the SLA policy) decides each ticket.
  3. The agent reads the final decision payload and reports the outcome.

Run against a live Sphinx (API on :8001 + MCP on :8100):
    python demo_agent.py [--transport rest|mcp]
"""
from __future__ import annotations

import argparse
import threading
import time

import httpx

from sphinx_sdk.client import SphinxClient

API = "http://localhost:8001"
MCP = "http://localhost:8100/mcp"


def _human_reviewer(api_url: str, interval_s: float = 4.0, approve_all: bool = True) -> threading.Thread:
    """Background thread that reviews and approves pending tickets like a human."""

    def run():
        seen: set[str] = set()
        while True:
            try:
                r = httpx.get(f"{api_url}/api/requests?status=pending&limit=50", timeout=5)
                for item in r.json()["items"]:
                    rid = item["id"]
                    if rid in seen:
                        continue
                    seen.add(rid)
                    if approve_all:
                        httpx.post(f"{api_url}/api/requests/{rid}/approve", json={"reviewer_id": "demo-human", "note": "Reviewed by demo human (simulated)."}, timeout=5)
                    else:
                        httpx.post(f"{api_url}/api/requests/{rid}/reject", json={"reviewer_id": "demo-human", "note": "Rejected by demo human (simulated)."}, timeout=5)
            except Exception:
                pass
            time.sleep(interval_s)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["rest", "mcp"], default="mcp")
    parser.add_argument("--api-url", default=API, help="Sphinx REST API base URL")
    parser.add_argument("--mcp-url", default=MCP, help="Sphinx MCP streamable HTTP endpoint")
    parser.add_argument("--no-auto-review", action="store_true", help="rely on SLA policy instead of a simulated human")
    args = parser.parse_args()

    reviewer = None if args.no_auto_review else _human_reviewer(args.api_url)

    scenarios = [
        {
            "title": "Approve refund of $980 for order ORD-77241",
            "description": "Customer reported duplicate charge; refund is within policy threshold.",
            "action_payload": {"action": "refund", "order_id": "ORD-77241", "amount_usd": 980.0, "currency": "USD", "reason": "duplicate_charge"},
            "risk_level": "medium",
        },
        {
            "title": "Flag customer ORD-77241 as high-risk",
            "description": "Second chargeback in 30 days; recommend watchlist entry.",
            "action_payload": {"action": "flag_risk", "customer_id": "CUST-2201", "level": "high", "reason": "repeated_chargebacks"},
            "risk_level": "high",
        },
        {
            "title": "Auto-fill support ticket from chat transcript",
            "description": "Mechanical action on a trusted pipeline; should auto-approve.",
            "action_payload": {"action": "create_ticket", "channel": "chat", "template": "refund-flow"},
            "risk_level": "low",
        },
    ]

    print(f"Sphinx demo agent (transport={args.transport})")
    with SphinxClient(
        transport=args.transport,
        agent_id="refund-agent",
        framework="langgraph",
        session_id="sess-refund-01",
        base_url=args.api_url,
        mcp_url=args.mcp_url,
    ) as client:
        for i, sc in enumerate(scenarios, 1):
            print(f"\n[step {i}] proposing: {sc['title']}")
            ticket = client.request_approval(
                sc["title"],
                sc["action_payload"],
                description=sc["description"],
                risk_level=sc["risk_level"],
            )
            print(f"  -> ticket {ticket.ref} status={ticket.status}")

            decision = client.wait_for_decision(ticket.id, timeout_s=120, poll_interval_s=1.0)
            print(f"  -> decision status={decision['status']} approved={decision['approved']}")
            print(f"     payload={decision['decision_payload']}")
            print(f"     reviewer_note={decision.get('reviewer_note')}")

            if decision["approved"]:
                outcome = "success"
                note = "Refund processed and acknowledged by customer."
            else:
                outcome = "partial" if i == 2 else "failure"
                note = "Action blocked; escalated to support lead."
            fb = client.submit_feedback(ticket.id, outcome, note=note)
            print(f"  -> feedback outcome={fb['outcome']}")


if __name__ == "__main__":
    main()
