# Pocketful — stage 1

An in-memory payments service. Python 3 standard library only; no build
steps, no runtime dependencies, no outbound network access required.

## Build (Docker)

```sh
docker build -t pocketful-stage1 .
```

## Run (Docker)

```sh
docker run --rm -p 8080:8080 -e PORT=8080 pocketful-stage1
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

Then, from the official package (with a fresh `--out` folder per run):

```sh
cd <official-package>
env -u https_proxy -u HTTPS_PROXY -u http_proxy -u HTTP_PROXY \
  NO_PROXY="127.0.0.1,localhost" no_proxy="127.0.0.1,localhost" \
  python -m harness run --track pocketful --base-url http://127.0.0.1:$PORT \
  --stage 1 --out <fresh-out-folder>
```
