# Pocketful stage 2 — design notes

Base: verified stage-1 tree (revision 3414286). Stage-1 spec remains fully in force.

## Decisions
- A1 State: users keep `balance` = **total**. `held(uid)` = sum(amount − captured_amount)
  over authorizations where from_user==uid, status=="open" and not expired.
  `available = total − held` (never negative — reset rejects over-seeded holds, and
  no operation can hold more than available). New State fields: `ttl` (int, default 600),
  `authorizations` {id -> record}. Record: {authorization_id, from_user_id, to_user_id,
  amount, captured_amount, note, visibility, status, expires_at (str), expires_dt,
  payment_id, payment_ids, created_at, seq}.
- A2 Expiry: `sweep_expired(s)` flips open→expired when expires_dt <= now; called at the
  top of every handler that reads/writes held, /me, authorizations, payments, request pay,
  settlements (all already under the global lock). "Even if no request occurred at the
  deadline" is satisfied because every read re-checks.
- A3 GET /me: adds total (=balance), available, held.
- A4 Funds: POST /payments, POST /requests/{id}/pay, POST /settlements,
  POST /authorizations all check **available**. Settlement affordability:
  available(uid) + net_delta >= 0 per touched wallet. Captures spend held funds
  (no available check).
- A5 POST /authorizations (idem): same shape/order as payments; to_handle required
  (422) / string (400); 404 unknown; 422 self_payment (same code as payments table);
  409 insufficient_funds on available. expires_at = created_at + ttl.
- A6 POST /authorizations/{id}/capture (idem): body {amount?, final?}. Order:
  404 → 403 (not the receiver) → sweep → status expired→409 authorization_expired,
  other non-open→409 authorization_not_open → amount rules (omitted=remaining;
  present: wrong JSON type→400, non-integral/<1→422 validation_failed,
  >remaining→422 capture_exceeds_authorization) → final must be bool if present (400).
  Effect: transfer from→to with auth note/visibility, authorization_id set,
  request_id null; captured_amount+=, payment_ids.append, payment_id=latest;
  closed (status "captured") iff remaining_after==0 OR final==true.
- A7 POST /authorizations/{id}/void: no key; only payer (403); 404; already voided→200;
  captured/expired→409 authorization_not_open.
- A8 GET /authorizations: direction outgoing=caller is payer, incoming=caller is
  receiver; status filter over 4 statuses (clock-expired matches expired only);
  paging identical to /requests.
- A9 Every authorization response (201 create, capture list items, void 200, GET list)
  carries remaining_amount = amount − captured_amount (0 when closed), plus
  payment_id (latest) and payment_ids (all, in order).
- A10 Payment objects gain `authorization_id` (null when not from a capture).
  payment_obj uses .get() so stage-1 exports (no such key) still render.
- A11 Fixture: authorization_ttl_seconds (int>0, default 600; bool rejected);
  authorizations list (default []): id unique ≤64, from/to reference users,
  amount integral 1..1e9, note str ≤200 (default ""), visibility (default "public"),
  status one of 4 (default "open"), expires_at parseable RFC3339 (required),
  captured_amount int 0..amount (default 0), payment_ids list[str] (default []).
  Reset error 422 (nothing changed) when some user's unexpired open seeded holds sum
  over their balance, at reset time.
- A12 Export/import: state gains ttl + authorizations (with expires_at str,
  payment_ids, captured_amount). Import accepts stage-1 exports (both omitted →
  ttl 600, no authorizations). expires_dt re-parsed on import.
- A13 Idempotency: /authorizations and /authorizations/{id}/capture join the five
  stage-1 paths through the same _do_write/idem machinery (7 total).

## UI decisions
- U1 Server-rendered HTML (no client-side rendering needed), one shared stylesheet,
  all data-testids per spec. JS only for: form submits via fetch, live split preview,
  in-place refreshes, idempotency-key derivation, latest-refresh-wins.
- U2 Auth: login/signup set HttpOnly cookie `pocketful_session` = bearer token
  (same token store → survives export/import). resolve_caller: Authorization header
  first, then cookie. Logout = POST /auth/logout clears the cookie.
- U3 Accept sniffing: GET /requests and /authorizations → HTML iff Accept contains
  text/html, else JSON (existing handler). All other UI routes render HTML always.
- U4 Money format: mu==0 → "1200 JPY"; else "N.nn EUR" (groupless decimal, exactly
  mu places). data-amount = raw minor units.
- U5 Idempotency key derivation (client): SHA-256 hex (64 chars) of
  `path + canonical(body)` — deterministic per form values, so unchanged resubmit
  replays (200, no double money) and any field change mints a new key. FNV-1a
  fallback if crypto.subtle is unavailable.
- U6 Pay/authorize forms keep their values after success; on 4xx show *-error and
  refresh balance/feed (inputs preserved); on network failure/timeout show
  *-uncertain (not error), keep retryable with the same derived key.
- U7 wallet-refresh: monotonically increasing seq; a refresh response is applied
  only if its seq is still the highest issued (latest wins, out-of-order safe).
- U8 Split preview: client-side §9 equal split on input (same rule as server);
  one split-share-{handle} per participant in given order; submit uses server result.
- U9 /requests buttons: pay (derived key from request id), decline, cancel;
  on any outcome re-render the lists; refusals also show request-error.
- U10 Visual system: system font stack, calm palette (ink/slate + one accent),
  available funds as the headline number (largest type), total/held secondary,
  status chips, direction arrows (in/out), visibility dot (public/private),
  labeled inputs, visible focus rings, 375px-clean single column, no h-scroll.

## Open items — all resolved
- [x] O1: `final` wrong type → 400 malformed_request (implemented).
- [x] O2: naive `expires_at` parsed as UTC (implemented in parse_rfc3339).
- [x] O3: signed-out UI gets → 302 /login (implemented).
- [x] O4: empty-note element rendered with empty text (implemented).

## Learned during verification (s2-run-1 → s2-run-6)
- Public endpoints must also serve REQUESTS WITH TOKENS: the harness's
  authenticated clients call /_test/* and /auth/* with Authorization headers.
  Route public paths to their handlers regardless of a valid token.
- Error elements (pay-error, request-error, ...) must be ABSENT from the DOM
  when there is no error — the suites use query_selector(...)==None. Created
  on demand, removed on success. (CSS display:none is not enough.)
- List containers (incoming-list, outgoing-list, authorization-list,
  activity-list) must always render and be visible; empty state inside.
- activity-parties-* must contain BOTH raw handles (no "You").
- request-amount-*/activity-amount-* testids ride on the amount span.
- Browser fetch() to our own HTML routes needs Accept: text/html, else the
  Accept-sniffing returns JSON (404/401 envelope) and rerender breaks.
- python str.format does not recurse into substituted values: sub-templates
  carrying their own placeholders (buttons with data-rid) must be formatted
  first with .format() on themselves.
