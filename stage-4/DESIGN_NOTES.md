# Pocketful stage 4 — design notes (refunds + batch corrections)

Basis: stage-3 tree at b736ea6 (verified). Stage 4 = stage 3 + refunds and
correction batches. No new UI surface in the spec; the stage-3 UI carries
forward unchanged ("existing receipts and saved statements remain available
in their original form" = old payments/snapshots still serve unchanged).

## Closed decisions
- D1 Refunds POST /payments/{pid}/refunds — 9th idempotent path.
  Receiver (target's to_user_id) only. Precedence after idem resolution:
  amount field (required; integral 1..1e9 per the shared amount rule — the
  spec gives no special zero case for refunds) → 422; target unknown → 404;
  caller != receiver → 403; target is itself a refund → 422
  invalid_refund_target; amount > target's current corrected amount −
  refunded → 422 refund_exceeds_payment; receiver available < amount → 409
  insufficient_funds; commit atomically. (404-before-403 mirrors stage-3
  corrections, which passed reviewer review.)
- D2 Refund payment: new payment, from = target's to, to = target's from,
  amount, note/visibility copied from the TARGET, refund_of = target id,
  request_id/settlement_id/authorization_id = null, created_at = now,
  revisions=[rev1]. It is an ordinary payment: appears in feed/statements/
  historical views by its own created_at; conservation holds (existing
  money). Replaying returns the original 201 body with 200.
- D3 Refunded tracking: p["refunded"] on the TARGET, incremented on commit.
  Invariant refunded ≤ current amount maintained by: refund check (D1) and
  the new correction rule (D4). Import: use stored value, default 0 for
  stage-1..3 exports. Refund payments can't be corrected, so per-refund
  amounts never change after creation.
- D4 Correction constraint: a correction's new amount < target's refunded →
  422 refund_exceeds_payment (item-level, before affordability). Applies to
  BOTH single corrections and batch items. "Correction debits are checked
  against available funds" — already the case (stage 3).
- D5 correction_allowed() (single path) now also excludes refunds:
  settlement_id, authorization_id, refund_of must all be None, else 422
  linked_payment_immutable. Settlement members remain blocked on the single
  path; captures and refunds blocked everywhere.
- D6 Batches POST /correction-batches — 10th idempotent path. Operator
  check first (401 handled by auth layer; non-operator 403), then idem
  resolution, then: corrections list 1..32 + all-string payment_ids +
  distinct ids (else 422) → per-item validation in INPUT ORDER (missing/
  invalid fields 422; unknown 404; capture-or-refund 422
  linked_payment_immutable; stale 409; proposed amount < refunded 422) →
  settlement completeness: any member corrected ⇒ ALL members of that
  settlement present as items (else 422 incomplete_settlement) → members of
  one settlement share one effective instant (compare parsed datetimes;
  offset spellings may differ, else 422 validation_failed) → affordability:
  combined effect — for every affected user, available(user) + net_delta ≥ 0
  (net = (new−old) if user is receiver, (old−new) if sender), else 409
  insufficient_funds → historical_ok for every affected user at the shared
  recorded time, else 409 historical_overdraft. Reject: no revision, no
  balance, no idem claim.
- D7 Batch commit: shared recorded_dt = max(now, max(last recorded of every
  member) + 1µs) — strictly later than every member's previous recorded_at;
  recorded_at = its iso. Each member gets one new revision carrying
  correction_batch_id = "cb_" + uuid hex[:16]. Response 201:
  {correction_batch_id, recorded_at, revisions: [revision objects, input
  order]}.
- D8 revision_obj gains correction_batch_id (null for non-batch revisions,
  incl. rev 1). Import of stage-1..3 exports: default None.
- D9 payment_obj gains refund_of (null except refunds). Seeded payments:
  refund_of None, refunded 0 (fixtures never carry these fields).
- D10 Routing: PAYMENT_ACTIONS regex gains "refunds" (POST, idempotent
  via _do_write); POST /correction-batches in the authed dispatch.
- D11 Import compatibility: accept snapshots missing refund_of/refunded/
  correction_batch_id (stages 1–3 exports). Settlement membership,
  corrections, snapshots retained as before.
- D12 No UI change. Stage-3 UI + all stage-2 probes must keep passing.
  Stage-1/2/3 API invariants unchanged (payments keep original amount in
  receipts; snapshots frozen; etc.).

## Watch-list
- R1 Graded suite ≈ 5× the 5-test sample. Corners: refund of a capture,
  refund of a settlement member, refund replay, cumulative refund cap,
  correction-after-refund cap (refund_exceeds_payment), batch with partial
  settlement, batch with two members different instants, batch operator
  checks, batch replay, concurrent stale, refund by non-receiver 403,
  refund of refund 422, batch idempotency per operator, historical check on
  combined batch effect.
- R2 "Current" refund cap uses the target's CURRENT corrected amount
  (latest revision), which a batch may be changing for a DIFFERENT payment —
  refund caps recompute from the refunded counter (invariant-protected).
- R3 A refund's source is the receiver's AVAILABLE (stage-2 semantics) —
  held funds can't fund refunds.
