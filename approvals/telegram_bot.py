"""
approvals/telegram_bot.py — the one-tap human-approval gate.

Identical mechanics to store-tester: no bot framework, just raw HTTPS via
`requests`. Two roles:
  1. push_pending_approvals() — orchestrator calls this; every pending approval is
     sent to the property manager with inline [Approve]/[Reject] buttons.
  2. poll_loop()              — long-running worker that reads button taps and
     writes the resolution back to the DB.

Nothing money-/legal-touching executes until status='approved'.

Setup (one time):
  1. Telegram → @BotFather → /newbot → save the token.
  2. Message the bot once, then open
       https://api.telegram.org/bot<TOKEN>/getUpdates
     and copy "chat":{"id":...} — that's TELEGRAM_CHAT_ID.
  3. Put both in .env.
"""

from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.store import connect, pending_approvals, resolve_approval

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"
POLL_TIMEOUT_S = 25

# Actions with legal/financial weight — flagged louder; same tap required.
HIGH_STAKES = {"issue_notice", "deposit_claim", "raise_rent", "non_renewal",
               "escalate_human"}


def _check_creds() -> None:
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env")


def send_message(text: str, parse_mode: str = "Markdown") -> dict:
    """Plain notification — daily summaries, errors, etc."""
    _check_creds()
    r = requests.post(
        f"{API}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text, "parse_mode": parse_mode},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def _format_approval(approval: dict) -> str:
    payload = json.loads(approval["payload_json"]) if approval["payload_json"] else {}
    action = approval["action"]
    bang = "⚠️ *HIGH-STAKES*" if action in HIGH_STAKES else "ℹ️"
    lines = [f"{bang} approval #{approval['id']} — `{action}`", ""]
    if approval.get("case_id"):
        lines.append(f"*case_id:* {approval['case_id']}")
    if payload:
        lines.append("*payload:*")
        lines.append("```json")
        lines.append(json.dumps(payload, indent=2))
        lines.append("```")
    return "\n".join(lines)


def _inline_keyboard(approval_id: int) -> dict:
    return {
        "inline_keyboard": [[
            {"text": "✅ Approve", "callback_data": f"approve:{approval_id}"},
            {"text": "❌ Reject",  "callback_data": f"reject:{approval_id}"},
        ]]
    }


def push_approval(approval: dict) -> None:
    _check_creds()
    r = requests.post(
        f"{API}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": _format_approval(approval),
            "parse_mode": "Markdown",
            "reply_markup": _inline_keyboard(approval["id"]),
        },
        timeout=15,
    )
    r.raise_for_status()


def push_pending_approvals() -> int:
    """Push every pending approval. No-op (returns 0) if Telegram isn't configured,
    so the orchestrator runs fine offline."""
    if not BOT_TOKEN or not CHAT_ID:
        return 0
    rows = pending_approvals()
    for row in rows:
        push_approval(dict(row))
    return len(rows)


def _handle_callback(callback: dict) -> None:
    data = callback.get("data", "")
    if ":" not in data:
        return
    action, sid = data.split(":", 1)
    try:
        approval_id = int(sid)
    except ValueError:
        return

    status = "approved" if action == "approve" else "rejected"
    user = callback.get("from", {})
    resolved_by = f"{user.get('username') or user.get('id', 'unknown')}"

    try:
        resolve_approval(approval_id, status, resolved_by)
    except Exception as exc:
        _answer_callback(callback["id"], f"Error: {exc}")
        return

    _answer_callback(callback["id"], f"#{approval_id} → {status}")
    msg = callback.get("message", {})
    if msg.get("message_id"):
        requests.post(
            f"{API}/editMessageReplyMarkup",
            json={"chat_id": CHAT_ID, "message_id": msg["message_id"],
                  "reply_markup": {"inline_keyboard": []}},
            timeout=10,
        )
        requests.post(
            f"{API}/sendMessage",
            json={"chat_id": CHAT_ID,
                  "text": f"#{approval_id} → *{status}* by `{resolved_by}`",
                  "parse_mode": "Markdown",
                  "reply_to_message_id": msg["message_id"]},
            timeout=10,
        )


def _answer_callback(callback_id: str, text: str) -> None:
    try:
        requests.post(
            f"{API}/answerCallbackQuery",
            json={"callback_query_id": callback_id, "text": text},
            timeout=10,
        )
    except requests.RequestException:
        pass


def poll_loop() -> None:
    """Long-poll Telegram for button taps. Run as a foreground process."""
    _check_creds()
    print(f"Bot polling. Chat: {CHAT_ID}. Ctrl+C to stop.")
    offset = 0
    while True:
        try:
            r = requests.get(
                f"{API}/getUpdates",
                params={"offset": offset, "timeout": POLL_TIMEOUT_S,
                        "allowed_updates": json.dumps(["callback_query", "message"])},
                timeout=POLL_TIMEOUT_S + 5,
            )
            r.raise_for_status()
            for upd in r.json().get("result", []):
                offset = upd["update_id"] + 1
                if "callback_query" in upd:
                    _handle_callback(upd["callback_query"])
                elif "message" in upd:
                    _handle_text(upd["message"])
        except requests.RequestException as exc:
            print(f"poll error: {exc}; sleeping 5s")
            time.sleep(5)


def _handle_text(message: dict) -> None:
    text = (message.get("text") or "").strip()
    if text == "/pending":
        rows = pending_approvals()
        if not rows:
            send_message("No pending approvals.")
            return
        for row in rows:
            push_approval(dict(row))
    elif text == "/status":
        send_message(_status_summary())
    elif text in ("/start", "/help"):
        send_message(
            "*Property agent bot*\n"
            "I send you approvals before anything money- or legal-touching happens.\n\n"
            "/pending — re-send all pending approvals\n"
            "/status — recent cases\n"
        )


def _status_summary() -> str:
    conn = connect()
    rows = conn.execute(
        "SELECT id, type, status, urgency, summary FROM cases ORDER BY id DESC LIMIT 6"
    ).fetchall()
    conn.close()
    if not rows:
        return "No cases yet."
    lines = ["*Recent cases:*"]
    for r in rows:
        u = f" [{r['urgency']}]" if r["urgency"] else ""
        lines.append(f"• #{r['id']} `{r['type']}`{u} — {r['status']}")
    return "\n".join(lines)


if __name__ == "__main__":
    poll_loop()
