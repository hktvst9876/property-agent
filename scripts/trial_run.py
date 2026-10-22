"""
scripts/trial_run.py — a scripted, real-world tenant<->landlord trial.

Runs a realistic multi-turn WhatsApp-style conversation through the SAME pipeline
the live agent uses (orchestrator.handle_inbound). Nothing is sent to a real
person — COMMS_DRY_RUN keeps everything logged-only.

  python main.py seed              # set up the demo flat/tenant/landlord first
  python scripts/trial_run.py      # then run this

If DEEPSEEK_API_KEY is set (and `pip install openai`), the message UNDERSTANDING
(llm/understand.py) and the WORDING (llm/drafter.py) are done by DeepSeek V3 — the
deterministic engines in core/ still make every decision. With no key it runs on
the offline keyword parser + mood-aware templates (same verdicts, simpler wording).
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from orchestrator import handle_inbound
from llm.router import status as router_status
from db.store import connect, find_party_by_phone

TENANT = "+6592220000"    # Aisha Rahman
LANDLORD = "+6591110000"  # Mr Tan Wei Ming

# (who_texts, message, optional note)
SCRIPT = [
    (TENANT,   "Hi, the aircon in master bedroom not cold at all, 2 days already super hot cannot sleep", False),
    (TENANT,   "oh and rent this month maybe few days late, my company delay salary. so sorry", False),
    (TENANT,   "any update on the aircon? still sweating here sia", False),
    (TENANT,   "STILL not fixed!!! 3rd day already, this is ridiculous", False),
    (TENANT,   "can I legally withhold rent until the aircon is repaired?", False),
    (LANDLORD, "aiyo just send someone lah, dont bother me with these small things", False),
]


def _who(phone: str) -> str:
    p = find_party_by_phone(phone)
    return f"{p['name']} ({p['role']})" if p else phone


def _new_outbound(after_id: int):
    conn = connect()
    rows = conn.execute(
        "SELECT audience_role, channel, body FROM communications "
        "WHERE id > ? AND direction='out' ORDER BY id", (after_id,)).fetchall()
    conn.close()
    return rows


def _max_id() -> int:
    conn = connect()
    row = conn.execute("SELECT COALESCE(MAX(id),0) m FROM communications").fetchone()
    conn.close()
    return row["m"]


def main() -> None:
    st = router_status()
    print("=" * 72)
    print("PROPERTY AGENT — REAL-WORLD TRIAL RUN")
    print("=" * 72)
    print(f"Providers available : {st['providers']}")
    print(f"Task -> provider map : {st['mapping']}")
    brain = "DeepSeek V3" if st["providers"].get("deepseek") else "offline templates + keyword parser"
    print(f"Understanding/wording: {brain}")
    print("=" * 72)

    for i, (phone, text, media) in enumerate(SCRIPT, 1):
        before = _max_id()
        result = handle_inbound(phone, text, has_media=media)
        print(f"\n[{i}] {_who(phone)} texts the agent:")
        print(f"    \"{text}\"")
        verdicts = [a.get("verdict") for a in result.get("actions", [])] if isinstance(result, dict) else None
        if verdicts:
            print(f"    -> engine verdict(s): {', '.join(str(v) for v in verdicts)}")
        for r in _new_outbound(before):
            print(f"\n    AGENT -> {r['audience_role']}:")
            for line in r["body"].splitlines():
                print(f"      {line}")
        print("\n" + "-" * 72)

    print("\nTrial complete. Nothing was sent (dry-run). Inspect cases with:  python main.py status")


if __name__ == "__main__":
    main()
