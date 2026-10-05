# Pocketful stage 3 — design notes (statements + payment corrections)

Basis: stage-2 tree at 342e218 (verified). stage-3 = stage-2 + revision model,
historical queries, statements, snapshots. UI: stage-3 spec adds no UI surface —
the stage-2 UI carries forward unchanged (all its probes must keep passing).

## Closed decisions
- D1 Payment record: keep `amount` = ORIGINAL (rev 1) amount (feed shows the
  original payment; receipts unchanged). Add `revisions`: list, ascending
  {revision, amount, effective_at(str), effective_dt, recorded_at(str),
  recorded_dt, reason}. Current amount = last revision.
- D2 Timestamps: full microsecond precision internally; serialize with
  `isoformat()` (whole-second dts have no fraction; API times usually carry a
  fraction). RFC 3339 allows fractions; spec examples show seconds but never
  forbid fractions. This is what makes "recorded times strictly increase"
  satisfiable: on append, recorded_dt = max(now, prev_recorded_dt + 1µs).
- D3 created_at on seeded payments: optional in fixture; must be RFC3339 WITH
  offset, not later than reset time (else 422, state unchanged). Omission =
  reset time. Stored string echoed verbatim in responses.
- D4 Opening balances: s.opening[uid] = (seeded user) seeded_balance − Σ
  delta1 over SEEDED payments only (flag `seeded: True`); (new user) 0.
  Corrections never change opening (rev-1 based). Captures/settlements are
  never "seeded" (fixture has no settlement/capture payments; seeded
  authorizations carry payment_ids referencing seeded payments — but those
  links never exist in a fixture; ignore).
- D5 selected revision per (payment, K=known_at or read-start now): latest
  revision with recorded_dt ≤ K; none → payment contributes NOTHING (not
  even rev 1, when K < created).
- D6 balance_at(caller, T, K, inclusive): s.opening[caller] + Σ sign×amount of
  selected revisions with eff ≤ T (inclusive) or eff < T (exclusive).
  /me as_of = inclusive. statement opening = exclusive at `from`;
  closing = exclusive at `to` (== opening + Σ window deltas, since window is
  [from,to)). /me without as_of: T = request start, inclusive.
- D7 from>to: treat as empty window; opening = balance before from, closing =
  balance before to (both defined); entries []. (Math convention [from,to)∅.)
- D8 held_at(caller, T, K): Σ over authorizations a where from=caller and
  a.created_dt ≤ K:
    caps = Σ capture-amounts c where c.time ≤ min(T, K)
    (capture time = created_dt of the linked capture payment)
    if a.status == "open":
        if T ≥ a.expires_dt: 0        # open holds expire at deadline,
        else: max(0, a.amount − caps) # even for T beyond now
    else:  # closed (voided/captured/expired)
        cl = a.closed_dt (event time; seeded closed → expires_dt, and seeded
        closed holds contribute 0 for all T — "need not reconstruct")
        if cl ≤ K and T ≥ cl: 0
        elif T ≥ a.expires_dt: 0     # deadline known once creation known
        else: max(0, a.amount − caps)
  /me without as_of: T = request start. All four money fields = total,
  total, total−held, held.
- D9 closed_at on authorization records: null while open; set at closure
  (void → now; final capture → that capture's created_dt; sweep expiry →
  expires_dt). Exposed in authorization_obj as RFC3339 or null.
- D10 GET /me: as_of and known_at both optional. Each, when present, must
  parse as RFC3339 WITH explicit offset (naive/bare date/empty → 422
  validation_failed); Z accepted. Response echoes each supplied param
  EXACTLY as given (raw decoded query string) as field as_of / known_at.
  Neither supplied → existing shape, no new fields (stage-1 test asserts
  "as_of" absent).
- D11 GET /statement params: from, to (optional; defaults −inf / read-start
  now), known_at (optional, default read-start now), limit/offset (as
  /requests), snapshot (optional token). Window [from,to). Entries sorted by
  (selected effective_dt, payment_id) ASC. Entry = {payment: payment_obj with
  amount OVERRIDDEN to selected amount, delta (−amt sender / +amt receiver),
  balance_after (cumulative over full window from opening), revision,
  effective_at, recorded_at}. Response: {opening_balance, entries,
  closing_balance, has_more, snapshot (first read only), known_at echo when
  given}. from>to → empty window (D7).
- D12 Snapshot: first (non-snapshot) read freezes {user, from_dt, to_dt,
  known_dt (or None), opening, closing, entries (full, pre-pagination),
  total}. Token "snap_"+uuid4hex. state.snapshots[token] = {...}; owned by
  user. Page request: snapshot + only limit/offset (from/to/known_at present
  → 422); unknown/foreign/pre-reset token → 404. Page responses carry
  opening/closing/has_more, entries slice, NO snapshot field. Tokens die on
  reset/import (new state object) and are exported+imported unchanged.
- D13 Corrections POST /payments/{pid}/corrections — 8th idempotent path.
  Body all required: expected_revision (int>0; wrong type 400, ≤0 422),
  amount (0..1e9, integral; invalid incl. string/bool → 422 per amount rule),
  effective_at (string, RFC3339 w/ offset, ≤ now; else 422), reason (string
  1..200; wrong type 400, else 422). Order after idem resolution: field
  validation → 404 unknown payment → 403 non-sender → 422
  linked_payment_immutable (settlement member OR capture) → 409
  stale_revision (expected != len(revisions)) → 409 insufficient_funds
  (debtor's CURRENT available < |diff|; debtor = sender if increase,
  receiver if decrease) → 409 historical_overdraft → commit. Commit:
  append revision {n+1, amount, effective_at raw, recorded_at now-bumped,
  reason}; apply diff atomically (sender/receiver balances) — conservation
  preserved (same two wallets). 201 {payment_id, revision, amount,
  effective_at, recorded_at, reason}. Failed validation claims no key.
- D14 historical_overdraft check (under lock, BEFORE commit): with the
  would-be new revision, for each of sender/receiver compute boundaries =
  {effective_dt of every selected (all-known) revision of payments involving
  the user} ∪ {hold event times of the user's authorizations (created,
  capture times, closed, expires)}; at each T: total = balance_at(user, T,
  now, inclusive) and available = total − held_at(user, T, now) must be ≥ 0.
  (Functions are piecewise-constant between boundaries, so boundaries suffice.)
  New revision's recorded_dt = now ⇒ it is "known" at K=now.
- D15 GET /payments/{pid}/revisions: 401 no token; 404 unknown OR caller not
  one of the two parties (even public). {"revisions":[{revision, amount,
  effective_at, recorded_at, reason}...]} including rev 1 (reason "").
- D16 Export: payments gain revisions (str times only) + seeded flag;
  authorizations gain closed_at + created_at; state gains snapshots
  (serializable). Import: accept stage-1 exports (no authorizations —
  already ok) and stage-2 exports (no revisions → synthesize rev 1 from
  amount+created_at, seeded only if the record came from a seeded payment —
  mark `seeded` when rebuilding? stage-2 snapshot payments have no `seeded`
  flag… FIX: seed-ness is derivable: a payment is seeded iff its id appears
  in the fixture… not available at import. SOLUTION: carry `seeded` in the
  stage-3 export; when importing a stage-2 snapshot, treat a payment as
  seeded iff created_at ≤ ... unknowable. Alternative: opening balance must
  work after importing a stage-2 export: stage-2 snapshot users keep their
  current balances; there is NO way to recover per-user seeded opening after
  the fact from a stage-2 export — BUT do we need to? "The ledger must import
  and account for authorizations and captures" + "accept exports produced by
  the same team's stage-1 or stage-2 service" + stage-1 §10: "identities,
  timestamps and monetary records must not be regenerated or replayed
  against an already-net balance." Key: opening balance semantics for a
  USER after import — the import check will query as_of/statement on the
  imported service. For that to be right, opening must be reconstructible.
  ⇒ EXPORT the opening balances explicitly (s.opening dict) in the stage-3
  snapshot, and import them. A stage-2 import (no opening field) → derive:
  opening[uid] = current balance − Σ net of ALL payments involving uid (all
  at their rev-1/current amount, since no revisions in stage-2 export). That
  is exact for a stage-2 state (every payment's full history = itself). ✓
  Same derivation also = "already-net balance, not replayed."
- D17 Seeded authorizations gain optional created_at (RFC3339 w/ offset,
  default reset time; future allowed — spec constrains only expiry
  placement). Seeded closed: closed_at = expires_at, contributes 0 hold.
- D18 Routing additions: GET /statement, POST /payments/{id}/corrections
  (AUTH_ACTIONS-style regex), GET /payments/{id}/revisions. All 401-checked
  (authed paths). Idempotency on corrections via _do_write (8th path).
- D19 /me with only known_at (no as_of): T = request start, K = known_at.
  Echo known_at.
- D20 Stage-1/2 exact-shape invariants kept: payment_obj unchanged (amount =
  original), /me without params unchanged, GET /activity unchanged (original
  payments, created_at order), feeds never show corrections.

## Watch-list (risks)
- R1 Graded stage-3 suite ≈ 5× the sample. Highest-risk corners: opening
  balance on page 2 (frozen via snapshot), as_of before earliest seeded
  payment (opening), statement excluding third-party public payments,
  stale-revision races, historical overdraft on multi-boundary timelines,
  snapshot 404 after reset, known_at before a correction (old amount shown),
  correction moving an entry across the window (fresh read changes, snapshot
  doesn't).
- R2 recorded_at strictness under same-second corrections → µs bump (D2/D13).
- R3 "balance_after" must be computed over the FULL window even when the
  page is partial (D11) — compute full list first, then slice.
- R4 from/to/known_at may be FUTURE — no clamping anywhere (only the
  correction's effective_at is bounded by now).
- R5 available-never-negative invariant includes historical views (D14).
