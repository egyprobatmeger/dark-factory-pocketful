# Stage 3 — state

- Milestone: in progress (stage 3 of 4).
- Done: stage-3/ copied from verified stage-2 (342e218); design notes written.
- Next: slice 1 — revision model in app.py (state shape, seeded created_at,
  openings, closed_at, current-amount helpers). Then slice 2 — corrections +
  revisions endpoint. Slice 3 — /me as_of/known_at + holds history. Slice 4 —
  /statement + snapshots. Then export/import widening, Dockerfile/RUN.md,
  harness loop, UI smoke.
- Latest commit: (pending first slice).
- Latest check run: none yet (s3-run-1 planned).

## Notes
- Services: /tmp/svc.sh <stage-dir> <port>; stage-3 target 18091, stage-2
  upgrade source 18092 (needed for the stage-3 upgrade import test).
- Stage-3 spec adds NO UI surface; stage-2 UI carries forward unchanged and
  all stage-2 behaviour/tests must keep passing.
- Build to the spec text, not the 62-line sample suite.
