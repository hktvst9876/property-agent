-- Property Agent AI — SQLite memory between runs.
-- "A case that isn't recorded didn't happen": every substantive action writes a
-- communications and/or decisions row.

-- People the agency talks to. Contact details here are NEVER shared across roles.
CREATE TABLE IF NOT EXISTS parties (
    id          INTEGER PRIMARY KEY,
    role        TEXT NOT NULL,          -- tenant|landlord|contractor|body_corporate|council|other
    name        TEXT NOT NULL,
    email       TEXT,
    phone       TEXT,
    trade       TEXT,                   -- for contractors: plumber|electrician|locksmith|general
    notes       TEXT,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Managed properties.
CREATE TABLE IF NOT EXISTS properties (
    id                    INTEGER PRIMARY KEY,
    address               TEXT NOT NULL,
    type                  TEXT DEFAULT 'condo',   -- hdb|condo|landed|commercial
    landlord_party_id     INTEGER REFERENCES parties(id),
    repair_threshold_sgd  REAL,                   -- landlord pre-approved spend ceiling
    jurisdiction          TEXT DEFAULT 'SG',
    notes                 TEXT,
    created_at            TEXT DEFAULT CURRENT_TIMESTAMP
);

-- A lease tying a tenant to a property for a term.
CREATE TABLE IF NOT EXISTS tenancies (
    id                    INTEGER PRIMARY KEY,
    property_id           INTEGER NOT NULL REFERENCES properties(id),
    tenant_party_id       INTEGER NOT NULL REFERENCES parties(id),
    start_date            TEXT,                   -- YYYY-MM-DD
    end_date              TEXT,                   -- YYYY-MM-DD (lease expiry)
    rent_sgd              REAL NOT NULL,
    rent_cycle            TEXT DEFAULT 'monthly',
    security_deposit_sgd  REAL DEFAULT 0,
    lease_notice_days     INTEGER DEFAULT 30,     -- contractual notice-to-remedy period
    minor_repair_cap_sgd  REAL,                   -- tenant's per-item minor repair responsibility
    status                TEXT DEFAULT 'active',  -- active|ending|ended
    ingoing_report_json   TEXT,                   -- condition at move-in
    created_at            TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Rent due/paid, one row per cycle.
CREATE TABLE IF NOT EXISTS rent_ledger (
    id              INTEGER PRIMARY KEY,
    tenancy_id      INTEGER NOT NULL REFERENCES tenancies(id),
    due_date        TEXT NOT NULL,                -- YYYY-MM-DD
    amount_sgd      REAL NOT NULL,
    paid_date       TEXT,                         -- NULL until paid
    paid_amount_sgd REAL DEFAULT 0,
    status          TEXT DEFAULT 'due',           -- due|paid|partial|overdue
    UNIQUE(tenancy_id, due_date)
);

-- A unit of work the agent is managing. The lifecycle hub.
CREATE TABLE IF NOT EXISTS cases (
    id                INTEGER PRIMARY KEY,
    type              TEXT NOT NULL,              -- maintenance|arrears|dispute|renewal|end_of_tenancy|general
    property_id       INTEGER REFERENCES properties(id),
    tenancy_id        INTEGER REFERENCES tenancies(id),
    opened_by_party_id INTEGER REFERENCES parties(id),
    status            TEXT DEFAULT 'open',        -- open|awaiting_party|awaiting_approval|awaiting_contractor|resolved|escalated
    urgency           TEXT,                       -- EMERGENCY|URGENT|ROUTINE
    summary           TEXT,
    next_action       TEXT,
    next_action_at    TEXT,
    escalated_reason  TEXT,
    created_at        TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at        TEXT DEFAULT CURRENT_TIMESTAMP
);

-- The audit trail. Every inbound and outbound message.
CREATE TABLE IF NOT EXISTS communications (
    id            INTEGER PRIMARY KEY,
    case_id       INTEGER REFERENCES cases(id),
    direction     TEXT NOT NULL,                 -- in|out
    channel       TEXT,                          -- email|sms|telegram|phone|portal
    from_party_id INTEGER REFERENCES parties(id),
    to_party_id   INTEGER REFERENCES parties(id),
    audience_role TEXT,
    subject       TEXT,
    body          TEXT,
    media_json    TEXT,                          -- e.g. {"has_media": true} for inbound photos
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Every deterministic verdict archived (mirror of store-tester decisions).
CREATE TABLE IF NOT EXISTS decisions (
    id            INTEGER PRIMARY KEY,
    case_id       INTEGER REFERENCES cases(id),
    engine        TEXT NOT NULL,                 -- triage|maintenance|arrears|dispute|renewal|end_of_tenancy|legal_guard
    verdict       TEXT NOT NULL,
    reason        TEXT,
    metrics_json  TEXT,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Human approval gate. Nothing money-/legal-touching executes without
-- status='approved'. The Telegram bot reads pending rows, writes resolutions.
CREATE TABLE IF NOT EXISTS approvals (
    id            INTEGER PRIMARY KEY,
    case_id       INTEGER REFERENCES cases(id),
    action        TEXT NOT NULL,                 -- dispatch_contractor|issue_notice|deposit_claim|escalate_human|raise_rent|non_renewal
    payload_json  TEXT,
    status        TEXT DEFAULT 'pending',        -- pending|approved|rejected|executed
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    resolved_at   TEXT,
    resolved_by   TEXT
);

-- Complaints. complainant_party_id is NEVER surfaced to other parties when
-- anonymity=1. "We received a complaint" is all the subject party is told.
CREATE TABLE IF NOT EXISTS complaints (
    id                  INTEGER PRIMARY KEY,
    case_id             INTEGER REFERENCES cases(id),
    complainant_party_id INTEGER REFERENCES parties(id),
    subject_party_id    INTEGER REFERENCES parties(id),
    category            TEXT,                    -- noise|damage|behaviour|other
    details             TEXT,
    evidence_json       TEXT,
    anonymity           INTEGER DEFAULT 1,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ledger_tenancy ON rent_ledger(tenancy_id, due_date);
CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
CREATE INDEX IF NOT EXISTS idx_decisions_case ON decisions(case_id, created_at);
CREATE INDEX IF NOT EXISTS idx_approvals_pending ON approvals(status);
CREATE INDEX IF NOT EXISTS idx_comms_case ON communications(case_id, created_at);
