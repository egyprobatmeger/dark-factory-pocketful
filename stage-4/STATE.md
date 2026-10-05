# Stage 4 — state

- Milestone: complete (final stage of the pocketful track).
- Done: stage-1/2/3 fully working + stage-4 widening:
  - POST /payments/{id}/refunds (9th idempotent path): receiver-only
    reverse payment linked by refund_of, note/visibility copied, cumulative
    cap vs current corrected amount (refund_exceeds_payment), available
    funds check, never reopens requests/authorizations or restores holds,
    refunds of refunds 422 invalid_refund_target
  - POST /correction-batches (10th idempotent path): operator-only,
    1..32 distinct items, per-item validation in input order, settlement
    completeness (incomplete_settlement), shared settlement effective
    instant, combined current-affordability and historical checks,
    shared recorded_at strictly after every member's previous one,
    revision objects carry correction_batch_id
  - payments expose refund_of (null except refunds); revisions expose
    correction_batch_id (null except batch corrections)
  - a correction (single or batch) cannot reduce a payment below its
    already-refunded amount (refund_exceeds_payment); captures and
    refunds are immutable to corrections
  - export/import accepts stage-1..3 exports (new fields default) and
    round-trips stage-4 state
- Next: none — stage 4 is the final stage.
- Latest commit: see git log (final state commit).
- Final check run (services restarted from the committed tree): checks/s4-run-1 —
  stage 1 pass 147/147, stage 2 pass 35/35, stage 3 pass 6/6, stage 4 pass
  5/5, report.json "highest contiguous: 4".
- Probes: /tmp/opencode/api-probe-stage4.py — 60/60 (refund reverse-payment
  shape/copy/replay, 403/404/invalid-target/amount/cap/available, refund of
  capture without hold restore, refund of settlement member, refund and
  capture immutability to corrections, correction-below-refunded floor,
  batch shape/replay/403/400/404/409/duplicate/empty, partial vs full
  settlement, different vs shared instants, over-draft, recorded_at
  ordering, stage-3 export import incl. frozen snapshot token).
  Regression against the stage-4 service: stage-3 probe suite 117/117,
  stage-2 UI playwright probe 17/17.
- Docker build: `docker build -t pocketful-stage4:local stage-4` → OK,
  image sha256:03f95a21681a; rootfs app/app.py + app/ui.py md5-identical to
  the committed tree.

## Notes for later work
- /tmp gets wiped between sessions (svc.sh, probes, daemonizer, base image);
  keep them reproducible: /tmp/svc.sh (double-fork, fuser port kill),
  daemonize-dockerd.py, import-py312-alpine.py (see AGENTS.md).
- Refunds move from the receiver's AVAILABLE (held funds can't fund a
  refund); a received payment's own value always covers its own refund
  unless the receiver has since spent/holded those funds.
- Batch recorded_at = max(now, max(last recorded of members) + 1µs).
- The harness stage-N upgrade test imports the PREVIOUS stage service's
  export: stage-4 must import stage-1..3 exports (new fields absent).
