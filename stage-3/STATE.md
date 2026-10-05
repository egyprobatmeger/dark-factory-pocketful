# Stage 3 — state

- Milestone: complete (re-work after reviewer FAIL: D1 fixed).
- Done: all stage-3 work plus the D1 fix — held_at() now gates each hold on
  the effective time: `t < created_dt` → not held ("A hold starts at
  authorization creation"), mirroring the expiry gate. Reviewer-demonstrated
  consequences verified in-probe: /me?as_of before a hold's creation reports
  held 0 / available = total, and the previously over-rejected legal
  correction (decrease effective before the hold existed) is accepted.
  historical_ok re-checked: boundaries already include created_dt, and the
  gate only reduces held for t < created_dt, so legal corrections cannot be
  newly over-rejected.
- Next: none for stage 3 (stage 4 is a later objective).
- Latest commit: see git log (final state commit).
- Final check run (services restarted from the committed tree): checks/s3-run-3 —
  stage 1 pass 147/147, stage 2 pass 35/35, stage 3 pass 6/6, highest
  contiguous 3 (stage 4 fails by construction).
- Probes: /tmp/opencode/api-probe-stage3.py — 117/117 (112 original + 5 D1:
  seeded hold created AFTER a payment's effective time; as_of before
  creation → held 0; as_of after → hold active; the D1 legal decrease 201;
  balances after). Stage-2 UI regression was 17/17 at s3-run-1 (UI unchanged
  by this fix).
- Docker build: `docker build -t pocketful-stage3:local stage-3` → OK,
  image sha256:7995ab74623d; rootfs app/app.py md5-identical to the
  committed tree (contains the D1 fix).

## Notes for later stages
- /tmp gets wiped between sessions (svc.sh, probes, daemonizer all lost
  repeatedly); keep these reproducible: /tmp/svc.sh (double-fork, fuser
  port kill), daemonize-dockerd.py, import-py312-alpine.py (see earlier
  STATE notes / AGENTS.md).
- Historical held() must gate on BOTH gates: known (created_dt ≤ known_at)
  AND effective (t ≥ created_dt) — one alone leaves a window where a hold
  counts before it starts (D1) or after it expires.
- Historical check subtlety: step functions are right-continuous — sample
  each boundary at t AND t+1µs; and the check runs at the NEW revision's
  recorded time (it is known from then).
- now_rfc3339() is microsecond precision; event times use it for exactness.
- payment_obj(s, p, amount=...) overrides amount for statement entries
  (selected revision amount); feed/receipts always use the original.
- httpx cookie jar: login() auto-saves the session cookie and replays it —
  "no token" probes need http.cookies.clear() first.
