# Stage 2 — state

- Milestone: complete (re-work after reviewer FAIL: D1/D2/D3 fixed).
- Done: all stage-2 work plus the reviewer fixes —
  - D1: void handler used undefined `errEl`; void now goes through
    `actThenRefresh(r, "authorization-error", "/authorizations")`: refresh
    first, then show the refusal so the rerender cannot wipe it. A voided
    item updates in place without a manual reload.
  - D2: capture input pre-filled with raw minor units; now pre-filled with
    the decimal remaining amount (`amount_text`), so a plain capture click
    submits the remaining amount. Same refresh-then-error ordering applied;
    on success the wallet+feed fragments refresh too.
  - D3: RUN.md was a byte-identical stage-1 copy; now a real stage-2
    document (stage-2 surface, both Docker + native run, stage-2 harness
    command with --previous-base-url).
  - requests pay/decline/cancel actions got the same refresh-then-error
    ordering (same latent race).
- Next: none for stage 2 (stages 3-4 are later objectives).
- Latest commit: see git log (final state commit).
- Final check run (services restarted from the committed tree): checks/s2-run-8 —
  stage 1 pass 147/147, stage 2 pass 35/35 (report.json "highest contiguous: 2";
  stage 3/4 fail by construction).
- UI probes (playwright, demonstrated paths): 17/17 pass — authorize from UI,
  decimal pre-fill, plain capture click, captured state + feed, void updates
  in place, refused capture shows authorization-error and survives the rerender,
  refused void (403) with payer still able to void, holds/available accounting.
- Docker build: `docker build -t pocketful-stage2:local stage-2` → OK,
  image sha256:4dd562bf7042 (tag pocketful-stage2:local); image app/app.py +
  app/ui.py md5-identical to the committed tree.

## Notes for later stages
- Services for checks: /tmp/svc.sh <stage-dir> <port> (double-fork daemon;
  port-based kill via fuser). Stage-2 target: 18091, stage-1 upgrade source: 18092.
- Harness stage-2 command needs --previous-base-url (stage-1 service) for the
  upgrade test.
- httpx/playwright in this VM need `env -u http(s)_proxy NO_PROXY=127.0.0.1,localhost`.
- UI: error elements are created/removed from the DOM (query_selector must find
  them only when present); list containers always render (visible empty states);
  fetch() to our own UI routes must send Accept: text/html or JSON comes back.
- UI actions whose buttons live inside the re-rendered area must refresh first
  and show errors after the rerender (actThenRefresh), or the error is wiped.
- python .format() does not recurse into substituted values — sub-templates with
  their own placeholders must be pre-formatted.
