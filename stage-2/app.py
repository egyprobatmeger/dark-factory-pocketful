"""Pocketful — stage 2: wallet screens, payment authorizations.

Extends the stage-1 service (payments, requests, splits, settlements) with
authorizations/captures (holds) and a server-rendered consumer UI.

Single-file HTTP service, Python 3 stdlib only. In-memory state, one global
lock around all state access. See DESIGN_NOTES.md for the decisions behind
each behaviour.
"""
import hashlib
import hmac
import html as _html
import json
import os
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs, parse_qsl

import ui

MAX_BODY = 32 * 1024 * 1024
MAX_NOTE = 200
MAX_AMOUNT = 1_000_000_000
HANDLE_RE = re.compile(r"^[a-z0-9_]{1,20}$")
DIGITS_RE = re.compile(r"^[0-9]+$")
SCRYPT_N = 2 ** 12
SCRYPT_R = 8
SCRYPT_P = 1


def now_rfc3339():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_integral_number(v):
    """True for JSON numbers with an integral value (int, or integral float)."""
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    if isinstance(v, float):
        return v.is_integer()
    return False


def check_amount(v):
    """Return (ok, value). ok means integral and 1..MAX_AMOUNT."""
    if not is_integral_number(v):
        return False, None
    value = int(v)
    if value < 1 or value > MAX_AMOUNT:
        return False, None
    return True, value


def check_visibility(v):
    return v == "public" or v == "private"


def check_note(v):
    return isinstance(v, str) and len(v) <= MAX_NOTE


def hash_password(password, salt=None):
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R,
                        p=SCRYPT_P, dklen=64)
    return "scrypt${}${}${}${}${}".format(
        SCRYPT_N, SCRYPT_R, SCRYPT_P, salt.hex(), dk.hex())


def verify_password(password, stored):
    try:
        _, n, r, p, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                            n=int(n), r=int(r), p=int(p), dklen=64)
        return hmac.compare_digest(dk, bytes.fromhex(dk_hex))
    except (ValueError, TypeError):
        return False


def derived_handle(email):
    local = email.split("@", 1)[0].lower()
    cleaned = "".join(c if (c.isascii() and (c.isalnum() or c == "_")) else "_"
                      for c in local)
    return cleaned[:20]


def valid_email(email):
    if not isinstance(email, str):
        return False
    if email.count("@") != 1:
        return False
    local, domain = email.split("@", 1)
    return bool(local) and bool(domain) and not any(c.isspace() for c in email)


def equal_split(amount, n):
    base = amount // n
    remainder = amount - base * n
    return [base + (1 if i < remainder else 0) for i in range(n)]


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def error(status, code, message="error"):
    return status, {"error": {"code": code, "message": message}}


def parse_rfc3339(value):
    """Parse an RFC 3339 timestamp with explicit offset; None when invalid."""
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class State:
    def __init__(self, currency="EUR", minor_units=2):
        self.currency = currency
        self.minor_units = minor_units
        self.ttl = 600           # authorization_ttl_seconds, service-wide
        self.users = {}          # id -> user dict
        self.handles = {}        # handle -> user id
        self.emails = {}         # email (verbatim) -> user id
        self.tokens = {}         # token -> user id
        self.payments = {}       # id -> payment dict
        self.requests = {}       # id -> request dict
        self.authorizations = {} # id -> authorization record
        self.idem = {}           # (user_id, method, path, key) -> {"body": canon, "status": int, "resp": dict}
        self.operators = set()   # user ids
        self.seq = 0
        self.counters = {"payment": 0, "request": 0, "split": 0, "settlement": 0,
                         "user": 0, "token": 0}

    def next_seq(self):
        self.seq += 1
        return self.seq

    def new_id(self, kind):
        table = {"user": self.users, "payment": self.payments,
                 "request": self.requests,
                 "authorization": self.authorizations}[kind]
        while True:
            rid = "{}_{}".format(kind, uuid.uuid4().hex[:16])
            if rid not in table:
                return rid

    def make_token(self):
        self.counters["token"] += 1
        tok = "tok_{}".format(uuid.uuid4().hex)
        while tok in self.tokens:
            tok = "tok_{}".format(uuid.uuid4().hex)
        return tok

    def held(self, uid, now_dt):
        total = 0
        for a in self.authorizations.values():
            if a["from_user_id"] != uid or a["status"] != "open":
                continue
            if a["expires_dt"] <= now_dt:
                continue
            total += a["amount"] - a["captured_amount"]
        return total

    def sweep_expired(self, now_dt):
        for a in self.authorizations.values():
            if a["status"] == "open" and a["expires_dt"] <= now_dt:
                a["status"] = "expired"

    def available(self, uid, now_dt):
        u = self.users[uid]
        return u["balance"] - self.held(uid, now_dt)


_LOCK = threading.RLock()
_STATE = None


def state():
    return _STATE


def empty_state():
    global _STATE
    with _LOCK:
        _STATE = State()
    return _STATE


def new_fixture_state(fx, at):
    at_dt = parse_rfc3339(at)
    s = State()
    s.currency = fx["currency"]
    s.minor_units = fx["minor_units"]
    s.ttl = fx.get("ttl", 600)
    for u in fx["users"]:
        s.users[u["id"]] = {
            "id": u["id"], "email": u["email"], "display_name": u["display_name"],
            "handle": u["handle"], "balance": u["balance"],
            "password_hash": hash_password(u["password"]),
        }
        s.handles[u["handle"]] = u["id"]
        s.emails[u["email"]] = u["id"]
    if "settlement_operator_ids" in fx:
        s.operators = set(fx["settlement_operator_ids"])
    for p in fx.get("payments", []):
        s.payments[p["id"]] = {
            "payment_id": p["id"], "from_user_id": p["from_user_id"],
            "to_user_id": p["to_user_id"], "amount": p["amount"], "note": p["note"],
            "visibility": p["visibility"], "request_id": None, "settlement_id": None,
            "authorization_id": None,
            "created_at": at, "seq": s.next_seq(),
        }
    for r in fx.get("requests", []):
        s.requests[r["id"]] = {
            "request_id": r["id"], "requester_id": r["requester_id"],
            "payer_id": r["payer_id"], "amount": r["amount"], "note": r["note"],
            "status": r["status"], "payment_id": r.get("payment_id"),
            "created_at": at, "seq": s.next_seq(),
        }
    for a in fx.get("authorizations", []):
        s.authorizations[a["id"]] = {
            "authorization_id": a["id"], "from_user_id": a["from_user_id"],
            "to_user_id": a["to_user_id"], "amount": a["amount"],
            "captured_amount": a["captured_amount"], "note": a["note"],
            "visibility": a["visibility"], "status": a["status"],
            "expires_at": a["expires_at"], "expires_dt": a["expires_dt"],
            "payment_id": None, "payment_ids": list(a["payment_ids"]),
            "created_at": at, "seq": s.next_seq(),
        }
    s.sweep_expired(parse_rfc3339(at))
    return s


# ---- fixture validation ---------------------------------------------------

def _need_str(d, key, lo=1, hi=None, nonempty=True):
    v = d.get(key)
    if not isinstance(v, str) or (nonempty and len(v) == 0) or len(v) < lo or \
            (hi is not None and len(v) > hi):
        return None
    return v


def validate_fixture(body):
    """Return a normalized fixture dict, or None if the fixture is invalid."""
    if not isinstance(body, dict):
        return None
    currency = body.get("currency")
    if not isinstance(currency, str) or not currency:
        return None
    minor_units = body.get("minor_units")
    if isinstance(minor_units, bool) or not isinstance(minor_units, int) or \
            minor_units not in (0, 2, 3):
        return None
    users_in = body.get("users")
    if not isinstance(users_in, list):
        return None
    users, seen_ids, seen_handles, seen_emails = [], set(), set(), set()
    for u in users_in:
        if not isinstance(u, dict):
            return None
        uid = _need_str(u, "id", hi=64)
        email = u.get("email")
        if uid is None or not isinstance(email, str) or not email:
            return None
        password = u.get("password")
        display = u.get("display_name", "")
        handle = _need_str(u, "handle")
        balance = u.get("balance")
        if isinstance(password, bool) or not isinstance(password, str):
            return None
        if not isinstance(display, str):
            return None
        if not HANDLE_RE.match(handle or ""):
            return None
        if not is_integral_number(balance) or int(balance) < 0:
            return None
        if uid in seen_ids or handle in seen_handles or email in seen_emails:
            return None
        seen_ids.add(uid)
        seen_handles.add(handle)
        seen_emails.add(email)
        users.append({"id": uid, "email": email, "password": password,
                      "display_name": display, "handle": handle,
                      "balance": int(balance)})
    user_ids = set(seen_ids)

    def valid_payment(p, allow_id_collision_with):
        if not isinstance(p, dict):
            return None
        pid = _need_str(p, "id", hi=64)
        if pid is None or pid in allow_id_collision_with:
            return None
        allow_id_collision_with.add(pid)
        frm = _need_str(p, "from_user_id")
        to = _need_str(p, "to_user_id")
        ok, amount = check_amount(p.get("amount"))
        note = p.get("note", "")
        vis = p.get("visibility", "public")
        if not ok or frm not in user_ids or to not in user_ids:
            return None
        if not check_note(note) or not check_visibility(vis):
            return None
        return {"id": pid, "from_user_id": frm, "to_user_id": to, "amount": amount,
                "note": note, "visibility": vis}

    payments = []
    used_ids = set()
    for p in body.get("payments", []) or []:
        np = valid_payment(p, used_ids)
        if np is None:
            return None
        payments.append(np)
    used_ids = set()
    requests = []
    for r in body.get("requests", []) or []:
        if not isinstance(r, dict):
            return None
        rid = _need_str(r, "id", hi=64)
        if rid is None or rid in used_ids:
            return None
        used_ids.add(rid)
        req = _need_str(r, "requester_id")
        payer = _need_str(r, "payer_id")
        ok, amount = check_amount(r.get("amount"))
        note = r.get("note", "")
        status = r.get("status", "pending")
        if req not in user_ids or payer not in user_ids or not ok:
            return None
        if not check_note(note) or status not in ("pending", "paid", "declined",
                                                  "cancelled"):
            return None
        requests.append({"id": rid, "requester_id": req, "payer_id": payer,
                         "amount": amount, "note": note, "status": status,
                         "payment_id": r.get("payment_id")})
    ops = body.get("settlement_operator_ids", [])
    if not isinstance(ops, list) or not all(isinstance(o, str) and o in user_ids
                                            for o in ops):
        return None
    ttl = body.get("authorization_ttl_seconds", 600)
    if isinstance(ttl, bool) or not isinstance(ttl, int) or ttl < 1:
        return None
    return {"currency": currency, "minor_units": minor_units, "users": users,
            "payments": payments, "requests": requests,
            "settlement_operator_ids": ops, "ttl": ttl, "authorizations": []}


def validate_seeded_authorizations(body, user_ids, now_dt):
    """Validate the fixture's authorizations; None when invalid.

    Also applies the reset error: a user whose unexpired open seeded holds sum to
    more than their balance makes the whole fixture invalid."""
    arr = body.get("authorizations", [])
    if not isinstance(arr, list):
        return None
    out, seen = [], set()
    holds = {}
    for a in arr:
        if not isinstance(a, dict):
            return None
        aid = _need_str(a, "id", hi=64)
        if aid is None or aid in seen:
            return None
        seen.add(aid)
        frm = _need_str(a, "from_user_id")
        to = _need_str(a, "to_user_id")
        ok, amount = check_amount(a.get("amount"))
        note = a.get("note", "")
        vis = a.get("visibility", "public")
        status = a.get("status", "open")
        exp = a.get("expires_at")
        cap = a.get("captured_amount", 0)
        pids = a.get("payment_ids", [])
        if frm not in user_ids or to not in user_ids or not ok:
            return None
        if not check_note(note) or not check_visibility(vis):
            return None
        if status not in ("open", "captured", "voided", "expired"):
            return None
        if isinstance(cap, bool) or not isinstance(cap, int) or cap < 0 or cap > amount:
            return None
        if not isinstance(pids, list) or not all(isinstance(x, str) for x in pids):
            return None
        exp_dt = parse_rfc3339(exp)
        if exp_dt is None:
            return None
        if status == "open" and exp_dt > now_dt:
            holds[frm] = holds.get(frm, 0) + (amount - cap)
        rec = {"id": aid, "from_user_id": frm, "to_user_id": to, "amount": amount,
               "captured_amount": cap, "note": note, "visibility": vis,
               "status": status, "expires_at": exp, "expires_dt": exp_dt,
               "payment_ids": pids}
        out.append(rec)
    balances = {u["id"]: u["balance"] for u in body["users"]}
    for uid, held in holds.items():
        if held > balances[uid]:
            return None
    return out


def do_reset(body):
    """Replace all state with the fixture. Returns (status, code) — 204 or 422."""
    if not isinstance(body, dict):
        return 422, "validation_failed"
    at = now_rfc3339()
    fx = validate_fixture(body)
    if fx is None:
        return 422, "validation_failed"
    auths = validate_seeded_authorizations(body, {u["id"] for u in fx["users"]},
                                           parse_rfc3339(at))
    if auths is None:
        return 422, "validation_failed"
    fx["authorizations"] = auths
    with _LOCK:
        global _STATE
        _STATE = new_fixture_state(fx, at)
    return 204, None


# ---- object shapes ---------------------------------------------------------

def payment_obj(s, p):
    return {
        "payment_id": p["payment_id"],
        "from_user_id": p["from_user_id"],
        "from_handle": s.users[p["from_user_id"]]["handle"],
        "to_user_id": p["to_user_id"],
        "to_handle": s.users[p["to_user_id"]]["handle"],
        "amount": p["amount"],
        "currency": s.currency,
        "note": p["note"],
        "visibility": p["visibility"],
        "request_id": p["request_id"],
        "settlement_id": p["settlement_id"],
        "authorization_id": p.get("authorization_id"),
        "created_at": p["created_at"],
    }


def authorization_obj(s, a):
    remaining = a["amount"] - a["captured_amount"]
    if a["status"] != "open":
        remaining = 0
    return {
        "authorization_id": a["authorization_id"],
        "from_user_id": a["from_user_id"],
        "from_handle": s.users[a["from_user_id"]]["handle"],
        "to_user_id": a["to_user_id"],
        "to_handle": s.users[a["to_user_id"]]["handle"],
        "amount": a["amount"],
        "captured_amount": a["captured_amount"],
        "remaining_amount": remaining,
        "currency": s.currency,
        "note": a["note"],
        "visibility": a["visibility"],
        "status": a["status"],
        "expires_at": a["expires_at"],
        "payment_id": a["payment_id"],
        "payment_ids": list(a["payment_ids"]),
        "created_at": a["created_at"],
    }


def request_obj(s, r):
    return {
        "request_id": r["request_id"],
        "requester_id": r["requester_id"],
        "requester_handle": s.users[r["requester_id"]]["handle"],
        "payer_id": r["payer_id"],
        "payer_handle": s.users[r["payer_id"]]["handle"],
        "amount": r["amount"],
        "currency": s.currency,
        "note": r["note"],
        "status": r["status"],
        "payment_id": r["payment_id"],
        "created_at": r["created_at"],
    }


# ---- core effects (callers hold the lock) ----------------------------------

def effect_transfer(s, frm_id, to_id, amount, note, visibility,
                    request_id=None, settlement_id=None, authorization_id=None,
                    created_at=None):
    at = created_at or now_rfc3339()
    s.users[frm_id]["balance"] -= amount
    s.users[to_id]["balance"] += amount
    pid = s.new_id("payment")
    p = {"payment_id": pid, "from_user_id": frm_id, "to_user_id": to_id,
         "amount": amount, "note": note, "visibility": visibility,
         "request_id": request_id, "settlement_id": settlement_id,
         "authorization_id": authorization_id,
         "created_at": at, "seq": s.next_seq()}
    s.payments[pid] = p
    return p


def new_user(s, email, password, display_name, handle):
    uid = s.new_id("user")
    s.users[uid] = {"id": uid, "email": email, "display_name": display_name,
                    "handle": handle, "balance": 0,
                    "password_hash": hash_password(password)}
    s.handles[handle] = uid
    s.emails[email] = uid
    tok = s.make_token()
    s.tokens[tok] = uid
    return s.users[uid], tok


# ---- idempotency -----------------------------------------------------------

def idem_lookup(s, user_id, method, path, key, canon_body):
    """Return (status, code, body_or_None).
    (204/None, None, None) means 'proceed as first use'."""
    entry = s.idem.get((user_id, method, path, key))
    if entry is None:
        return 204, None, None
    if entry["body"] == canon_body:
        return 200, None, entry["resp"]
    return 409, "idempotency_key_reuse", None


def idem_claim(s, user_id, method, path, key, canon_body, status, resp):
    s.idem[(user_id, method, path, key)] = {
        "body": canon_body, "status": status, "resp": resp}


def read_key_header(headers):
    key = headers.get("Idempotency-Key")
    if key is None:
        return None, "missing"
    if key == "":
        return None, "missing"
    return key, "ok"


def check_key(key):
    if len(key) > 255:
        return 422, "validation_failed"
    return None, None


# ---- request parsing --------------------------------------------------------

def parse_query(qs):
    out = {}
    for k, values in parse_qs(qs, keep_blank_values=True).items():
        out[k] = values[0]
    return out


def check_int_param(value, lo, hi):
    if not isinstance(value, str) or not DIGITS_RE.match(value):
        return None
    n = int(value)
    if n < lo or (hi is not None and n > hi):
        return None
    return n


def parse_page_params(q, has_direction, has_status, direction_values, status_values):
    if has_direction and "direction" in q and q["direction"] not in direction_values:
        return None
    if has_status and "status" in q and q["status"] not in status_values:
        return None
    limit = 50
    if "limit" in q:
        limit = check_int_param(q["limit"], 1, 200)
        if limit is None:
            return None
    offset = 0
    if "offset" in q:
        offset = check_int_param(q["offset"], 0, None)
        if offset is None:
            return None
    return limit, offset, (q.get("direction") if has_direction else None), \
        (q.get("status") if has_status else None)


# ---- endpoint handlers (all take the parsed body or None, plus caller) -----
# Each returns (status, payload) where payload is a dict or None (for 204).

def auth_signup(body, _caller=None):
    if not isinstance(body, dict):
        return error(400, "malformed_request", "body must be a JSON object")
    if "email" not in body or "password" not in body:
        return error(422, "validation_failed", "email and password are required")
    email = body["email"]
    password = body["password"]
    if not isinstance(email, str) or not isinstance(password, str):
        return error(400, "malformed_request", "email and password must be strings")
    display = body.get("display_name", "")
    if not isinstance(display, str):
        return error(400, "malformed_request", "display_name must be a string")
    if len(password) < 8:
        return error(422, "validation_failed", "password too short")
    if not valid_email(email):
        return error(422, "validation_failed", "invalid email")
    handle = derived_handle(email)
    if not handle:
        return error(422, "validation_failed", "invalid email")
    with _LOCK:
        s = state()
        if email in s.emails:
            return error(409, "email_taken")
        if handle in s.handles:
            return error(409, "handle_taken")
        user, tok = new_user(s, email, password, display, handle)
    return 201, {"user_id": user["id"], "display_name": user["display_name"],
                 "token": tok}


def auth_login(body, _caller=None):
    if not isinstance(body, dict):
        return error(400, "malformed_request", "body must be a JSON object")
    if "email" not in body or "password" not in body:
        return error(422, "validation_failed", "email and password are required")
    email = body["email"]
    password = body["password"]
    if not isinstance(email, str) or not isinstance(password, str):
        return error(400, "malformed_request", "email and password must be strings")
    if not valid_email(email):
        return error(422, "validation_failed", "invalid email")
    with _LOCK:
        s = state()
        uid = s.emails.get(email)
        user = s.users.get(uid) if uid else None
        if user is None or not verify_password(password, user["password_hash"]):
            return error(401, "unauthenticated", "invalid credentials")
        tok = s.make_token()
        s.tokens[tok] = uid
    return 200, {"user_id": user["id"], "display_name": user["display_name"],
                 "token": tok}


def get_me(body, caller):
    with _LOCK:
        s = state()
        now_dt = datetime.now(timezone.utc)
        s.sweep_expired(now_dt)
        u = s.users[caller]
        held = s.held(caller, now_dt)
    return 200, {"user_id": u["id"], "display_name": u["display_name"],
                 "handle": u["handle"], "balance": u["balance"],
                 "total": u["balance"], "available": u["balance"] - held,
                 "held": held,
                 "currency": s.currency, "minor_units": s.minor_units}


def post_payment(body, caller, idem):
    if not isinstance(body, dict):
        return error(400, "malformed_request", "body must be a JSON object")
    user_id, method, path, key, canon = idem
    with _LOCK:
        s = state()
        s.sweep_expired(datetime.now(timezone.utc))
        status, code, stored = idem_lookup(s, user_id, method, path, key, canon)
        if status != 204:
            if status == 409:
                return error(409, "idempotency_key_reuse")
            return status, stored
        if "to_handle" not in body:
            return error(422, "validation_failed", "to_handle is required")
        to_handle = body["to_handle"]
        if not isinstance(to_handle, str):
            return error(400, "malformed_request", "to_handle must be a string")
        amount = body.get("amount")
        ok, amount = check_amount(amount)
        if not ok:
            return error(422, "validation_failed", "invalid amount")
        note = body.get("note", "")
        visibility = body.get("visibility", "public")
        if not check_note(note):
            return error(422, "validation_failed", "invalid note")
        if not check_visibility(visibility):
            return error(422, "validation_failed", "invalid visibility")
        me = s.users[caller]
        if to_handle == me["handle"]:
            return error(422, "self_payment")
        to_id = s.handles.get(to_handle)
        if to_id is None:
            return error(404, "not_found", "no user with that handle")
        if s.available(caller, datetime.now(timezone.utc)) < amount:
            return error(409, "insufficient_funds")
        p = effect_transfer(s, caller, to_id, amount, note, visibility)
        resp = payment_obj(s, p)
        idem_claim(s, user_id, method, path, key, canon, 201, resp)
    return 201, resp


def post_request(body, caller, idem):
    if not isinstance(body, dict):
        return error(400, "malformed_request", "body must be a JSON object")
    user_id, method, path, key, canon = idem
    with _LOCK:
        s = state()
        status, code, stored = idem_lookup(s, user_id, method, path, key, canon)
        if status != 204:
            if status == 409:
                return error(409, "idempotency_key_reuse")
            return status, stored
        if "payer_handle" not in body:
            return error(422, "validation_failed", "payer_handle is required")
        payer_handle = body["payer_handle"]
        if not isinstance(payer_handle, str):
            return error(400, "malformed_request", "payer_handle must be a string")
        amount = body.get("amount")
        ok, amount = check_amount(amount)
        if not ok:
            return error(422, "validation_failed", "invalid amount")
        note = body.get("note", "")
        if not check_note(note):
            return error(422, "validation_failed", "invalid note")
        me = s.users[caller]
        if payer_handle == me["handle"]:
            return error(422, "self_request")
        payer_id = s.handles.get(payer_handle)
        if payer_id is None:
            return error(404, "not_found", "no user with that handle")
        rid = s.new_id("request")
        r = {"request_id": rid, "requester_id": caller, "payer_id": payer_id,
             "amount": amount, "note": note, "status": "pending",
             "payment_id": None, "created_at": now_rfc3339(), "seq": s.next_seq()}
        s.requests[rid] = r
        resp = request_obj(s, r)
        idem_claim(s, user_id, method, path, key, canon, 201, resp)
    return 201, resp


def post_pay_request(body, caller, request_id, idem):
    if not isinstance(body, dict):
        return error(400, "malformed_request", "body must be a JSON object")
    user_id, method, path, key, canon = idem
    with _LOCK:
        s = state()
        now_dt = datetime.now(timezone.utc)
        s.sweep_expired(now_dt)
        status, code, stored = idem_lookup(s, user_id, method, path, key, canon)
        if status != 204:
            if status == 409:
                return error(409, "idempotency_key_reuse")
            return status, stored
        r = s.requests.get(request_id)
        if r is None:
            return error(404, "not_found", "no such request")
        if caller != r["payer_id"]:
            return error(403, "forbidden", "only the payer may pay")
        if r["status"] != "pending":
            return error(409, "request_not_pending")
        visibility = body.get("visibility", "public")
        if not check_visibility(visibility):
            return error(422, "validation_failed", "invalid visibility")
        if s.available(caller, now_dt) < r["amount"]:
            return error(409, "insufficient_funds")
        p = effect_transfer(s, caller, r["requester_id"], r["amount"], r["note"],
                            visibility, request_id=r["request_id"])
        r["status"] = "paid"
        r["payment_id"] = p["payment_id"]
        resp = payment_obj(s, p)
        idem_claim(s, user_id, method, path, key, canon, 201, resp)
    return 201, resp


def post_decline(body, caller, request_id):
    with _LOCK:
        s = state()
        r = s.requests.get(request_id)
        if r is None:
            return error(404, "not_found", "no such request")
        if caller != r["payer_id"]:
            return error(403, "forbidden", "only the payer may decline")
        if r["status"] != "pending" and r["status"] != "declined":
            return error(409, "request_not_pending")
        r["status"] = "declined"
        resp = request_obj(s, r)
    return 200, resp


def post_cancel(body, caller, request_id):
    with _LOCK:
        s = state()
        r = s.requests.get(request_id)
        if r is None:
            return error(404, "not_found", "no such request")
        if caller != r["requester_id"]:
            return error(403, "forbidden", "only the requester may cancel")
        if r["status"] != "pending" and r["status"] != "cancelled":
            return error(409, "request_not_pending")
        r["status"] = "cancelled"
        resp = request_obj(s, r)
    return 200, resp


def post_split(body, caller, idem):
    if not isinstance(body, dict):
        return error(400, "malformed_request", "body must be a JSON object")
    user_id, method, path, key, canon = idem
    with _LOCK:
        s = state()
        status, code, stored = idem_lookup(s, user_id, method, path, key, canon)
        if status != 204:
            if status == 409:
                return error(409, "idempotency_key_reuse")
            return status, stored
        amount = body.get("amount")
        ok, amount = check_amount(amount)
        if not ok:
            return error(422, "validation_failed", "invalid amount")
        handles = body.get("participant_handles")
        if not isinstance(handles, list) or len(handles) == 0 or \
                any(not isinstance(h, str) for h in handles):
            return error(422, "validation_failed", "invalid participant_handles")
        if len(set(handles)) != len(handles):
            return error(422, "validation_failed", "duplicate handle")
        note = body.get("note", "")
        if not check_note(note):
            return error(422, "validation_failed", "invalid note")
        users = []
        for h in handles:
            uid = s.handles.get(h)
            if uid is None:
                return error(404, "not_found", "no user with that handle")
            users.append(uid)
        shares = equal_split(amount, len(users))
        created_at = now_rfc3339()
        split_id = "sp_{}".format(uuid.uuid4().hex[:16])
        share_list = [{"handle": s.users[u]["handle"], "amount": a}
                      for u, a in zip(users, shares)]
        req_list = []
        for u, a in zip(users, shares):
            if u == caller:
                continue
            rid = s.new_id("request")
            r = {"request_id": rid, "requester_id": caller, "payer_id": u,
                 "amount": a, "note": note, "status": "pending",
                 "payment_id": None, "created_at": created_at, "seq": s.next_seq()}
            s.requests[rid] = r
            req_list.append(request_obj(s, r))
        resp = {"split_id": split_id, "amount": amount, "currency": s.currency,
                "note": note, "shares": share_list, "requests": req_list,
                "created_at": created_at}
        idem_claim(s, user_id, method, path, key, canon, 201, resp)
    return 201, resp


def get_requests(body, caller, q):
    page = parse_page_params(
        q, True, True, ("incoming", "outgoing"),
        ("pending", "paid", "declined", "cancelled"))
    if page is None:
        return error(422, "validation_failed", "invalid list parameters")
    limit, offset, direction, status_filter = page
    with _LOCK:
        s = state()
        rows = [r for r in s.requests.values()
                if r["requester_id"] == caller or r["payer_id"] == caller]
        if direction == "incoming":
            rows = [r for r in rows if r["payer_id"] == caller]
        elif direction == "outgoing":
            rows = [r for r in rows if r["requester_id"] == caller]
        if status_filter:
            rows = [r for r in rows if r["status"] == status_filter]
        rows.sort(key=lambda r: (r["created_at"], r["seq"]), reverse=True)
        total = len(rows)
        page = rows[offset:offset + limit]
        items = [request_obj(s, r) for r in page]
    return 200, {"requests": items,
                 "has_more": offset + len(items) < total}


def get_activity(body, caller, q):
    page = parse_page_params(q, False, False, (), ())
    if page is None:
        return error(422, "validation_failed", "invalid paging parameters")
    limit, offset, _, _ = page
    with _LOCK:
        s = state()
        rows = [p for p in s.payments.values()
                if p["visibility"] == "public" or p["from_user_id"] == caller
                or p["to_user_id"] == caller]
        rows.sort(key=lambda p: (p["created_at"], p["seq"]), reverse=True)
        total = len(rows)
        page = rows[offset:offset + limit]
        items = [payment_obj(s, p) for p in page]
    return 200, {"payments": items,
                 "has_more": offset + len(items) < total}


def post_settlement(body, caller, idem):
    if not isinstance(body, dict):
        return error(400, "malformed_request", "body must be a JSON object")
    user_id, method, path, key, canon = idem
    with _LOCK:
        s = state()
        now_dt = datetime.now(timezone.utc)
        s.sweep_expired(now_dt)
        if caller not in s.operators:
            return error(403, "forbidden", "operator required")
        status, code, stored = idem_lookup(s, user_id, method, path, key, canon)
        if status != 204:
            if status == 409:
                return error(409, "idempotency_key_reuse")
            return status, stored
        transfers = body.get("transfers")
        if transfers is None:
            return error(422, "validation_failed", "transfers is required")
        if not isinstance(transfers, list) or not (1 <= len(transfers) <= 32):
            return error(422, "validation_failed", "transfers must have 1..32 entries")
        resolved = []
        for t in transfers:
            if not isinstance(t, dict):
                return error(422, "validation_failed", "transfer must be an object")
            if "from_handle" not in t or "to_handle" not in t:
                return error(422, "validation_failed",
                             "from_handle and to_handle are required")
            frm_h = t["from_handle"]
            to_h = t["to_handle"]
            if not isinstance(frm_h, str) or not isinstance(to_h, str):
                return error(400, "malformed_request",
                             "handles must be strings")
            frm_id = s.handles.get(frm_h)
            to_id = s.handles.get(to_h)
            if frm_id is None or to_id is None:
                return error(404, "not_found", "no user with that handle")
            if frm_id == to_id:
                return error(422, "self_payment")
            ok, amount = check_amount(t.get("amount"))
            if not ok:
                return error(422, "validation_failed", "invalid amount")
            note = t.get("note", "")
            visibility = t.get("visibility", "public")
            if not check_note(note) or not check_visibility(visibility):
                return error(422, "validation_failed", "invalid note or visibility")
            resolved.append((frm_id, to_id, amount, note, visibility))
        net = {}
        for frm_id, to_id, amount, _, _ in resolved:
            net[frm_id] = net.get(frm_id, 0) - amount
            net[to_id] = net.get(to_id, 0) + amount
        for uid, delta in net.items():
            if s.available(uid, now_dt) + delta < 0:
                return error(409, "insufficient_funds")
        at = now_rfc3339()
        settlement_id = "stl_{}".format(uuid.uuid4().hex[:16])
        payments = []
        for frm_id, to_id, amount, note, visibility in resolved:
            p = effect_transfer(s, frm_id, to_id, amount, note, visibility,
                                settlement_id=settlement_id, created_at=at)
            payments.append(payment_obj(s, p))
        resp = {"settlement_id": settlement_id, "committed_at": at,
                "payments": payments}
        idem_claim(s, user_id, method, path, key, canon, 201, resp)
    return 201, resp


def post_authorization(body, caller, idem):
    if not isinstance(body, dict):
        return error(400, "malformed_request", "body must be a JSON object")
    user_id, method, path, key, canon = idem
    with _LOCK:
        s = state()
        now_dt = datetime.now(timezone.utc)
        s.sweep_expired(now_dt)
        status, code, stored = idem_lookup(s, user_id, method, path, key, canon)
        if status != 204:
            if status == 409:
                return error(409, "idempotency_key_reuse")
            return status, stored
        if "to_handle" not in body:
            return error(422, "validation_failed", "to_handle is required")
        to_handle = body["to_handle"]
        if not isinstance(to_handle, str):
            return error(400, "malformed_request", "to_handle must be a string")
        amount = body.get("amount")
        ok, amount = check_amount(amount)
        if not ok:
            return error(422, "validation_failed", "invalid amount")
        note = body.get("note", "")
        visibility = body.get("visibility", "public")
        if not check_note(note):
            return error(422, "validation_failed", "invalid note")
        if not check_visibility(visibility):
            return error(422, "validation_failed", "invalid visibility")
        me = s.users[caller]
        if to_handle == me["handle"]:
            return error(422, "self_payment")
        to_id = s.handles.get(to_handle)
        if to_id is None:
            return error(404, "not_found", "no user with that handle")
        if s.available(caller, now_dt) < amount:
            return error(409, "insufficient_funds")
        created_at = now_rfc3339()
        expires_dt = now_dt + timedelta(seconds=s.ttl)
        aid = s.new_id("authorization")
        a = {"authorization_id": aid, "from_user_id": caller, "to_user_id": to_id,
             "amount": amount, "captured_amount": 0, "note": note,
             "visibility": visibility, "status": "open",
             "expires_at": expires_dt.isoformat(timespec="seconds"),
             "expires_dt": expires_dt,
             "payment_id": None, "payment_ids": [],
             "created_at": created_at, "seq": s.next_seq()}
        s.authorizations[aid] = a
        resp = authorization_obj(s, a)
        idem_claim(s, user_id, method, path, key, canon, 201, resp)
    return 201, resp


def post_capture(body, caller, authorization_id, idem):
    if not isinstance(body, dict):
        return error(400, "malformed_request", "body must be a JSON object")
    user_id, method, path, key, canon = idem
    with _LOCK:
        s = state()
        now_dt = datetime.now(timezone.utc)
        s.sweep_expired(now_dt)
        status, code, stored = idem_lookup(s, user_id, method, path, key, canon)
        if status != 204:
            if status == 409:
                return error(409, "idempotency_key_reuse")
            return status, stored
        a = s.authorizations.get(authorization_id)
        if a is None:
            return error(404, "not_found", "no such authorization")
        if caller != a["to_user_id"]:
            return error(403, "forbidden", "only the receiver may capture")
        if a["expires_dt"] <= now_dt:
            a["status"] = "expired"
            return error(409, "authorization_expired")
        if a["status"] != "open":
            return error(409, "authorization_not_open")
        remaining = a["amount"] - a["captured_amount"]
        if "amount" in body:
            amt = body["amount"]
            if isinstance(amt, bool) or not is_integral_number(amt):
                return error(422, "validation_failed", "invalid amount")
            amt = int(amt)
            if amt < 1:
                return error(422, "validation_failed", "invalid amount")
            if amt > remaining:
                return error(422, "capture_exceeds_authorization")
        else:
            amt = remaining
        final = body.get("final", True)
        if not isinstance(final, bool):
            return error(400, "malformed_request", "final must be a boolean")
        p = effect_transfer(s, a["from_user_id"], a["to_user_id"], amt,
                            a["note"], a["visibility"],
                            authorization_id=a["authorization_id"])
        a["captured_amount"] += amt
        a["payment_ids"].append(p["payment_id"])
        a["payment_id"] = p["payment_id"]
        if final or a["captured_amount"] >= a["amount"]:
            a["status"] = "captured"
        resp = payment_obj(s, p)
        idem_claim(s, user_id, method, path, key, canon, 201, resp)
    return 201, resp


def post_void(body, caller, authorization_id):
    with _LOCK:
        s = state()
        now_dt = datetime.now(timezone.utc)
        s.sweep_expired(now_dt)
        a = s.authorizations.get(authorization_id)
        if a is None:
            return error(404, "not_found", "no such authorization")
        if caller != a["from_user_id"]:
            return error(403, "forbidden", "only the payer may void")
        if a["status"] != "open" and a["status"] != "voided":
            return error(409, "authorization_not_open")
        a["status"] = "voided"
        resp = authorization_obj(s, a)
    return 200, resp


def get_authorizations(body, caller, q):
    page = parse_page_params(
        q, True, True, ("outgoing", "incoming"),
        ("open", "captured", "voided", "expired"))
    if page is None:
        return error(422, "validation_failed", "invalid list parameters")
    limit, offset, direction, status_filter = page
    with _LOCK:
        s = state()
        now_dt = datetime.now(timezone.utc)
        s.sweep_expired(now_dt)
        rows = [a for a in s.authorizations.values()
                if a["from_user_id"] == caller or a["to_user_id"] == caller]
        if direction == "outgoing":
            rows = [a for a in rows if a["from_user_id"] == caller]
        elif direction == "incoming":
            rows = [a for a in rows if a["to_user_id"] == caller]
        if status_filter:
            rows = [a for a in rows if a["status"] == status_filter]
        rows.sort(key=lambda a: (a["created_at"], a["seq"]), reverse=True)
        total = len(rows)
        page = rows[offset:offset + limit]
        items = [authorization_obj(s, a) for a in page]
    return 200, {"authorizations": items,
                 "has_more": offset + len(items) < total}


# ---- export / import --------------------------------------------------------

def export_state():
    with _LOCK:
        s = state()
        snap = {
            "currency": s.currency,
            "minor_units": s.minor_units,
            "ttl": s.ttl,
            "users": [{k: v for k, v in u.items()} for u in s.users.values()],
            "handles": dict(s.handles),
            "emails": dict(s.emails),
            "tokens": dict(s.tokens),
            "payments": {k: dict(v) for k, v in s.payments.items()},
            "requests": {k: dict(v) for k, v in s.requests.items()},
            "authorizations": {
                k: {kk: vv for kk, vv in a.items() if kk != "expires_dt"}
                for k, a in s.authorizations.items()},
            "idem": [{"key": list(k), "entry": dict(v)}
                     for k, v in s.idem.items()],
            "operators": sorted(s.operators),
            "seq": s.seq,
        }
    return {"track": "pocketful", "format_version": 1, "state": snap}


def import_state(body):
    if not isinstance(body, dict):
        return 400, "malformed_request"
    if body.get("track") != "pocketful" or body.get("format_version") != 1 or \
            isinstance(body.get("format_version"), bool):
        return 422, "validation_failed"
    snap = body.get("state")
    if not isinstance(snap, dict):
        return 422, "validation_failed"
    try:
        if not isinstance(snap.get("currency"), str) or \
                not isinstance(snap.get("minor_units"), int) or \
                isinstance(snap.get("minor_units"), bool) or \
                snap["minor_units"] not in (0, 2, 3) or \
                not isinstance(snap.get("users"), list) or \
                not isinstance(snap.get("handles"), dict) or \
                not isinstance(snap.get("emails"), dict) or \
                not isinstance(snap.get("tokens"), dict) or \
                not isinstance(snap.get("payments"), dict) or \
                not isinstance(snap.get("requests"), dict) or \
                not isinstance(snap.get("idem"), list) or \
                not isinstance(snap.get("operators"), list) or \
                not isinstance(snap.get("seq"), int) or \
                isinstance(snap.get("seq"), bool):
            raise ValueError("shape")
        ttl = snap.get("ttl", 600)
        if isinstance(ttl, bool) or not isinstance(ttl, int) or ttl < 1:
            raise ValueError("ttl")
        users = {}
        for u in snap["users"]:
            if not isinstance(u, dict) or not isinstance(u.get("id"), str) or \
                    not isinstance(u.get("balance"), int) or \
                    isinstance(u.get("balance"), bool):
                raise ValueError("user")
            users[u["id"]] = u
        for table in (snap["payments"], snap["requests"]):
            for k, v in table.items():
                if not isinstance(k, str) or not isinstance(v, dict):
                    raise ValueError("row")
        auths = snap.get("authorizations", {})
        if not isinstance(auths, dict):
            raise ValueError("authorizations")
        for k, a in auths.items():
            if not isinstance(k, str) or not isinstance(a, dict):
                raise ValueError("authorization")
            if not isinstance(a.get("amount"), int) or \
                    isinstance(a.get("amount"), bool) or \
                    not isinstance(a.get("captured_amount"), int) or \
                    isinstance(a.get("captured_amount"), bool) or \
                    a["captured_amount"] < 0 or \
                    a["captured_amount"] > a["amount"] or \
                    not isinstance(a.get("status"), str) or \
                    not isinstance(a.get("expires_at"), str) or \
                    not isinstance(a.get("from_user_id"), str) or \
                    not isinstance(a.get("to_user_id"), str):
                raise ValueError("authorization")
            if a["from_user_id"] not in users or a["to_user_id"] not in users:
                raise ValueError("authorization")
            if parse_rfc3339(a["expires_at"]) is None:
                raise ValueError("authorization")
            pids = a.get("payment_ids", [])
            if not isinstance(pids, list) or not all(isinstance(x, str)
                                                      for x in pids):
                raise ValueError("authorization")
        for row in snap["idem"]:
            if not isinstance(row, dict) or not isinstance(row.get("key"), list) or \
                    not isinstance(row.get("entry"), dict):
                raise ValueError("idem")
    except (ValueError, AttributeError, TypeError):
        return 422, "validation_failed"
    with _LOCK:
        global _STATE
        s = State()
        s.currency = snap["currency"]
        s.minor_units = snap["minor_units"]
        s.ttl = snap.get("ttl", 600)
        s.users = {k: dict(v) for k, v in users.items()}
        s.handles = dict(snap["handles"])
        s.emails = dict(snap["emails"])
        s.tokens = dict(snap["tokens"])
        s.payments = {k: dict(v) for k, v in snap["payments"].items()}
        s.requests = {k: dict(v) for k, v in snap["requests"].items()}
        for k, a in auths.items():
            record = dict(a)
            record["payment_ids"] = list(record.get("payment_ids", []))
            record["expires_dt"] = parse_rfc3339(record["expires_at"])
            s.authorizations[k] = record
        s.idem = {tuple(row["key"]): dict(row["entry"]) for row in snap["idem"]}
        s.operators = set(snap["operators"])
        s.seq = snap["seq"]
        _STATE = s
    return 204, None


# ---- HTTP plumbing ----------------------------------------------------------

import socket

REQUEST_ACTIONS = re.compile(r"^/requests/([^/]+)/(pay|decline|cancel)$")
AUTH_ACTIONS = re.compile(r"^/authorizations/([^/]+)/(capture|void)$")
SESSION_COOKIE = "pocketful_session"
UI_HTML_ACCEPTS = ("/", "/requests", "/split", "/signup", "/login",
                   "/authorizations")
_AUTH_ERROR_TEXT = {
    "email_taken": "An account with that email already exists.",
    "handle_taken": "That account name is already taken.",
    "unauthenticated": "Incorrect email or password.",
    "validation_failed": "Check your details — the email must be valid and "
                         "the password at least 8 characters.",
    "malformed_request": "Something went wrong. Please try again.",
}


def resolve_caller(headers, s):
    auth = headers.get("Authorization")
    if isinstance(auth, str):
        parts = auth.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1]:
            tok = s.tokens.get(parts[1])
            if tok is not None:
                return tok
    cookie = headers.get("Cookie")
    if isinstance(cookie, str):
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith(SESSION_COOKIE + "="):
                value = part[len(SESSION_COOKIE) + 1:]
                return s.tokens.get(value)
    return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "pocketful/2"

    def log_message(self, *args):
        pass

    def _send(self, status, payload=None):
        if status == 204:
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(self, status, data, ctype, extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location, status=302, set_cookie=None):
        self.send_response(status)
        self.send_header("Location", location)
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _wants_html(self):
        accept = self.headers.get("Accept", "")
        return "text/html" in accept

    def _send_html(self, status, html_text, set_cookie=None,
                   clear_cookie=False):
        extra = {}
        if set_cookie:
            extra["Set-Cookie"] = set_cookie
        if clear_cookie:
            extra["Set-Cookie"] = \
                SESSION_COOKIE + "=; Path=/; Max-Age=0; HttpOnly"
        self._send_bytes(status, html_text.encode("utf-8"),
                         "text/html; charset=utf-8", extra)

    def _read_raw(self):
        cl = self.headers.get("Content-Length")
        if cl is None:
            return b""
        try:
            length = int(cl)
        except ValueError:
            return None
        if length < 0 or length > MAX_BODY:
            return None
        if length == 0:
            return b""
        try:
            return self.rfile.read(length)
        except OSError:
            return None

    def _drain(self):
        raw = self._read_raw()
        if raw is not None:
            return
        self.close_connection = True

    def _json_body(self):
        raw = self._read_raw()
        if raw is None:
            return None, True
        if raw == b"":
            return None, False
        try:
            return json.loads(raw.decode("utf-8")), False
        except (UnicodeDecodeError, ValueError):
            return None, True

    def _read_body(self):
        raw = self._read_raw()
        if raw is None:
            return "", True
        try:
            return raw.decode("utf-8"), False
        except UnicodeDecodeError:
            return "", True

    UI_ROUTES = ("/", "/requests", "/split", "/authorizations")
    AUTH_UI_ROUTES = ("/signup", "/login")
    AUTH_API = {"/signup": "/auth/signup", "/login": "/auth/login"}

    def _handle(self, method):
        try:
            parts = urlsplit(self.path)
            path = parts.path
            q = parse_query(parts.query)
            html = self._wants_html()
            if method == "GET" and (path in self.UI_ROUTES or
                                    path in self.AUTH_UI_ROUTES) and html:
                self._ui_page(path)
                return
            caller, body, bad = self._preauth(method, path)
            if bad:
                return
            if path in ("/health", "/_test/reset", "/_test/export",
                        "/_test/import", "/auth/signup", "/auth/login"):
                outcome = self._dispatch_unauth(method, path, q, body)
            elif caller is not None:
                outcome = self._dispatch(method, path, q, caller, body)
            else:
                outcome = self._dispatch_unauth(method, path, q, body)
            if outcome is not None:
                status, payload = outcome
                self._send(status, payload)
        except BrokenPipeError:
            pass
        except Exception:
            import traceback
            traceback.print_exc()
            try:
                self._send(*error(500, "internal", "internal error"))
            except Exception:
                pass

    PUBLIC_PATHS = ("/health", "/_test/reset", "/_test/export", "/_test/import",
                    "/auth/signup", "/auth/login",
                    "/", "/requests", "/split", "/signup", "/login",
                    "/authorizations")  # POST /signup|/login handled in dispatch

    def _preauth(self, method, path):
        """Read body + resolve caller. Returns (caller, body_text, fatal)."""
        body, fatal = self._read_body()
        if fatal:
            self._send(*error(400, "malformed_request", "body must be text"))
            return None, None, True
        public = path in self.PUBLIC_PATHS or \
            (method == "POST" and path == "/auth/logout")
        if not public:
            with _LOCK:
                caller = resolve_caller(self.headers, state())
            if caller is None:
                self._send(*error(401, "unauthenticated"))
                return None, None, True
            return caller, body, False
        with _LOCK:
            caller = resolve_caller(self.headers, state())
        return caller, body, False

    def _ui_refresh_fragments(self, caller):
        with _LOCK:
            s = state()
            now_dt = datetime.now(timezone.utc)
            s.sweep_expired(now_dt)
            u = s.users[caller]
            held = s.held(caller, now_dt)
            dm = {
                "user": u, "handle": u["handle"], "mu": s.minor_units,
                "cur": s.currency, "total": u["balance"],
                "available": u["balance"] - held, "held": held,
            }
            rows = [p for p in s.payments.values()
                    if p["visibility"] == "public" or p["from_user_id"] == caller
                    or p["to_user_id"] == caller]
            rows.sort(key=lambda p: (p["created_at"], p["seq"]), reverse=True)
            dm["payments"] = [payment_obj(s, p) for p in rows[:200]]
            frag_wallet = ui.wallet_card(dm)
            frag_feed = ui.feed_card(dm)
        html_text = (
            '<html><body>'
            '<div data-fragment="wallet">{}</div>'
            '<div data-fragment="feed">{}</div>'
            '</body></html>'.format(frag_wallet, frag_feed))
        self._send_html(200, html_text)

    def _auth_html(self, path, body):
        """Browser form submit on /login or /signup (Accept: text/html)."""
        handler = auth_signup if path == "/signup" else auth_login
        parsed, malformed = _json_text(body)
        if malformed:
            parsed = {}
        status, payload = handler(parsed, None)
        if status in (200, 201):
            cookie = "{}={}; Path=/; HttpOnly".format(SESSION_COOKIE,
                                                      payload["token"])
            self._redirect("/", 302, cookie)
            return
        msg = _AUTH_ERROR_TEXT.get(payload.get("error", {}).get("code", ""),
                                   "Something went wrong. Please try again.")
        html_text = ui.render_signup(msg) if path == "/signup" \
            else ui.render_login(msg)
        self._send_html(200, html_text)

    def _dispatch(self, method, path, q, caller, body):
        if method == "POST" and path in ("/signup", "/login"):
            self._auth_html(path, body)
            return None
        if method == "POST" and path == "/auth/logout":
            return self._ui_logout()
        if method == "GET" and path == "/api/ui/refresh":
            self._ui_refresh_fragments(caller)
            return None
        if method == "GET" and path == "/me":
            return get_me(None, caller)
        if method == "GET" and path == "/requests":
            return get_requests(None, caller, q)
        if method == "GET" and path == "/activity":
            return get_activity(None, caller, q)
        if method == "GET" and path == "/authorizations":
            return get_authorizations(None, caller, q)
        if method == "POST":
            if path == "/payments":
                return self._do_write(caller, path, body, post_payment)
            if path == "/requests":
                return self._do_write(caller, path, body, post_request)
            if path == "/splits":
                return self._do_write(caller, path, body, post_split)
            if path == "/settlements":
                return self._do_write(caller, path, body, post_settlement)
            if path == "/authorizations":
                return self._do_write(caller, path, body, post_authorization)
            m = REQUEST_ACTIONS.match(path)
            if m:
                rid, action = m.group(1), m.group(2)
                if action == "pay":
                    return self._do_write(
                        caller, path, body,
                        lambda b, c, i: post_pay_request(b, c, rid, i))
                if action == "decline":
                    return post_decline(None, caller, rid)
                if action == "cancel":
                    return post_cancel(None, caller, rid)
            m = AUTH_ACTIONS.match(path)
            if m:
                aid, action = m.group(1), m.group(2)
                if action == "capture":
                    return self._do_write(
                        caller, path, body,
                        lambda b, c, i: post_capture(b, c, aid, i))
                if action == "void":
                    return post_void(None, caller, aid)
        return error(404, "not_found", "no such resource")

    def _dispatch_unauth(self, method, path, q, body):
        if method == "POST" and path in ("/signup", "/login"):
            self._auth_html(path, body)
            return None
        if method == "GET" and path == "/health":
            return 200, {"status": "ok"}
        if path in ("/", "/split", "/authorizations", "/requests"):
            if self._wants_html():
                self._redirect("/login")
                return None
            return error(401, "unauthenticated")
        if method == "POST" and path == "/_test/reset":
            if body is None:
                return error(400, "malformed_request", "body required")
            try:
                parsed = json.loads(body) if body else None
            except ValueError:
                return error(400, "malformed_request", "invalid JSON")
            status, code = do_reset(parsed)
            if status == 204:
                return 204, None
            return error(status, code, "invalid fixture")
        if method == "GET" and path == "/_test/export":
            return 200, export_state()
        if method == "POST" and path == "/_test/import":
            if body is None:
                return error(400, "malformed_request", "body required")
            try:
                parsed = json.loads(body) if body else None
            except ValueError:
                return error(400, "malformed_request", "invalid JSON")
            status, code = import_state(parsed)
            if status == 204:
                return 204, None
            return error(status, code, "invalid state")
        if method == "POST" and path == "/auth/signup":
            parsed, malformed = _json_text(body)
            if malformed:
                return error(400, "malformed_request", "invalid JSON")
            return self._auth_result(auth_signup(parsed, None))
        if method == "POST" and path == "/auth/login":
            parsed, malformed = _json_text(body)
            if malformed:
                return error(400, "malformed_request", "invalid JSON")
            return self._auth_result(auth_login(parsed, None))
        return error(404, "not_found", "no such resource")

    def _auth_result(self, outcome):
        """Send an auth response; on success, set the browser session cookie."""
        status, payload = outcome
        if status in (200, 201):
            cookie = "{}={}; Path=/; HttpOnly".format(SESSION_COOKIE, payload["token"])
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_bytes(status, data, "application/json; charset=utf-8",
                             {"Set-Cookie": cookie})
            return None
        self._send(status, payload)
        return None

    def _ui_page(self, path):
        with _LOCK:
            s = state()
            caller = resolve_caller(self.headers, s)
        if path in ("/login", "/signup"):
            html_text = ui.render_login() if path == "/login" else ui.render_signup()
            self._send_html(200, html_text)
            return
        if caller is None:
            self._redirect("/login")
            return
        with _LOCK:
            s = state()
            now_dt = datetime.now(timezone.utc)
            s.sweep_expired(now_dt)
            u = s.users[caller]
            held = s.held(caller, now_dt)
            dm = {
                "user": u, "handle": u["handle"], "mu": s.minor_units,
                "cur": s.currency, "total": u["balance"],
                "available": u["balance"] - held, "held": held,
            }
            if path == "/":
                rows = [p for p in s.payments.values()
                        if p["visibility"] == "public" or p["from_user_id"] == caller
                        or p["to_user_id"] == caller]
                rows.sort(key=lambda p: (p["created_at"], p["seq"]), reverse=True)
                dm["payments"] = [payment_obj(s, p) for p in rows[:200]]
                html_text = ui.render_home(dm)
            elif path == "/requests":
                rows = [r for r in s.requests.values()
                        if r["requester_id"] == caller or r["payer_id"] == caller]
                rows.sort(key=lambda r: (r["created_at"], r["seq"]), reverse=True)
                objs = [request_obj(s, r) for r in rows[:200]]
                dm["incoming"] = [o for o in objs if o["payer_id"] == caller]
                dm["outgoing"] = [o for o in objs if o["requester_id"] == caller]
                html_text = ui.render_requests(dm)
            elif path == "/split":
                html_text = ui.render_split(dm)
            elif path == "/authorizations":
                rows = [a for a in s.authorizations.values()
                        if a["from_user_id"] == caller or a["to_user_id"] == caller]
                rows.sort(key=lambda a: (a["created_at"], a["seq"]), reverse=True)
                dm["authorizations"] = [authorization_obj(s, a) for a in rows[:200]]
                html_text = ui.render_authorizations(dm)
            else:
                html_text = ui.render_home(dm)
        self._send_html(200, html_text)

    def _ui_logout(self):
        self._redirect("/", 302, clear_cookie=True)

    def _do_write(self, caller, path, body, handler):
        key = self.headers.get("Idempotency-Key")
        if key is None or key == "":
            return error(400, "missing_idempotency_key", "Idempotency-Key is required")
        if len(key) > 255:
            return error(422, "validation_failed", "key too long")
        parsed, malformed = _json_text(body)
        if malformed:
            return error(400, "malformed_request", "invalid JSON")
        canon = canonical(parsed) if isinstance(parsed, dict) else None
        idem = (caller, "POST", path, key, canon)
        if canon is None:
            # non-object body: no claim possible; fall through to validation
            status, payload = handler(parsed, caller, idem)
            return status, payload
        return handler(parsed, caller, idem)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")

    def do_PATCH(self):
        self._handle("PATCH")


def _json_text(body):
    if body is None:
        return None, True
    if body == "":
        return None, False
    try:
        return json.loads(body), False
    except ValueError:
        return None, True


def main():
    port = int(os.environ.get("PORT", "8080"))
    empty_state()
    httpd = ThreadingHTTPServer
    ThreadingHTTPServer.request_queue_size = 256
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
