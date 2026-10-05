# Pocketful — stage 4

Refunds and batch corrections on top of the stage-3 service.
Python 3 standard library only; no build steps, no runtime
dependencies, no outbound network access required.

This stage extends stages 1–3 (all of whose behaviour continues to
apply) with ten idempotent write paths:

- `POST /payments/{id}/refunds` (9th) — the original receiver refunds a
  payment (direct, request, capture or settlement member; never a refund).
  The refund is a new reverse-direction payment linked by `refund_of`,
  paid from the receiver's available funds. Cumulative refunds cannot
  exceed the payment's current corrected amount.
- `POST /correction-batches` (10th) — settlement operators correct
  several payments in one request (1..32, distinct payment_ids),
  including every member of a settlement at one shared effective instant.
  All new revisions share one `recorded_at` and carry `correction_batch_id`.
- payments expose `refund_of` (null except refunds); revisions expose
  `correction_batch_id` (null except batch corrections)
- a correction cannot reduce a payment below its already-refunded amount
- captures and refunds are immutable to corrections (single or batch)
- the service accepts exports from stages 1–3, retaining settlement
  membership, corrections and snapshots

## Build (Docker)

```sh
docker build -t pocketful-stage4 .
```

## Run (Docker)

```sh
docker run --rm -p 8080:8080 -e PORT=8080 pocketful-stage4
```

The container listens on `0.0.0.0:$PORT` (default 8080). State is
in-memory; a restart starts empty.

## Run (native)

```sh
PORT=18091 python3 app.py
```

## Verify

```sh
curl http://127.0.0.1:$PORT/health
# -> {"status": "ok"}
```

The UI is served at `http://127.0.0.1:$PORT/` for `Accept: text/html`
requests; the same paths return JSON to API clients.

Then, from the official package (with a fresh `--out` folder per run; the
stage-3 service must be running for the upgrade checks):

```sh
cd <official-package>
env -u https_proxy -u HTTPS_PROXY -u http_proxy -u HTTP_PROXY \
  NO_PROXY="127.0.0.1,localhost" no_proxy="127.0.0.1,localhost" \
  python -m harness run --track pocketful --base-url http://127.0.0.1:$PORT \
  --previous-base-url http://127.0.0.1:<stage3-port> \
  --stage 4 --out <fresh-out-folder>
```
