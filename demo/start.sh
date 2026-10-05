#!/bin/sh
# Demo hosting glue (NOT part of the judged submission code):
# starts the unmodified stage-4 service, then seeds it once with demo
# users funded with play money, so every cold start lands on a usable demo.
P="${PORT:-8080}"
PORT="$P" python /app/app.py &
APP_PID=$!
PORT="$P" python3 - <<'PY'
import os, time, urllib.request
base = "http://127.0.0.1:%s" % os.environ.get("PORT", "8080")
for _ in range(60):
    try:
        urllib.request.urlopen(base + "/health", timeout=2)
        break
    except Exception:
        time.sleep(1)
seed = open("/app/seed_state.json", "rb").read()
req = urllib.request.Request(base + "/_test/import", data=seed,
                             headers={"Content-Type": "application/json"},
                             method="POST")
try:
    print("seed import status:", urllib.request.urlopen(req, timeout=10).status)
except Exception as e:
    print("seed import note:", e)
PY
wait $APP_PID
