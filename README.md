# Pocketful — built by an AI Dark Factory

**WeAreDevelopers × BAND — AI Dark Factory hackathon, "pocketful" track.**

This repository is the complete output of one autonomous agent-team run:
a payments service built in four stages by three AI seats coordinating in
a single Band room, launched by exactly one human message and completed
with no further human input.

## What Pocketful is

Pocketful is a staged payments-service specification. Each `stage-N/`
folder in this repository is a complete, self-contained, buildable
service implementing that stage's specification:

| Stage | Adds |
|-------|------|
| `stage-1/` | Core in-memory payments service: accounts, payments, payment requests, splits, settlements, export/import, idempotency |
| `stage-2/` | Payment authorizations (create / capture / void), holds, wallet UI |
| `stage-3/` | Payment corrections, per-payment revision history, historical `as_of` queries, statements, snapshots |
| `stage-4/` | Refunds (linked by `refund_of`) and batch corrections (up to 32 payments, `correction_batch_id`) — the final, complete service |

Every stage is a single-file Python 3 application (`app.py`, plus `ui.py`
from stage 2 on) using **only the Python standard library**: no runtime
dependencies, no build steps, no outbound network access. State is
in-memory; a restart starts empty.

## The factory

The service was built by a three-seat agent team working in one Band
room:

- **coordinator** — breaks the run into stages, dispatches work, closes
  stages only on the reviewer's verdict
- **implementer** — designs, builds and self-tests each stage in slices
- **reviewer** — independently re-measures each stage against the official
  checks *and* reads the specification for what the checks do not cover,
  then issues a PASS / FAIL verdict

All three seats ran the **opencode** harness with the model
**qwen/qwen3.8-27b**. Their mandates — the standing instructions each
seat worked under — are in [`mandates/`](mandates/), with the model that
actually ran named in each file's header.

The entire run was launched by a single human dispatch message on
2026-10-05 at 09:50:42 CEST; after that message there were no further
human messages in the room — every later post is seat-to-seat traffic.
(How the run was hosted, and the infrastructure events around it, are
described openly in [`FACTORY.md`](FACTORY.md).) The full story — timeline, verification results, the two
review FAIL → repair → PASS loops, measured cost and time, failures and
lessons — is in [`FACTORY.md`](FACTORY.md). The exported room log is in
`room.json`. The git history of this repository is the team's own work
record: every stage was committed slice by slice by the seats themselves.

## Repository structure

```
README.md          this file
FACTORY.md         how the factory ran: design decisions, results, cost, failures
room.json          the Band room log (unedited export)
mandates/          coordinator.md, implementer.md, reviewer.md
stage-1/ … stage-4/
    app.py         the service (ui.py joins from stage 2)
    Dockerfile     RUN-free image definition (python:3.12-alpine)
    RUN.md         exact build / run / verify commands for the stage
    STATE.md       the seat's own save-point notes for that stage
    DESIGN_NOTES.md design decisions taken while building the stage
```

## Running a stage

Each stage runs the same way; see that stage's `RUN.md` for its exact
commands. With Docker:

```sh
cd stage-4
docker build -t pocketful-stage4 .
docker run --rm -p 8080:8080 -e PORT=8080 pocketful-stage4
curl http://127.0.0.1:8080/health
# -> {"status": "ok"}
```

Or natively (Python 3.12):

```sh
cd stage-4
PORT=18091 python3 app.py
```

The service listens on `0.0.0.0:$PORT` (default 8080). Browser requests
(`Accept: text/html`) receive the wallet UI; API clients receive JSON on
the same paths.

## Verification

Measured with the official harness on the final revision (`16a6832`):

- Stage 1: **147/147**, Stage 2: **35/35**, Stage 3: **6/6**, Stage 4: **5/5**
- `highest_contiguous = 4`

After the run, as part of preparing this submission, EVORA re-measured
the closing revision from a fresh clone with the official harness:
147/147 + 35/35 + 6/6 + 5/5, `highest_contiguous = 4`. (On the first
attempt one stage-2 browser probe timed out at 34/35; a clean re-run
minutes later measured the full result above.) Each stage's Docker image builds
from a clean container (the stage-1 image included — it needs no network).

## Cost and time

- Total wall-clock time: **~7 hours 14 minutes** (09:50:42 → 17:04:49 CEST, per the room log)
- Account spend over the run window: **10.16 USD**, derived from the provider's billing totals

Details and methodology are in [`FACTORY.md`](FACTORY.md).
