# Stage 2 — state

- Milestone: complete.
- Done: stage-1 fully re-implemented in stage-2/ plus authorizations
  (create/capture/void/list, TTL + clock expiry, holds on available funds,
  7 idempotent paths), export/import accepting stage-1 exports, and the
  server-rendered UI (all routes, all data-testids, replay keys, latest
  refresh wins, available funds as headline number).
- Next: none for stage 2 (stages 3-4 are later objectives).
- Latest commit: see git log (final state commit).
- Final check run (service restarted from the committed tree): checks/s2-run-6 —
  stage 1 pass 147/147, stage 2 pass 35/35 (report.json "highest contiguous: 2";
  stage 3/4 fail by construction).
- Docker build: `docker build -t pocketful-stage2:local stage-2` → OK,
  image sha256:bbb52ad02baa284adb48d5ce05e6db71f54d146f606298659743d128d9681c8c
  (contents via docker create + export: app/app.py, app/ui.py, python3.12).

## Notes for later stages
- Services for checks: /tmp/svc.sh <stage-dir> <port> (double-fork daemon;
  port-based kill via fuser). Stage-2 target: 18091, stage-1 upgrade source: 18092.
- Harness stage-2 command needs --previous-base-url (stage-1 service) for the
  upgrade test.
- httpx/playwright in this VM need `env -u http(s)_proxy NO_PROXY=127.0.0.1,localhost`.
- UI: error elements are created/removed from the DOM (query_selector must find
  them only when present); list containers always render (visible empty states);
  fetch() to our own UI routes must send Accept: text/html or JSON comes back.
- python .format() does not recurse into substituted values — sub-templates with
  their own placeholders must be pre-formatted.
