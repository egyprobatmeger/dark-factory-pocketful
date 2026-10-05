# Pocketful — stage 3

Statements and payment corrections on top of the stage-2 service.
Python 3 standard library only; no build steps, no runtime
dependencies, no outbound network access required.

This stage extends stage 1 and 2 (all of whose behaviour continues to
apply) with:

- per-payment revision histories and `POST /payments/{id}/corrections`
  (the eighth idempotent write path), `GET /payments/{id}/revisions`
- historical queries: `GET /me` and `GET /statement` accept `as_of` and
  `known_at` RFC 3339 instants
- `GET /statement` — the caller's money movements in `[from, to)` with
  per-entry `balance_after`, and opaque `snapshot` tokens for stable
  pagination
- seeded payments may carry `created_at`; authorizations carry `closed_at`

## Build (Docker)

```sh
docker build -t pocketful-stage3 .
```

## Run (Docker)

```sh
docker run --rm -p 8080:8080 -e PORT=8080 pocketful-stage3
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
stage-2 service must be running for the upgrade checks):

```sh
cd <official-package>
env -u https_proxy -u HTTPS_PROXY -u http_proxy -u HTTP_PROXY \
  NO_PROXY="127.0.0.1,localhost" no_proxy="127.0.0.1,localhost" \
  python -m harness run --track pocketful --base-url http://127.0.0.1:$PORT \
  --previous-base-url http://127.0.0.1:<stage2-port> \
  --stage 3 --out <fresh-out-folder>
```
