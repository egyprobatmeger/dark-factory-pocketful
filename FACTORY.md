# FACTORY.md — how this factory ran

**Track:** pocketful (WeAreDevelopers × BAND — AI Dark Factory)
**Run date:** 2026-10-05
**Final revision:** `16a6832`

## The team and the setup

Three agent seats worked in a single Band room:

- **coordinator** — dispatched each stage, and closed a stage only after
  the reviewer's verdict and its own closing report
- **implementer** — built each stage
- **reviewer** — independently verified each stage and issued the verdict

All three seats ran the same harness and model — **opencode** with
**qwen/qwen3.8-27b** — as the rules expressly allow ("all seats may use
the same runtime/model"). Each seat worked under a written mandate; the
three mandate files are in `mandates/`, and each header names the model
that actually ran.

## One human message in the room

The run was launched by a **single human dispatch message on 2026-10-05
at 09:50:42 CEST**. After that message there were **no further human
messages in the room**: no steering, no approvals, no hints, no re-runs
were posted. Every handoff, verdict and closing report in the room log
(`room.json`) is seat-to-seat traffic between the three agents.

That statement is about the room, and it is the whole of it. Things did
happen *outside* the room, on the infrastructure the seats ran on —
restarts after two machine swaps, and one session-rotation attempt
during stage 4. Those operations are disclosed item by item under
"Infrastructure events" and "Who EVORA is" below; none of them put a
message into the room or changed the content of the work.

## Timeline (all times CEST, 2026-10-05, from the room record)

Message ids are the Band message ids of the posts, as recorded in the
seats' session logs; they can be matched against `room.json`.

| Time | Event |
|------|-------|
| 09:50:42 | **Single human dispatch** (the run's only human message) |
| 09:51:11 | Coordinator: STAGE 1 HANDOFF (msg `8a468743`) |
| 11:06:50 | Reviewer: STAGE 1 VERDICT: **PASS** (msg `0e2d2b66`) |
| 11:07:23 | Coordinator: STAGE 1 REPORT (msg `d64cb297`) + STAGE 2 HANDOFF (msg `ff5e7e70`) |
| 12:30:55 | Reviewer: STAGE 2 VERDICT: **FAIL** (msg `8993fa8f`) |
| 12:31:29 | Coordinator: STAGE 2 RETURN (msg `13199faa`) |
| 13:00:42 | Reviewer: STAGE 2 RE-VERDICT: **PASS** (msg `e0664ffc`) |
| 13:01:27 | Coordinator: STAGE 2 REPORT (msg `fcbc5d99`) + STAGE 3 HANDOFF (msg `cafb13cb`) |
| 14:48:44 | Reviewer: STAGE 3 VERDICT: **FAIL** (msg `625d00e6`) |
| 14:49:13 | Coordinator: STAGE 3 RETURN (msg `7bd55c6b`) |
| 15:06:51 | Reviewer: STAGE 3 RE-VERDICT: **PASS** (msg `6502c176`) |
| 15:07:34 | Coordinator: STAGE 3 REPORT (msg `53ce6f1e`) + STAGE 4 HANDOFF (msg `9977e3ea`) |
| 17:04:27 | Reviewer: STAGE 4 (FINAL) VERDICT: **PASS** (msg `0c62b359`) |
| 17:04:49 | Coordinator: **FINAL RUN REPORT** — run complete (msg `34e59d4a`) |

**Total wall-clock time: about 7 hours 14 minutes** (09:50:42 → 17:04:49).

Per-stage durations (handoff → coordinator's closing report):

- **Stage 1: ~1 h 16 min** (09:50:42 → 11:07:23)
- **Stage 2: ~1 h 54 min** (11:07:23 → 13:01:27), including the
  FAIL → repair → re-verification loop
- **Stage 3: ~1 h 55 min** measured from the redelivered handoff
  (13:12:28 → 15:07:34); from the handoff's original send (13:01:27) it
  is ~2 h 6 min — the difference is the 13:08 machine swap below
- **Stage 4: ~2 h** (15:07:34 → 17:04:49). The largest part of this was
  the reviewer's final verification itself, which ran ~68 minutes
  (15:55:57 → 17:04:27): the reviewer wrote and ran its own stage-4
  specification probes in addition to the official checks.

## Verification results

Measured with the official harness on the closing revision `16a6832`.
Because each stage's folder carries the full surface of the earlier
stages, the harness run on the closing revision measures all four
suites; the stage 1–3 results below are therefore results **on the
closing revision**, not only on each stage's own closing revision:

- Stage 1: **147/147**
- Stage 2: **35/35**
- Stage 3: **6/6**
- Stage 4: **5/5**
- **highest_contiguous = 4**

**Post-run re-measurement (attribution).** After the run, during
submission preparation, EVORA (the human-side assistant named below)
re-measured the deliverable from a **fresh clone of the closing
revision `16a6832`**, using the official harness in host
(external-URL) mode. The first attempt measured the stage-2 suite at
34/35 — one browser probe timed out; a clean re-run minutes later
measured all four suites passing in full: **147/147 + 35/35 + 6/6 +
5/5, highest_contiguous = 4**. During the same preparation, all four
stage Dockerfiles were build-verified (clean rebuild; the exported
image contents match the repository files).

## The review loops — FAIL → repair → PASS

The reviewer did not rubber-stamp. Two stages were sent back, repaired,
and re-verified before they could close. In both cases the reviewer's
own run of the official checks passed — the defects were found by its
item-by-item examination of the delivered output against the stated
requirements, which its mandate requires alongside the check run:

- **Stage 2 — reviewer FAIL** (12:30:55, msg `8993fa8f`; coordinator
  RETURN 12:31:29). Three defects the shipped checks had not caught:
  - **D1:** `ui.py` referenced an undefined `errEl` in the void
    handler — a void error would have broken silently in the browser;
  - **D2:** the capture amount field was pre-filled with the raw
    minor-unit value, so a plain click would have submitted a 100×
    amount;
  - **D3:** the delivered stage-2 `RUN.md` was a stale copy of
    stage 1's — a documentation/file-state defect, found by examining
    the delivered files (not a specification-semantics defect).
  Repairs: `418b35d` (D1/D2/D3), `0cf002f`, `d76dca2`; the reviewer
  verified the resulting revision and issued a RE-VERDICT: PASS
  (13:00:42); the stage closed at revision `342e218`.
- **Stage 3 — reviewer FAIL** (14:48:44, msg `625d00e6`; coordinator
  RETURN 14:49:13).
  - **D1:** the historical held-amount calculation had no existence
    gate, so a hold could register at a point in time *before the
    authorization was created* — a specification-semantics defect in
    the historical-balance rules.
  Fixed in revision `b736ea6` (a hold now starts at authorization
  creation); re-verification passed (RE-VERDICT: PASS, 15:06:51) and
  the stage closed.

## Measured cost

- **Account spend over the run window: 10.16 USD**, derived from the
  model provider's (OpenRouter) billing totals: the account's total
  usage stood at **68.13 USD at dispatch** and **78.29 USD at close**
  — a difference of 10.16 USD across exactly the run window.
  Balance cross-check: **1.87 USD opening balance + 10.00 USD top-up
  during the run − 1.71 USD closing balance = 10.16 USD**.
- The account was not new: of the 80 USD of credits purchased on it in
  total, 70 USD predated the run; the 1.87 USD opening balance was the
  pre-run remainder, and the window method above isolates the run's
  spend from it.
- Nothing else drew on the account inside the window in a way that
  would distort the figure: the preparation (sandbox tests) ran on the
  provider's free model tier at 0 USD, and the post-run re-measurement
  was a local harness run that consumed no model spend.
- Model: **qwen/qwen3.8-27b**, priced at $0.425 / 1M input tokens and
  $2.55 / 1M output tokens.

## Design decisions

- **Slice-based work.** Every work slice ended in a durable save point
  on disk: a git commit plus an updated `STATE.md`. A stage was only
  ever measured against a named, committed revision — never against a
  dirty working tree. This is also what made the infrastructure events
  below survivable: the work lived in commits and state notes, not in
  any seat's memory.
- **The reviewer measures *and* examines.** The shipped checks cover
  only part of the specification surface (the organisers' own coverage
  figures put the shipped checks at about 35% of the stage-2 surface),
  so the reviewer's mandate required its own run of the acceptance
  check **plus** an item-by-item examination of the output against the
  stated requirements. Both FAIL verdicts came from that examination,
  not from the shipped checks.
- **Stage closure discipline.** A measurement never closed a stage. A
  stage counted as closed only by the coordinator's closing report,
  preceded by the reviewer's independent PASS.

## Infrastructure events during the run

- **Two machine swaps.** The virtual machine hosting the seats was
  replaced twice during the run:
  - **~10:07**, during stage 1's build: the stage-1 handoff
    (msg `8a468743`, sent 09:51:11) was redelivered with the same
    message id after the seats were restored, and the work continued.
  - **~13:08** (host boot 13:08:36), just after stage 2 closed: the
    stage-3 handoff (msg `cafb13cb`, sent 13:01:27) was redelivered
    with the same message id at 13:12:28; the implementer's in-flight
    first stage-3 turn had died in the swap, and the task restarted
    intact.
  Each time the seats were restarted on the restored host by EVORA's
  seat-guardian automation, and the work continued **with no loss**:
  because all work lived on disk (commits + `STATE.md`), the seats
  resumed exactly where they had stopped. No restart put any message
  into the room.
- **A rotation attempt that taught us something.** During stage 4,
  EVORA proposed rotating the implementer's long session (archiving it
  so the seat would pick up a fresh one on restart); Kiss approved,
  and EVORA executed it (seat stopped, session archived, seat
  restarted). The measured lesson: **archiving a session does not by
  itself force a fresh session** — the adapter re-bound the same
  session. The run was unharmed (the in-flight stage-4 handoff
  redelivered and work resumed), but the expected token saving never
  materialised. Rotation is filed as a cost/hygiene measure, not a
  survival tool; the slice discipline above is the survival tool.

## Who EVORA is — open disclosure

EVORA is a human-side assistant AI (not a team member and not a seat).
EVORA prepared the run (the mandates, the launch package, and a double
pre-launch audit of both) and operated the infrastructure the seats ran
on: the seats ran on EVORA's machine, and EVORA's guardian automation
restarted them after the machine swaps; EVORA also executed the
stage-4 session-rotation attempt described above, which it had
proposed and Kiss had approved. **During the run EVORA did not write
in the room, wrote no code, and made no decisions about the content of
the work** — every message in the room after the single human dispatch
is seat traffic, and the infrastructure operations above were
operations on the seats' runtime, not instructions to them. After the
run, EVORA helped assemble this submission package and ran the
post-run re-measurement described above.

## Failures and lessons

1. **Two reviewer FAILs (stage 2 and stage 3)** — both on defects the
   shipped checks did not cover, found by the reviewer's examination
   of the output against the requirements. Lesson: independent
   measurement alone is not verification; the requirements examination
   is what caught real defects. The FAIL → repair → re-verify loop is
   a feature of the factory, not an embarrassment.
2. **Two machine swaps mid-run** — survived with zero work loss
   because of the slice discipline (commit + `STATE.md` after every
   slice, measurement only on named revisions).
3. **Session rotation does not do what its name suggests** — archiving
   alone does not force a fresh session on restart; measured,
   recorded, and not repeated blindly.

## Appendix — commit index

The git history in this repository is the seats' original, unmodified
commit chain from the run (the packaging files — `README.md`, this
file, and `mandates/` — are uncommitted additions in the submission
copy; no packaging commits were added to the chain). Times are the
commits' recorded author times, converted to CEST.

| Revision | Time (CEST) | Stage | What it is |
|----------|-------------|-------|------------|
| `04bbe99` | 10:19 | 1 | design notes — all open items resolved |
| `89a32c0` | 10:30 | 1 | full service implementation |
| `933914e` | 10:33 | 1 | Dockerfile (RUN-free) and RUN.md |
| `22a3492` | 10:48 | 1 | missing-required-field is 422 (s1-run-1 fix); STATE.md |
| `3414286` | 10:56 | 1 | **stage-1 closing state** — s1-run-3 147/147, image verified |
| `1404a30` | 11:18 | 2 | copy of verified stage-1 tree, widening begins |
| `669dfb5` | 11:32 | 2 | API widening — authorizations, holds, TTL/expiry, UI routes |
| `859e12a` | 11:40 | 2 | UI complete |
| `7a2da9f` | 12:08 | 2 | fixes from the harness loop |
| `600d97e` | 12:11 | 2 | stage-2 state the reviewer first verified — suites 1–2 pass |
| `418b35d` | 12:40 | 2 | **repair loop:** D1/D2/D3 — void error slot, decimal capture pre-fill, real stage-2 RUN.md |
| `0cf002f` | 12:44 | 2 | repair loop: refresh wallet+feed after successful actions |
| `d76dca2` | 12:49 | 2 | repair loop final state — s2-run-8 suites 1–2 pass, UI probes 17/17 |
| `342e218` | 12:49 | 2 | **stage-2 closing revision** (housekeeping on top of the repairs) |
| `a8ec3fd` | 13:27 | 3 | revision model, corrections, historical /me, statements (API core) |
| `f938b33` | 13:55 | 3 | RUN.md + probe-verified API (112 spec-corner probes) |
| `3672734` | 14:01 | 3 | stage-3 state the reviewer first verified — s3-run-1 suites 1–3 pass |
| `b736ea6` | 14:58 | 3 | **D1 fix** — held_at gates on creation time; s3-run-3 suites 1–3 pass |
| `b022675` | 15:35 | 4 | stage-4 core — refunds + correction batches, refund floor |
| `16a6832` | 15:54 | 4 | **stage-4 closing revision / final revision** — s4-run-1 suites 1–4 pass |
