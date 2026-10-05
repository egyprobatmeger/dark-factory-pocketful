# Stage 3 — state

- Milestone: complete (stage 3 of 4).
- Done: stage-1/2 fully working + stage-3 widening:
  - revision model (rev 1 = original; per-payment history; recorded_at strictly
    increasing via µs bump), corrections as 8th idempotent path (403/404/422
    linked_payment_immutable/409 stale_revision/409 insufficient_funds/409
    historical_overdraft, all-or-nothing), GET /payments/{id}/revisions
  - historical engine: balance_at / held_at over selected revisions
    (known_at) and effective times (as_of); /me as_of+known_at with echo;
    seeded created_at (future → 422); opening = ending − net of original
    seeded payments
  - GET /statement: [from,to) window, oldest first (id tie-break), per-entry
    balance_after over the FULL window, opening/closing, revision fields,
    snapshot tokens (frozen paging, per-user, 404/422 rules, dead on reset,
    exported/imported)
  - export/import: revisions + opening + snapshots serialized; stage-1/2
    exports importable (rev synthesized from amount+created_at, openings
    derived from net balances)
  - authorizations gain closed_at; lifecycle events set it (void/capture/
    sweep expiry)
- Next: none for stage 3 (stage 4 is a later objective).
- Latest commit: see git log (final state commit).
- Final check run (services restarted from the committed tree): checks/s3-run-1 —
  stage 1 pass 147/147, stage 2 pass 35/35, stage 3 pass 6/6, highest
  contiguous 3 (stage 4 fails by construction: refunds/correction-batches
  are stage-4 surface).
- Probes: /tmp/opencode/api-probe-stage3.py — 112/112 (model-computed
  expectations; opening on page 2, as_of before earliest payment, third-party
  exclusion, stale-revision races, historical overdraft both debit directions,
  current-check precedence, snapshot freeze/404/422, known_at views,
  full export/import round trip incl. pre-export token + replay, stage-2
  export import). Stage-2 UI regression: 17/17.
- Docker build: `docker build -t pocketful-stage3:local stage-3` → OK,
  image sha256:22a526c210b5; rootfs app/app.py + app/ui.py md5-identical to
  the committed tree. Base image python:3.12-alpine re-imported after another
  image-store wipe (2026-10-05, second time this session).

## Notes for later stages
- /tmp gets wiped between sessions (svc.sh, probes, daemonizer all lost once);
  keep the service starter + probes reproducible from this repo knowledge:
  /tmp/svc.sh (double-fork, fuser port kill), daemonize-dockerd.py (double
  fork dockerd with vfs/iptables=false), import-py312-alpine.py (curl
  token/manifest/blobs → docker import).
- Historical check subtlety: step functions are right-continuous — sample
  each boundary at t AND t+1µs; and the check must run at the NEW revision's
  recorded time (it is known from then).
- now_rfc3339() is microsecond precision (whole-second dts print without
  fraction); event times (void/capture/expiry) use it for exactness.
- payment_obj(s, p, amount=...) overrides amount for statement entries
  (selected revision amount); feed/receipts always use the original.
- httpx cookie jar: login() auto-saves the session cookie and replays it —
  "no token" probes need http.cookies.clear() first.
- httpx Client + proxy env: always the env -u prefix (see AGENTS.md).
