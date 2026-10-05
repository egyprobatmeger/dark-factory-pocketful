# Pocketful — stage 2

Wallet screens and payment authorizations on top of the stage-1 payment
service. Python 3 standard library only; no build steps, no runtime
dependencies, no outbound network access required.

This stage extends stage 1 (all of whose behaviour continues to apply) with:

- `POST /authorizations`, `POST /authorizations/{id}/capture` (final and
  nonfinal), `POST /authorizations/{id}/void`, `GET /authorizations`
- holds: `GET /me` adds `total`, `available`, `held`; `insufficient_funds`
  is evaluated against `available`
- the browser UI: `/` (wallet + pay/request/authorise forms + feed),
  `/requests`, `/split`, `/authorizations`, `/login`, `/signup`

## Build (Docker)

```sh
docker build -t pocketful-stage2 .
```

## Run (Docker)

```sh
docker run --rm -p 8080:8080 -e PORT=8080 pocketful-stage2
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
requests; the same paths return JSON to API clients (e.g.
`GET /requests`, `GET /authorizations`).

Then, from the official package (with a fresh `--out` folder per run; the
stage-1 service must be running for the upgrade checks):

```sh
cd <official-package>
env -u https_proxy -u HTTPS_PROXY -u http_proxy -u HTTP_PROXY \
  NO_PROXY="127.0.0.1,localhost" no_proxy="127.0.0.1,localhost" \
  python -m harness run --track pocketful --base-url http://127.0.0.1:$PORT \
  --previous-base-url http://127.0.0.1:<stage1-port> \
  --stage 2 --out <fresh-out-folder>
```
