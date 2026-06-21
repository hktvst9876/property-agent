"""
notify.py — operator-facing FYI messages (no approval needed).

Sends a short case summary to the property manager. Falls back to console when
Telegram isn't configured, so the orchestrator runs fine offline. The approval
flow lives in approvals/telegram_bot.py.
"""

from __future__ import annotations
import os

_URGENCY_EMOJI = {"EMERGENCY": "🔴", "URGENT": "🟠", "ROUTINE": "🟢"}


def case_summary(case: dict, decision: dict, action_taken: str) -> str:
    emoji = _URGENCY_EMOJI.get(case.get("urgency") or "", "ℹ️")
    lines = [
        f"{emoji} *Case #{case.get('id')} — {case.get('type')}*",
        f"verdict: *{decision.get('verdict')}*",
        f"_{decision.get('reason', '')}_",
        f"action: {action_taken}",
    ]
    if case.get("next_action"):
        lines.append(f"next: {case['next_action']}")
    return "\n".join(lines)


def notify_operator(case: dict, decision: dict, action_taken: str) -> None:
    msg = case_summary(case, decision, action_taken)
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        try:
            from approvals.telegram_bot import send_message
            send_message(msg)
            return
        except Exception as exc:   # never let a notification failure break a case
            print(f"  (operator notify failed, console only: {exc})")
    print("  [OPERATOR]\n" + "\n".join("    " + ln for ln in msg.splitlines()))
