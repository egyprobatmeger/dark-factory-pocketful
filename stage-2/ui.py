"""Pocketful stage 2 — server-rendered consumer UI.

One shared stylesheet and client script. Every integration-tested element
carries its spec data-testid. The page model is plain dicts built by app.py.
"""
import json
import re
from datetime import datetime

from urllib.parse import urlsplit


def esc(v):
    if v is None:
        return ""
    return (str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def amount_text(minor, minor_units):
    """Decimal text a person types: 1500 with 2 places is '15.00'."""
    if minor_units == 0:
        return str(minor)
    text = str(minor).rjust(minor_units + 1, "0")
    return "{}.{}".format(text[:-minor_units], text[-minor_units:])


def money(minor, minor_units, currency):
    if minor_units == 0:
        return "{} {}".format(minor, currency)
    return "{}{} {}".format("-" if minor < 0 else "",
                            amount_text(abs(int(minor)), minor_units),
                            currency)


def fmt_ts(iso):
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%b %-d, %-H:%M")
    except (ValueError, TypeError):
        return iso


def rel_time(iso):
    try:
        dt = datetime.fromisoformat(iso)
        now = datetime.now(dt.tzinfo)
        secs = int((now - dt).total_seconds())
    except (ValueError, TypeError):
        return ""
    if secs < 5:
        return "just now"
    if secs < 60:
        return "{}s ago".format(secs)
    if secs < 3600:
        return "{}m ago".format(secs // 60)
    if secs < 86400:
        return "{}h ago".format(secs // 3600)
    return "{}d ago".format(secs // 86400)


STATUS_LABELS = {"pending": "Pending", "paid": "Paid", "declined": "Declined",
                 "cancelled": "Cancelled", "open": "Open",
                 "captured": "Captured", "voided": "Voided", "expired": "Expired"}

CSS = """
:root{
  --bg:#f4f6fa; --surface:#ffffff; --ink:#17203a; --muted:#5d6b88;
  --line:#e2e7f0; --brand:#2450d6; --brand-ink:#ffffff;
  --danger:#c62f4b; --danger-bg:#fdf1f3; --ok:#1e7f4f; --ok-bg:#e9f7f0;
  --warn-bg:#fbf3e2; --chip:#eef1f7; --shadow:0 1px 2px rgba(23,32,58,.06),
  0 8px 24px rgba(23,32,58,.06);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--ink);
  font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
a{color:var(--brand);text-decoration:none}
button{font:inherit}
.topbar{background:var(--surface);border-bottom:1px solid var(--line);
  position:sticky;top:0;z-index:5}
.topbar-in{max-width:1060px;margin:0 auto;display:flex;align-items:center;gap:18px;
  padding:10px 20px;min-height:58px}
.brand{display:flex;align-items:center;gap:9px;font-weight:700;font-size:18px;color:var(--ink)}
.brand svg{display:block}
.nav{display:flex;gap:4px;margin-left:8px;flex:1;min-width:0;overflow-x:auto}
.nav a{padding:8px 12px;border-radius:9px;color:var(--muted);font-weight:600;white-space:nowrap}
.nav a.active,.nav a:hover{background:var(--chip);color:var(--ink)}
.userbox{display:flex;align-items:center;gap:12px;margin-left:auto;flex:0 0 auto}
.who{display:flex;flex-direction:column;line-height:1.15;text-align:right}
.who-name{font-weight:650;font-size:14px}
.handle{color:var(--muted);font-size:12.5px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;
  border:1px solid transparent;border-radius:10px;padding:9px 16px;font-weight:650;
  cursor:pointer;background:var(--chip);color:var(--ink);text-align:center}
.btn:hover{filter:brightness(.98)}
.btn:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,
textarea:focus-visible{outline:3px solid rgba(36,80,214,.45);outline-offset:1px}
.btn-primary{background:var(--brand);color:var(--brand-ink)}
.btn-quiet{background:transparent;color:var(--muted);border-color:transparent}
.btn-danger{background:var(--danger-bg);color:var(--danger)}
.btn-small{padding:6px 12px;font-size:14px;border-radius:8px}
.btn[disabled]{opacity:.55;cursor:default}
.wrap{max-width:1060px;margin:0 auto;padding:24px 20px 56px}
.grid{display:grid;grid-template-columns:1.05fr .95fr;gap:20px;align-items:start}
@media (max-width:860px){.grid{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;
  box-shadow:var(--shadow);padding:20px;margin-bottom:20px}
.card h2{margin:0 0 14px;font-size:16px;letter-spacing:.2px}
.stack{display:flex;flex-direction:column;gap:16px}
.wallet-top{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;flex-wrap:wrap}
.wallet-kicker{color:var(--muted);font-weight:600;font-size:13px;letter-spacing:.4px;
  text-transform:uppercase}
.wallet-num{font-size:42px;font-weight:750;letter-spacing:-.5px;line-height:1.1;margin-top:2px;
  font-variant-numeric:tabular-nums}
.wallet-sub{display:flex;gap:22px;margin-top:14px;flex-wrap:wrap}
.wallet-sub .k{color:var(--muted);font-size:12.5px;font-weight:600;text-transform:uppercase;
  letter-spacing:.4px}
.wallet-sub .v{font-size:16px;font-weight:650;font-variant-numeric:tabular-nums}
.field{display:flex;flex-direction:column;gap:6px;margin-bottom:14px}
.field label{font-size:13.5px;font-weight:650;color:var(--ink)}
.field .hint{color:var(--muted);font-size:12px}
input[type=text],input[type=email],input[type=password],input[type=number],
select,textarea{font:inherit;color:var(--ink);background:var(--surface);
  border:1px solid #c9d2e2;border-radius:10px;padding:10px 12px;width:100%}
textarea{resize:vertical;min-height:44px}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media (max-width:520px){.row2{grid-template-columns:1fr}}
.amount-wrap{position:relative}
.amount-wrap input{padding-right:64px;font-variant-numeric:tabular-nums}
.amount-wrap .unit{position:absolute;right:12px;top:50%;transform:translateY(-50%);
  color:var(--muted);font-size:13px;font-weight:650;pointer-events:none}
.err-slot:empty{display:none}
.error{background:var(--danger-bg);color:var(--danger);border-radius:10px;
  padding:10px 12px;font-size:14px;font-weight:600;margin-bottom:14px}
.error.show{display:block}
.form-foot{display:flex;align-items:center;gap:12px;margin-top:4px}
.foot-note{color:var(--muted);font-size:12.5px}
.list{display:flex;flex-direction:column}
.item{display:flex;align-items:center;gap:14px;padding:13px 2px;border-top:1px solid var(--line)}
.item:first-child{border-top:none;padding-top:2px}
.item:last-child{padding-bottom:2px}
.amt{font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}
.amt .in{color:var(--ok)}
.amt .out{color:var(--ink)}
.item-main{flex:1;min-width:0}
.parties{font-weight:650;font-size:14.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.meta{color:var(--muted);font-size:13px;display:flex;gap:10px;align-items:center;
  flex-wrap:wrap;margin-top:2px}
.note{color:var(--muted);font-size:13.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chip{display:inline-block;background:var(--chip);color:var(--muted);border-radius:999px;
  padding:2px 10px;font-size:12px;font-weight:650;white-space:nowrap}
.chip.status-open,.chip.status-pending{background:var(--warn-bg);color:#8a6116}
.chip.status-paid,.chip.status-captured{background:var(--ok-bg);color:var(--ok)}
.chip.status-declined,.chip.status-cancelled,.chip.status-voided,
.chip.status-expired{background:var(--chip);color:var(--muted)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--muted);
  margin-right:6px}
.dot.public{background:var(--ok)}
.dot.private{background:#8a6116}
.empty{color:var(--muted);padding:22px 4px;font-size:14.5px}
.empty b{color:var(--ink)}
.actions{display:flex;gap:8px;flex:0 0 auto;flex-wrap:wrap;justify-content:flex-end}
.section-head{display:flex;align-items:center;justify-content:space-between;gap:10px;
  margin:26px 0 10px}
.section-head h2{margin:0;font-size:15px}
.split-preview{background:var(--chip);border-radius:10px;padding:12px 14px;margin-bottom:14px;
  font-size:14px;display:none}
.split-preview.show{display:block}
.share-row{display:flex;justify-content:space-between;gap:12px;padding:3px 0}
.share-row .h{color:var(--muted);font-weight:650}
.share-row .a{font-weight:700;font-variant-numeric:tabular-nums}
.capture-row{display:flex;align-items:center;gap:10px;margin-top:10px;flex-wrap:wrap}
.capture-row input{max-width:150px;font-variant-numeric:tabular-nums}
.section-title{font-size:13px;font-weight:700;color:var(--muted);text-transform:uppercase;
  letter-spacing:.5px;margin:18px 0 4px}
.auth-card{max-width:420px;margin:8vh auto 0}
.auth-card h1{font-size:22px;margin:0 0 4px}
.auth-sub{color:var(--muted);margin:0 0 18px;font-size:14.5px}
.auth-foot{margin-top:14px;color:var(--muted);font-size:13.5px;text-align:center}
.page-head{margin:6px 0 18px}
.page-head h1{margin:0;font-size:22px}
.page-head p{margin:4px 0 0;color:var(--muted);font-size:14.5px}
footer{color:var(--muted);font-size:12.5px;text-align:center;padding:18px 0 34px}
"""

SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Pocketful</title>
<style>{css}</style>
</head>
<body>
<header class="topbar"><div class="topbar-in">
  <a class="brand" href="/"><svg width="24" height="24" viewBox="0 0 24 24" fill="none"
    aria-hidden="true"><rect x="2" y="5" width="20" height="15" rx="4" fill="#2450d6"/>
    <rect x="2" y="5" width="20" height="6" rx="3" fill="#3d68e8"/>
    <circle cx="17" cy="14.5" r="2.4" fill="#ffffff"/></svg>Pocketful</a>
  <nav class="nav" aria-label="Main">
    <a href="/" class="{nav_home}">Home</a>
    <a href="/requests" class="{nav_requests}">Requests</a>
    <a href="/split" class="{nav_split}">Split</a>
    <a href="/authorizations" class="{nav_authz}">Authorizations</a>
  </nav>
  {userbox}
</div></header>
<main class="wrap">{content}</main>
<footer>Pocketful — demo service. All amounts are local minor units.</footer>
<script>
"use strict";
window.POCKET = {{page: "{page}", minorUnits: {mu}, currency: "{cur}"}};
{client}
</script>
</body>
</html>
"""

LOGO_ONLY_USERBOX = ""

USERBOX = """<div class="userbox">
  <div class="who">
    <span class="who-name" data-testid="current-user">{name}</span>
    <span class="handle" data-testid="current-handle">{handle}</span>
  </div>
  <button type="button" class="btn btn-quiet btn-small" data-testid="logout-button">Log out</button>
</div>"""


def shell(title, page, content, user=None, client="", mu=2, cur="EUR"):
    nav = {
        "nav_home": "active" if page == "home" else "",
        "nav_requests": "active" if page == "requests" else "",
        "nav_split": "active" if page == "split" else "",
        "nav_authz": "active" if page == "authorizations" else "",
    }
    if user:
        userbox = USERBOX.format(name=esc(user["display_name"] or user["handle"]),
                                 handle=esc(user["handle"]))
    else:
        userbox = ""
    return SHELL.format(title=esc(title), css=CSS, nav_home=nav["nav_home"],
                        nav_requests=nav["nav_requests"], nav_split=nav["nav_split"],
                        nav_authz=nav["nav_authz"], userbox=userbox, content=content,
                        page=page, mu=mu, cur=esc(cur), client=client)


def render_login(error_msg=None):
    err = ""
    if error_msg:
        err = '<p class="error show" data-testid="auth-error">{}</p>'.format(esc(error_msg))
    content = """<div class="card auth-card">
<h1>Log in</h1>
<p class="auth-sub">Welcome back to Pocketful.</p>
{err}
<form data-form="login">
  <div class="field"><label for="le">Email</label>
    <input type="email" id="le" data-testid="login-email" name="email" required autocomplete="email"></div>
  <div class="field"><label for="lp">Password</label>
    <input type="password" id="lp" data-testid="login-password" name="password" required autocomplete="current-password"></div>
  <button type="submit" class="btn btn-primary" data-testid="login-submit" style="width:100%">Log in</button>
</form>
<p class="auth-foot">New here? <a href="/signup">Create an account</a></p>
</div>""".format(err=err)
    return shell("Log in", "login", content, client=CLIENT_JS)


def render_signup(error_msg=None):
    err = ""
    if error_msg:
        err = '<p class="error show" data-testid="auth-error">{}</p>'.format(esc(error_msg))
    content = """<div class="card auth-card">
<h1>Create your account</h1>
<p class="auth-sub">One wallet, ready to move money.</p>
{err}
<form data-form="signup">
  <div class="field"><label for="se">Email</label>
    <input type="email" id="se" data-testid="signup-email" name="email" required autocomplete="email"></div>
  <div class="field"><label for="sd">Display name</label>
    <input type="text" id="sd" data-testid="signup-display-name" name="display_name" required></div>
  <div class="field"><label for="sp">Password</label>
    <input type="password" id="sp" data-testid="signup-password" name="password" required
      autocomplete="new-password"><span class="hint">At least 8 characters.</span></div>
  <button type="submit" class="btn btn-primary" data-testid="signup-submit" style="width:100%">Create account</button>
</form>
<p class="auth-foot">Already have an account? <a href="/login">Log in</a></p>
</div>""".format(err=err)
    return shell("Sign up", "signup", content, client=CLIENT_JS)


def wallet_card(dm):
    held_html = ""
    if dm["held"] > 0:
        held_html = ('<div><div class="k">Held</div>'
                     '<div class="v" data-testid="wallet-held" '
                     'data-amount="{held}">{held_txt}</div></div>').format(
            held=dm["held"], held_txt=esc(money(dm["held"], dm["mu"], dm["cur"])))
    return """<section class="card wallet" data-testid="wallet" aria-label="Wallet">
  <div class="wallet-top">
    <div>
      <div class="wallet-kicker">Available to spend</div>
      <div class="wallet-num" data-testid="wallet-available" data-amount="{avail}">{avail_txt}</div>
      <div style="color:var(--muted);font-size:13px;margin-top:6px">
        Total <span data-testid="wallet-balance" data-amount="{total}">{total_txt}</span>
        {heldbit}
      </div>
    </div>
    <button type="button" class="btn btn-quiet btn-small" data-testid="wallet-refresh"
      title="Refresh balance and activity">&#8635;&nbsp;Refresh</button>
  </div>
</section>""".format(
        avail=dm["available"], avail_txt=esc(money(dm["available"], dm["mu"], dm["cur"])),
        total=dm["total"], total_txt=esc(money(dm["total"], dm["mu"], dm["cur"])),
        heldbit=held_html)


def input_field(prefix, label, name, placeholder="", autocomplete="off"):
    return """<div class="field"><label for="{pid}">{label}</label>
  <input type="text" id="{pid}" data-testid="{pid}" name="{name}"
    autocomplete="{ac}" placeholder="{ph}"></div>""".format(
        pid=prefix, label=label, name=name, ac=autocomplete, ph=esc(placeholder))


def amount_field(prefix, label, name, currency):
    return """<div class="field"><label for="{pid}">{label}</label>
  <div class="amount-wrap">
    <input type="text" id="{pid}" data-testid="{pid}" name="{name}" inputmode="decimal"
      autocomplete="off" placeholder="0.00">
    <span class="unit">{cur}</span>
  </div></div>""".format(pid=prefix, label=label, name=name, cur=esc(currency))


def visibility_field(prefix):
    return """<div class="field"><label for="{pid}">Visibility</label>
  <select id="{pid}" data-testid="{pid}" name="visibility">
    <option value="public">Public — anyone can see it</option>
    <option value="private">Private — only you two</option>
  </select></div>""".format(pid=prefix)


def pay_card(dm):
    return """<form class="card" data-form="pay" method="post" action="/api/ui/pay">
<h2>Send money</h2>
<div class="err-slot" data-slot="pay-error"></div>
<div class="err-slot" data-slot="pay-uncertain"></div>
{handle}{amount}{note}{vis}
<div class="form-foot">
  <button type="submit" class="btn btn-primary" data-testid="pay-submit">Send payment</button>
  <span class="foot-note">Money moves immediately.</span>
</div>
</form>""".format(
        handle=input_field("pay-handle", "To", "handle", placeholder="recipient",
                           autocomplete="off"),
        amount=amount_field("pay-amount", "Amount", "amount", dm["cur"]),
        note="""<div class="field"><label for="pay-note">Note</label>
  <textarea id="pay-note" data-testid="pay-note" name="note" rows="1"></textarea></div>""",
        vis=visibility_field("pay-visibility"))


def request_card(dm):
    return """<form class="card" data-form="request" method="post" action="/api/ui/request">
<h2>Ask for money</h2>
<div class="err-slot" data-slot="request-error"></div>
{handle}{amount}{note}
<div class="form-foot">
  <button type="submit" class="btn" data-testid="request-submit">Send request</button>
  <span class="foot-note">They can pay it from their Requests page.</span>
</div>
</form>""".format(
        handle=input_field("request-handle", "From", "handle", placeholder="person"),
        amount=amount_field("request-amount", "Amount", "amount", dm["cur"]),
        note="""<div class="field"><label for="request-note">Note</label>
  <textarea id="request-note" data-testid="request-note" name="note" rows="1"></textarea></div>""")


def authorize_card(dm):
    return """<form class="card" data-form="authorize" method="post" action="/api/ui/authorize">
<h2>Authorize payment</h2>
<div class="err-slot" data-slot="authorize-error"></div>
{handle}{amount}{note}{vis}
<div class="form-foot">
  <button type="submit" class="btn btn-primary" data-testid="authorize-submit">Authorize</button>
  <span class="foot-note">Reserves funds; they collect it later.</span>
</div>
</form>""".format(
        handle=input_field("authorize-handle", "To", "handle", placeholder="recipient"),
        amount=input_field("authorize-amount", "Amount", "amount", placeholder="0.00"),
        note="""<div class="field"><label for="authorize-note">Note</label>
  <textarea id="authorize-note" data-testid="authorize-note" name="note" rows="1"></textarea></div>""",
        vis=visibility_field("authorize-visibility"))


def feed_item(dm, p):
    pid = p["payment_id"]
    me = dm["handle"]
    outgoing = p["from_handle"] == me
    parties = "{} → {}".format(esc(p["from_handle"]), esc(p["to_handle"]))
    note = esc(p["note"]) if p["note"] else ""
    arrow = ('<span class="out">&#8595; out</span>' if outgoing
             else '<span class="in">&#8593; in</span>')
    return """<div class="item" data-testid="activity-item-{pid}" data-visibility="{vis}">
  <div class="amt">{arrow} <span data-testid="activity-amount-{pid}">{amt}</span></div>
  <div class="item-main">
    <div class="parties" data-testid="activity-parties-{pid}">{parties}</div>
    <div class="meta"><span class="note" data-testid="activity-note-{pid}">{note}</span>
      <span><span class="dot {vis}"></span>{vislabel} &middot; {ts}</span></div>
  </div>
</div>""".format(pid=esc(pid), vis=p["visibility"],
                  arrow=arrow, amt=esc(money(p["amount"], dm["mu"], dm["cur"])),
                  parties=parties, note=note, vislabel="Public" if p["visibility"] == "public"
                  else "Private", ts=esc(fmt_ts(p["created_at"])))


def feed_card(dm):
    items = "".join(feed_item(dm, p) for p in dm["payments"])
    if dm["payments"]:
        body = '<div class="list" data-testid="activity-list">{}</div>'.format(items)
    else:
        body = """<div class="empty" data-testid="empty-activity">
  <b>No activity yet.</b><br>Sent and received payments show up here.</div>"""
    return """<div class="card" data-testid="feed-card">
<h2>Activity</h2>
{body}
</div>""".format(body=body)


def render_home(dm, page_state=""):
    content = """{wallet}
<div class="grid">
  <div class="stack">
    {pay}
    {request}
    {authorize}
  </div>
  {feed}
</div>
{page_state}""".format(wallet=wallet_card(dm), pay=pay_card(dm),
                        request=request_card(dm), authorize=authorize_card(dm),
                        feed=feed_card(dm), page_state=page_state)
    return shell("Wallet", "home", content, user=dm["user"], client=CLIENT_JS,
                 mu=dm["mu"], cur=dm["cur"])


def request_item(dm, r):
    rid = r["request_id"]
    incoming = r["payer_handle"] == dm["handle"]
    party = esc(r["payer_handle"]) if incoming else esc(r["requester_handle"])
    verb = "wants" if incoming else "you asked"
    actions = ""
    if r["status"] == "pending":
        if incoming:
            actions = """<div class="actions">
              <button type="button" class="btn btn-danger btn-small"
                data-testid="request-decline-{}" data-rid="{}" data-act="decline">Decline</button>
              <button type="button" class="btn btn-primary btn-small"
                data-testid="request-pay-{}" data-rid="{}" data-act="pay">Pay now</button>
            </div>""".format(esc(rid), esc(rid), esc(rid), esc(rid))
        else:
            actions = """<div class="actions">
              <button type="button" class="btn btn-quiet btn-small"
                data-testid="request-cancel-{}" data-rid="{}" data-act="cancel">Cancel</button>
            </div>""".format(esc(rid), esc(rid))
    return """<div class="item" data-testid="request-item-{rid}" data-status="{status}">
  <div class="amt"><span data-testid="request-amount-{rid}">{amt}</span></div>
  <div class="item-main">
    <div class="parties"><span class="dot {vis}"></span>{party} {verb} this</div>
    <div class="meta"><span class="chip status-{status}">{label}</span>
      <span>{note}</span><span>&middot; {ts}</span></div>
  </div>
  {actions}
</div>""".format(rid=esc(rid), status=r["status"],
                  amt=esc(money(r["amount"], dm["mu"], dm["cur"])),
                  party=party, verb=verb,
                  vis="public" if r.get("visibility", "public") == "public" else "private",
                  label=esc(STATUS_LABELS.get(r["status"], r["status"])),
                  note=esc(r["note"]) if r["note"] else "",
                  ts=esc(fmt_ts(r["created_at"])), actions=actions)


def render_requests(dm):
    empty = ""
    if not dm["incoming"] and not dm["outgoing"]:
        empty = """<div class="card" style="margin-bottom:24px">
  <div class="empty" data-testid="empty-requests">
    <b>No requests yet.</b><br>Money you ask for, and people who ask you, show up here.
  </div>
</div>"""
    inc = "".join(request_item(dm, r) for r in dm["incoming"]) or \
        '<div class="empty">No incoming requests.</div>'
    out = "".join(request_item(dm, r) for r in dm["outgoing"]) or \
        '<div class="empty">No outgoing requests.</div>'
    content = """<div class="page-head"><h1>Requests</h1>
  <p>Pay, decline or cancel — money only moves when you pay.</p></div>
  <div class="err-slot" data-slot="request-error" style="margin-top:0"></div>
  {empty}
  <div class="section-title">Incoming — you pay</div>
  <div class="card" style="margin-bottom:24px">
    <div class="list" data-testid="incoming-list">{inc}</div>
  </div>
  <div class="section-title">Outgoing — you asked</div>
  <div class="card" style="margin-bottom:24px">
    <div class="list" data-testid="outgoing-list">{out}</div>
  </div>""".format(empty=empty, inc=inc, out=out)
    return shell("Requests", "requests", content, user=dm["user"], client=CLIENT_JS,
                 mu=dm["mu"], cur=dm["cur"])


def render_split(dm):
    content = """<div class="page-head"><h1>Split a bill</h1>
  <p>Enter the total and the people, in order. Pocketful works out exact shares.</p></div>
<div class="card">
  <div class="err-slot" data-slot="split-error"></div>
  <div class="field"><label for="split-amount">Total amount</label>
    <div class="amount-wrap"><input type="text" id="split-amount" data-testid="split-amount"
      name="amount" inputmode="decimal" autocomplete="off" placeholder="0.00"></div></div>
  <div class="field"><label for="split-handles">People</label>
    <input type="text" id="split-handles" data-testid="split-handles" name="handles"
      autocomplete="off" placeholder="ada, bob, cy">
    <span class="hint">Separate handles with commas, in the order you want the split.</span></div>
  <div class="field"><label for="split-note">Note</label>
    <input type="text" id="split-note" data-testid="split-note" name="note"
      autocomplete="off" placeholder="Dinner"></div>
  <div class="split-preview" data-testid="split-preview" aria-live="polite"></div>
  <div class="form-foot">
    <button type="button" class="btn btn-primary" data-testid="split-submit">Split it</button>
    <span class="foot-note">Creates a request for each other person.</span>
  </div>
</div>"""
    return shell("Split", "split", content, user=dm["user"], client=CLIENT_JS,
                 mu=dm["mu"], cur=dm["cur"])


def authz_item(dm, a):
    aid = esc(a["authorization_id"])
    mine = a["from_handle"] == dm["handle"]
    party = esc(a["to_handle"]) if mine else esc(a["from_handle"])
    verb = "you reserved for" if mine else "is owed to"
    capture = ""
    if not mine and a["status"] == "open":
        remaining = a["remaining_amount"]
        capture = """<div class="capture-row">
          <input type="text" data-testid="authorization-capture-amount-{}" data-aid="{}"
            inputmode="decimal" autocomplete="off" value="{}">
          <button type="button" class="btn btn-primary btn-small"
            data-testid="authorization-capture-{}" data-aid="{}">Capture</button>
        </div>""".format(aid, aid, esc(amount_text(remaining, dm["mu"])), aid, aid)
    closed_hint = ""
    if a["status"] in ("voided", "expired"):
        hint = STATUS_LABELS.get(a["status"], a["status"])
        closed_hint = """<div class="meta"><span class="chip status-{st}">{hint}</span>
          <span>closed — no further captures</span></div>""".format(
              st=a["status"], hint=esc(hint))
    voidbtn = ""
    if mine and a["status"] == "open":
        voidbtn = """<div class="actions">
          <button type="button" class="btn btn-danger btn-small"
            data-testid="authorization-void-{}" data-aid="{}">Void</button>
        </div>""".format(aid, aid)
    captured = ""
    if a["status"] == "captured":
        captured = """<div class="meta"><span class="chip status-captured">Captured</span>
          <span>captured: <b data-testid="authorization-captured-{aid}">{cap}</b></span></div>""".format(
            aid=aid, cap=esc(money(a["captured_amount"], dm["mu"], dm["cur"])))
    return """<div class="item" data-testid="authorization-item-{aid}" data-status="{status}">
  <div class="amt"><span data-testid="authorization-amount-{aid}">{amt}</span></div>
  <div class="item-main">
    <div class="parties"><span class="dot {vis}"></span>{party} &middot; {verb} them</div>
    <div class="meta"><span class="chip status-{status}">{label}</span>
      <span>expires <span data-testid="authorization-expires-{aid}">{exp}</span></span>
      <span>&middot; {ts}</span></div>
    {captured}{capture}
  </div>
  {voidbtn}
</div>""".format(aid=aid, status=a["status"], amt=esc(money(a["amount"], dm["mu"], dm["cur"])),
                 party=party, verb=verb,
                 vis="public" if a["visibility"] == "public" else "private",
                 label=esc(STATUS_LABELS.get(a["status"], a["status"])),
                 exp=esc(a["expires_at"]), ts=esc(fmt_ts(a["created_at"])),
                 captured=captured, capture=capture, voidbtn=voidbtn)


def render_authorizations(dm):
    items = "".join(authz_item(dm, a) for a in dm["authorizations"])
    if not items:
        items = """<div class="empty" data-testid="empty-authorizations">
  <b>No authorizations yet.</b><br>Authorise a payment from your wallet to reserve funds.</div>"""
    body = '<div class="list" data-testid="authorization-list">{}</div>'.format(items)
    content = """<div class="page-head"><h1>Authorizations</h1>
  <p>Reserved funds: capture what you earned, or void what you set aside.</p></div>
  <div class="err-slot" data-slot="authorization-error" style="margin-top:0"></div>
  <div class="card">{body}</div>""".format(body=body)
    return shell("Authorizations", "authorizations", content, user=dm["user"],
                 client=CLIENT_JS, mu=dm["mu"], cur=dm["cur"])


CLIENT_JS = r"""
(function(){
  var PAGE = window.POCKET.page, MU = window.POCKET.minorUnits, CUR = window.POCKET.currency;

  function moneyText(minor){
    if (MU === 0) return minor + " " + CUR;
    var s = Math.abs(minor).toString().padStart(MU + 1, "0");
    return s.slice(0, -MU) + "." + s.slice(-MU) + " " + CUR;
  }
  function parseAmount(str){
    if (typeof str !== "string") return null;
    var s = str.trim();
    if (!s) return null;
    var re = MU === 0 ? /^\d+$/ : new RegExp("^\\d+(\\.\\d{1," + MU + "})?$");
    if (!re.test(s)) return null;
    var parts = s.split(".");
    var major = parseInt(parts[0], 10);
    var frac = parts[1] ? parseInt(parts[1].padEnd(MU, "0"), 10) : 0;
    var minor = major * Math.pow(10, MU) + frac;
    if (minor < 1) return null;
    return minor;
  }
  function fmtMinor(minor){ return moneyText(minor); }

  async function keyFor(action, fields){
    var norm = Object.keys(fields).sort().map(function(k){
      return k + "=" + String(fields[k] == null ? "" : fields[k]);
    }).join("&");
    var payload = action + "|" + norm;
    try {
      if (window.crypto && crypto.subtle) {
        var buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(payload));
        return Array.from(new Uint8Array(buf)).map(function(b){
          return b.toString(16).padStart(2, "0");
        }).join("");
      }
    } catch (e) {}
    var h = 0x811c9dc5;
    for (var i = 0; i < payload.length; i++) {
      h ^= payload.charCodeAt(i); h = (h * 0x01000193) >>> 0;
    }
    return "fnv_" + h.toString(16) + "_" + payload.length;
  }

  async function api(path, body, key){
    var res = await fetch(path, {
      method: "POST",
      headers: {"Content-Type": "application/json", "Accept": "application/json",
                "Idempotency-Key": key},
      body: JSON.stringify(body)
    });
    var data = null;
    try { data = await res.json(); } catch (e) {}
    return {status: res.status, ok: res.ok, data: data};
  }
  function errText(r){
    if (r && r.data && r.data.error && r.data.error.message) return r.data.error.message;
    if (r && r.status) return "Something went wrong (code " + r.status + ").";
    return "Something went wrong.";
  }
  function show(slot, msg){
    var slotEl = document.querySelector('[data-slot="' + slot + '"]');
    if (!slotEl) return;
    var el = slotEl.querySelector('[data-testid="' + slot + '"]');
    if (!el) {
      el = document.createElement("p");
      el.className = "error";
      el.setAttribute("role", "alert");
      el.setAttribute("data-testid", slot);
      slotEl.appendChild(el);
    }
    el.textContent = msg;
  }
  function hide(slot){
    var el = document.querySelector('[data-slot="' + slot + '"] [data-testid="' + slot + '"]');
    if (el) el.remove();
  }

  var refreshSeq = 0;
  function renderFragments(html){
    var doc = new DOMParser().parseFromString(html, "text/html");
    var out = {};
    var w = doc.querySelector('[data-fragment="wallet"] > *');
    if (w) out.wallet = w;
    var f = doc.querySelector('[data-fragment="feed"] > *');
    if (f) out.feed = f;
    return out;
  }
  function replaceBlock(sel, node){
    var cur = document.querySelector(sel);
    if (cur && node) cur.replaceWith(node);
  }
  async function refreshPage(){
    var seq = ++refreshSeq;
    try {
      var res = await fetch("/api/ui/refresh");
      if (!res.ok) return;
      var html = await res.text();
      if (seq !== refreshSeq) return;   // latest refresh wins
      var frags = renderFragments(html);
      if (frags.wallet) replaceBlock('[data-testid="wallet"]', frags.wallet);
      if (frags.feed) replaceBlock('[data-testid="feed-card"]', frags.feed);
    } catch (e) { /* keep current state */ }
  }
  function wireRefresh(){
    var b = document.querySelector('[data-testid="wallet-refresh"]');
    if (b) b.addEventListener("click", function(){ refreshPage(); });
  }

  function formVals(form){
    var v = {};
    form.querySelectorAll("input[name],select[name],textarea[name]").forEach(function(el){
      v[el.name] = el.value;
    });
    return v;
  }

  function wirePay(){
    var form = document.querySelector('[data-form="pay"]');
    if (!form) return;
    form.addEventListener("submit", async function(ev){
      ev.preventDefault();
      hide("pay-error"); hide("pay-uncertain");
      var v = formVals(form);
      var minor = parseAmount(v.amount);
      if (minor === null) { show("pay-error", "Enter a valid amount (up to " +
        (MU ? MU : 0) + " decimal place" + (MU === 1 ? "" : "s") + ")."); return; }
      var body = {to_handle: v.handle.trim(), amount: minor};
      if (v.note) body.note = v.note;
      body.visibility = v.visibility;
      var key = await keyFor("pay", {handle: v.handle.trim(), amount: minor,
        note: v.note, visibility: v.visibility});
      var btn = form.querySelector('[data-testid="pay-submit"]');
      btn.disabled = true;
      try {
        var r = await api("/payments", body, key);
        if (r.ok) { refreshPage(); }
        else if (r.status >= 400 && r.status < 500) {
          show("pay-error", errText(r)); refreshPage();
        } else {
          show("pay-uncertain", "We're not sure the payment went through. Check your balance, " +
            "then send again with the same details to retry.");
        }
      } catch (e) {
        show("pay-uncertain", "Network error — the payment may have gone through. " +
          "Check your balance, then retry with the same details.");
      }
      btn.disabled = false;
    });
  }
  function wireRequest(){
    var form = document.querySelector('[data-form="request"]');
    if (!form) return;
    form.addEventListener("submit", async function(ev){
      ev.preventDefault();
      hide("request-error");
      var v = formVals(form);
      var minor = parseAmount(v.amount);
      if (minor === null) { show("request-error", "Enter a valid amount."); return; }
      var body = {payer_handle: v.handle.trim(), amount: minor};
      if (v.note) body.note = v.note;
      var key = await keyFor("request", {handle: v.handle.trim(), amount: minor, note: v.note});
      var r = await api("/requests", body, key);
      if (r.ok) { refreshPage(); }
      else if (r.status >= 400 && r.status < 500) { show("request-error", errText(r)); }
    });
  }
  function wireAuthorize(){
    var form = document.querySelector('[data-form="authorize"]');
    if (!form) return;
    form.addEventListener("submit", async function(ev){
      ev.preventDefault();
      hide("authorize-error");
      var v = formVals(form);
      var minor = parseAmount(v.amount);
      if (minor === null) { show("authorize-error", "Enter a valid amount."); return; }
      var body = {to_handle: v.handle.trim(), amount: minor, visibility: v.visibility};
      if (v.note) body.note = v.note;
      var key = await keyFor("authorize", {handle: v.handle.trim(), amount: minor,
        note: v.note, visibility: v.visibility});
      var r = await api("/authorizations", body, key);
      if (r.ok) { refreshPage(); }
      else if (r.status >= 400 && r.status < 500) { show("authorize-error", errText(r)); }
    });
  }

  function wireSplit(){
    var form = document.querySelector('[data-testid="split-amount"]');
    if (!form) return;
    var am = document.querySelector('[data-testid="split-amount"]');
    var hs = document.querySelector('[data-testid="split-handles"]');
    var nt = document.querySelector('[data-testid="split-note"]');
    var pv = document.querySelector('[data-testid="split-preview"]');
        function handles(){
      return hs.value.split(",").map(function(s){ return s.trim(); })
        .filter(function(s){ return s.length; });
    }
    function preview(){
      var minor = parseAmount(am.value);
      var list = handles();
      if (minor === null || !list.length) { pv.classList.remove("show"); pv.innerHTML = ""; return; }
      var n = list.length, base = Math.floor(minor / n), rem = minor - base * n;
      var rows = list.map(function(h, i){
        var share = base + (i < rem ? 1 : 0);
        return '<div class="share-row"><span class="h">' + h.replace(/&/g,"&amp;")
          .replace(/</g,"&lt;") + '</span><span class="a" data-testid="split-share-'
          + h.replace(/"/g,"&quot;") + '">' + moneyText(share) + "</span></div>";
      }).join("");
      pv.innerHTML = '<div class="share-row" style="border-bottom:1px solid var(--line);padding-bottom:6px;margin-bottom:4px">'
        + "<span class=\"h\">Total</span><span class=\"a\">" + moneyText(minor)
        + "</span></div>" + rows;
      pv.classList.add("show");
    }
    am.addEventListener("input", preview);
    hs.addEventListener("input", preview);
    document.querySelector('[data-testid="split-submit"]').addEventListener("click", async function(){
      hide("split-error");
      var minor = parseAmount(am.value);
      var list = handles();
      if (minor === null) { show("split-error", "Enter a valid total amount."); return; }
      if (!list.length) { show("split-error", "Add at least one handle."); return; }
      var body = {amount: minor, participant_handles: list};
      if (nt.value) body.note = nt.value;
      var key = await keyFor("split", {amount: minor, handles: list.join(","), note: nt.value});
      var r = await api("/splits", body, key);
      if (r.ok) { location.assign("/requests"); }
      else if (r.status >= 400 && r.status < 500) { show("split-error", errText(r)); }
      else { location.assign("/requests"); }
    });
  }

  async function actionResult(r, slot){
    if (r.ok) return true;
    if (r.status >= 400 && r.status < 500) { show(slot, errText(r)); return false; }
    show(slot, "Network error — the action may have gone through.");
    return false;
  }
  // For actions whose button lives inside the re-rendered area: refresh first so
  // the list shows the new state, then surface the refusal in the error slot so
  // the re-render cannot wipe it out.
  async function actThenRefresh(r, slot, page){
    var refused = r.status >= 400 && r.status < 500;
    if (r.ok || refused) await rerender(page);
    if (r.ok) return true;
    if (refused) { show(slot, errText(r)); return false; }
    show(slot, "Network error — the action may have gone through.");
    return false;
  }
  async function rerender(page){
    try {
      var res = await fetch(page + "?_rerender=1", {headers: {
        "Accept": "text/html", "X-Rerender": "1"}});
      if (!res.ok) return;
      var html = await res.text();
      var doc = new DOMParser().parseFromString(html, "text/html");
      var main = doc.querySelector("main.wrap");
      document.querySelector("main.wrap").replaceWith(main);
      wireAll();
    } catch (e) { location.reload(); }
  }
  function wireRequests(){
    document.querySelectorAll('[data-testid^="request-pay-"],[data-testid^="request-decline-"],[data-testid^="request-cancel-"]')
      .forEach(function(btn){
        btn.addEventListener("click", async function(){
          var rid = btn.getAttribute("data-rid"), act = btn.getAttribute("data-act");
          hide("request-error");
           var r;
           if (act === "pay") {
             var key = await keyFor("requestpay", {rid: rid});
             r = await api("/requests/" + rid + "/pay", {}, key);
           } else {
             r = await api("/requests/" + rid + "/" + act, {});
           }
           actThenRefresh(r, "request-error", "/requests");
        });
      });
  }
  function wireAuthz(){
    document.querySelectorAll('[data-testid^="authorization-capture-"]')
      .forEach(function(btn){
        if (!btn.classList.contains("btn")) return;
        btn.addEventListener("click", async function(){
          var aid = btn.getAttribute("data-aid");
          hide("authorization-error");
          var input = document.querySelector('[data-testid="authorization-capture-amount-' + aid + '"]');
          var body = {};
          if (input) {
            var minor = parseAmount(input.value);
            if (minor === null) { show("authorization-error", "Enter a valid capture amount."); return; }
            body.amount = minor;
          }
          var key = await keyFor("capture", {aid: aid, amount: body.amount || "remaining"});
          var r = await api("/authorizations/" + aid + "/capture", body, key);
          actThenRefresh(r, "authorization-error", "/authorizations");
        });
      });
    document.querySelectorAll('[data-testid^="authorization-void-"]').forEach(function(btn){
      btn.addEventListener("click", async function(){
        var aid = btn.getAttribute("data-aid");
        hide("authorization-error");
        var r = await api("/authorizations/" + aid + "/void", {});
        actThenRefresh(r, "authorization-error", "/authorizations");
      });
    });
  }
  function wireLogout(){
    var b = document.querySelector('[data-testid="logout-button"]');
    if (b) b.addEventListener("click", function(){ location.assign("/auth/logout"); });
  }
  function authMessage(r){
    if (r && r.data && r.data.error) {
      var code = r.data.error.code;
      if (code === "email_taken") return "An account with that email already exists.";
      if (code === "handle_taken") return "That account name is already taken.";
      if (code === "unauthenticated") return "Incorrect email or password.";
      if (code === "validation_failed") return "Check your details — the email must be valid and the password at least 8 characters.";
    }
    return "Something went wrong. Please try again.";
  }
  function wireAuthForms(){
    document.querySelectorAll('[data-form="login"],[data-form="signup"]').forEach(function(form){
      form.addEventListener("submit", async function(ev){
        ev.preventDefault();
        var old = document.querySelector('[data-testid="auth-error"]');
        if (old) old.remove();
        var v = formVals(form);
        var body = {email: v.email, password: v.password};
        if (form.getAttribute("data-form") === "signup") body.display_name = v.display_name;
        var path = form.getAttribute("data-form") === "login" ? "/auth/login" : "/auth/signup";
        var r = await api(path, body, "");
        if (r.ok) { location.assign("/"); }
        else {
          var el = document.createElement("p");
          el.className = "error";
          el.setAttribute("role", "alert");
          el.setAttribute("data-testid", "auth-error");
          el.textContent = authMessage(r);
          form.insertBefore(el, form.firstChild);
        }
      });
    });
  }
  function wireAll(){
    wireRefresh(); wirePay(); wireRequest(); wireAuthorize();
    wireSplit(); wireRequests(); wireAuthz(); wireLogout(); wireAuthForms();
  }
  wireAll();
})();
"""
