# Property Agent AI (Singapore)

An autonomous property-management agent that sits between landlords, tenants,
contractors, and authorities across the whole tenancy lifecycle — maintenance,
rent arrears, disputes, renewals, and end-of-tenancy.

It follows the same spine as the `store-tester` project in this workspace:

> **Deterministic engines decide. The LLM only drafts. A human approves anything
> that touches money or the law.**

## Why it's built this way

- **`core/` engines make every verdict** (urgency, repair authority, arrears
  stage, dispute handling, renewal, deposit deductions). They are pure functions
  with no LLM in the loop, so behaviour is testable and predictable.
- **`llm/drafter.py` only phrases** the verdict for the audience (warm to a
  tenant, businesslike to a landlord, direct to a contractor). It is fed the
  verdict as a fixed fact it may not change, and it works offline via templates
  when no API key is set.
- **`approvals/telegram_bot.py` is the gate.** Over-threshold repairs, formal
  notices, rent raises, deposit claims, and escalations all wait for a one-tap
  Approve/Reject. Nothing money-/legal-touching executes until approved.
- **`db/` is the memory.** Every case, message, decision, and approval is stored,
  so "a case that isn't recorded didn't happen" holds.

## The legal guardrail (`core/legal_guard.py`)

The agent **never gives legal advice and never answers a legal question** — those
get a referral. It may surface *factual* legal information **only** once a party
is genuinely at risk (e.g. 14+ days in arrears, a deposit dispute), and every
such statement carries:

1. a **disclaimer** that it is general information to be verified with a qualified
   professional, and
2. a **non-empty list of sources**.

If no source is available, it **refuses to state anything and escalates** to a
human. Singapore facts and their sources live in `jurisdictions/singapore.py`.

## Quick start

```bash
pip install -r requirements.txt
python main.py init-db
python main.py seed          # demo HDB property, tenancy, and overdue ledger
python main.py status
```

**Replace your texting (the main use case):** feed a real free-text message in and
see what the agent texts back — offline, no browser, nothing sent:

```bash
python main.py simulate "+6592220000" "aircon spoil liao, so hot"        # Singlish ok
python main.py simulate "+6592220000" "any update? still waiting"        # continues the SAME case, gives the ETA
python main.py simulate "+6592220000" "still not fixed!!"               # chase again -> escalates to a human
python main.py simulate "+6592220000" "rent late sorry and the toilet is choked"  # TWO issues, two actions
python main.py simulate "+6592220000" "ceiling is leaking, see pic" --media        # photo noted + sent to contractor
python main.py simulate "+6592220000" "can I legally withhold rent?"   # -> refused (referral)
```

It holds a conversation: a reply threads onto the open case instead of starting
over, repeated chasing escalates, and one message can trigger several actions. The
agent resolves the sender, understands the message (`core/intake_parser.py`), runs
the right engine(s), and drafts a mood-aware reply to each party — all without a model.

**Following through on its own:**

```bash
python main.py sweep arrears      # nudge/escalate overdue rent across all tenancies
python main.py sweep renewals     # open renewals ~90 days before expiry
python main.py sweep followups    # chase contractors whose ETA has passed; escalate if still stalled
```

Or run a pre-structured situation end-to-end:

```bash
# Emergency maintenance -> dispatched immediately, landlord notified
python main.py intake '{"type":"maintenance","tenancy_id":1,"description":"I smell gas in the kitchen","estimated_cost_sgd":250,"trade":"plumber"}'

# Over-threshold repair -> queued for landlord approval
python main.py intake '{"type":"maintenance","tenancy_id":1,"description":"Leaking tap under sink","estimated_cost_sgd":1200}'

# A direct legal question is never answered
python main.py intake '{"type":"legal_question","description":"Can I legally evict my tenant?"}'
```

## Tests

The engines need no API key or network:

```bash
python -m pytest -q
```

## Going live on WhatsApp (no paid API)

The agent texts people by driving **WhatsApp Web** in a real browser with a
persistent login — no Twilio, no Meta Business API, no fees.

> ⚠️ This automates the WhatsApp *Web* client, which is unofficial and against
> WhatsApp's Terms of Service. Heavy/spammy use can get your number banned. Keep
> it human-paced. (You chose this channel knowing the tradeoff.)

```bash
pip install selenium          # only needed for live mode; Chrome must be installed
# in .env:
#   WHATSAPP_MODE=live
#   COMMS_DRY_RUN=0
python main.py listen         # opens WhatsApp Web; scan the QR with your phone once
```

`listen` polls for new messages and runs each through the same pipeline, replying
on the same chat. Set `WHATSAPP_PROFILE_DIR` to keep the login between runs.

**The inbound side is the fragile part.** Reading messages depends on WhatsApp's
HTML, which changes; the selectors live at the top of `integrations/whatsapp.py`
so there's one place to fix when a read breaks. Sending is robust.

## How the replies are written

By default the agent uses **built-in, mood-aware templates** — no model, no API.
They read the sender's message and open with appropriate empathy: an angry or
distressed tenant is acknowledged first, a calm one isn't. The decision content and
any legal facts are filled in by the engines.

```bash
python main.py simulate "+6592220000" "the aircon is STILL broken, third time!! fix it"
# -> reply opens with: "I'm really sorry for the trouble — I completely understand
#    the frustration..." then the specifics (contractor, ETA).
```

This is keyword-based, so it catches common moods, not every nuance. If you ever
want fully natural, LLM-written wording, set `ANTHROPIC_API_KEY` (and
`pip install anthropic`); the drafter will use it and fall back to templates if it's
unavailable. The engines and legal guardrail are unchanged either way.

## Other optional toggles

- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — the approval gate for notices,
  over-threshold repairs, rent raises, deposit claims, and escalations. Run the
  poller with `python main.py bot`.
- `COMMS_DRY_RUN` — `1` (default) logs messages but never sends. Set to `0` only
  when you mean for the agent to actually message people.

## Layout

```
config.py          thresholds, jurisdiction, model + provider map
core/              deterministic engines + intake_parser + legal_guard + case transitions
jurisdictions/     SG legal facts with sources (swap-in design for AU/NZ)
llm/               router (decisions locked to Claude) + drafter + prompts
integrations/      whatsapp (Web channel) + comms (routing) + contractors (mock)
approvals/         Telegram one-tap approval gate
db/                SQLite schema + helpers (the agent's memory)
orchestrator.py    handle_inbound() (threading, multi-issue, follow-ups) + handle_event() + sweeps + listen()
main.py            CLI (init-db, seed, simulate, listen, intake, sweep, status, bot)
scripts/seed_demo.py
tests/
```
