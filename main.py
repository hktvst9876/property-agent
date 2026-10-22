"""
main.py — command-line entry point.

  python main.py init-db                 # create the SQLite schema
  python main.py seed                    # load a demo property/tenancy/ledger
  python main.py intake '<event json>'   # run one incoming situation end-to-end
  python main.py sweep arrears           # scan all tenancies for arrears
  python main.py sweep renewals          # scan all tenancies for approaching expiry
  python main.py sweep followups         # chase overdue contractors / stalled cases
  python main.py status                  # recent cases + pending approvals
  python main.py bot                     # run the Telegram approval poller (needs .env)
  python main.py simulate <phone> "<text>" [--media]   # feed one inbound message
                                             # through the pipeline (offline), show the reply
  python main.py chat [phone]            # interactive back-and-forth (safe dry-run); you
                                         # type as a party, the agent replies. Default
                                         # sender is the seeded tenant. /as <phone> to switch.
  python main.py listen                  # live: poll WhatsApp and auto-handle messages
                                         # (mock unless WHATSAPP_MODE=live)
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

# Console may be cp1252 (Windows); our summaries use unicode (arrows, emoji that
# also go to Telegram). Encode console output as UTF-8 so printing never crashes.
for _stream in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from db.store import init_db, connect, pending_approvals


def _cmd_init_db() -> None:
    init_db()
    print("Database initialised.")


def _cmd_seed() -> None:
    from scripts.seed_demo import seed
    seed()


def _cmd_intake(arg: str) -> None:
    from orchestrator import handle_event
    event = json.loads(arg)
    result = handle_event(event)
    print(json.dumps(result, indent=2, default=str))


def _cmd_sweep(which: str) -> None:
    from orchestrator import sweep_arrears, sweep_renewals, sweep_followups
    if which == "arrears":
        results = sweep_arrears()
    elif which == "renewals":
        results = sweep_renewals()
    elif which == "followups":
        results = sweep_followups()
    else:
        print("Usage: python main.py sweep [arrears|renewals|followups]")
        return
    print(json.dumps(results, indent=2, default=str))


def _cmd_status() -> None:
    conn = connect()
    cases = conn.execute(
        "SELECT id, type, status, urgency, summary FROM cases ORDER BY id DESC LIMIT 10"
    ).fetchall()
    conn.close()
    print("Recent cases:")
    for c in cases:
        u = f" [{c['urgency']}]" if c["urgency"] else ""
        print(f"  #{c['id']} {c['type']}{u} — {c['status']}: {c['summary']}")
    pend = pending_approvals()
    print(f"\nPending approvals: {len(pend)}")
    for p in pend:
        print(f"  #{p['id']} {p['action']} (case {p['case_id']})")


def _cmd_bot() -> None:
    from approvals.telegram_bot import poll_loop
    poll_loop()


def _cmd_simulate(phone: str, text: str, has_media: bool = False) -> None:
    """Inject one inbound message and show what the agent texts back. Offline."""
    from orchestrator import handle_inbound
    before = _max_comm_id()
    result = handle_inbound(phone, text, has_media=has_media)
    print("\n--- agent decision ---")
    print(json.dumps(result, indent=2, default=str))
    print("\n--- replies the agent would send ---")
    rows = _comms_after(before)
    if not rows:
        print("  (none)")
    for r in rows:
        print(f"\n  to: {r['audience_role']} via {r['channel']}")
        for line in r["body"].splitlines():
            print(f"    {line}")


def _cmd_chat(phone: str | None = None) -> None:
    """Interactive mock conversation. You type as a party; the agent replies. Always
    dry-run (nothing is sent to a real person), so it's safe to experiment freely."""
    from orchestrator import handle_inbound
    from db.store import find_party_by_phone

    phone = phone or "+6592220000"   # default to the seeded tenant (Aisha Rahman)

    def _who(p: str) -> str:
        party = find_party_by_phone(p)
        return f"{party['name']} ({party['role']})" if party else f"unknown sender {p}"

    print(f"\n  Interactive chat — you are texting AS: {_who(phone)}")
    print("  Type a message and press Enter to send it to the agent.")
    print("  Commands:  /as <phone>  switch who you're texting as   |   /quit  exit\n")

    while True:
        try:
            text = input("  you> ").lstrip("﻿").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  (ended)")
            return
        if not text:
            continue
        if text in ("/quit", "/exit"):
            print("  (ended)")
            return
        if text.startswith("/as "):
            phone = text[4:].strip()
            print(f"  [now texting as: {_who(phone)}]\n")
            continue

        before = _max_comm_id()
        handle_inbound(phone, text)
        rows = _comms_after(before)
        if not rows:
            print("    (the agent did not send a reply)\n")
            continue
        for r in rows:
            print(f"\n  agent -> {r['audience_role']}:")
            for line in r["body"].splitlines():
                print(f"      {line}")
        print()


def _cmd_listen() -> None:
    from orchestrator import listen
    listen()


def _max_comm_id() -> int:
    conn = connect()
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM communications").fetchone()
    conn.close()
    return row["m"]


def _comms_after(comm_id: int):
    conn = connect()
    rows = conn.execute(
        "SELECT audience_role, channel, body FROM communications "
        "WHERE id > ? AND direction='out' ORDER BY id", (comm_id,),
    ).fetchall()
    conn.close()
    return rows


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "init-db":
        _cmd_init_db()
    elif cmd == "seed":
        _cmd_seed()
    elif cmd == "intake":
        if len(sys.argv) < 3:
            print("Usage: python main.py intake '<event json>'")
            return
        _cmd_intake(sys.argv[2])
    elif cmd == "sweep":
        _cmd_sweep(sys.argv[2] if len(sys.argv) > 2 else "")
    elif cmd == "status":
        _cmd_status()
    elif cmd == "bot":
        _cmd_bot()
    elif cmd == "simulate":
        if len(sys.argv) < 4:
            print('Usage: python main.py simulate <phone> "<text>" [--media]')
            return
        _cmd_simulate(sys.argv[2], sys.argv[3], has_media="--media" in sys.argv)
    elif cmd == "chat":
        _cmd_chat(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "listen":
        _cmd_listen()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
