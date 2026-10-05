---
title: Pocketful Demo
sdk: docker
app_port: 8080
---

# Pocketful — live demo

Live demo of the Pocketful stage-4 payments service, built end-to-end by
three AI seats in one Band room from a single human message
(WeAreDevelopers x BAND — AI Dark Factory hackathon, team Whynot).
Source (the judged submission): https://github.com/egyprobatmeger/dark-factory-pocketful

Demo accounts (play money, EUR):
- demo-a@example.com / demo-pass-123 — starts with EUR 1,000.00
- demo-b@example.com / demo-pass-456 — starts with EUR 1,000.00

Or register your own account. The service keeps state in memory;
on a cold start it re-seeds the two demo accounts above.

Packaging repair note (2026-10-05, this demo copy only): the stage-4
UI's Log out button navigates to GET /auth/logout, which the service
did not route (it answered a raw 404 JSON), and the logout handler
itself crashed on an invalid argument. In this demo copy only,
app.py now routes GET /auth/logout like POST and the handler clears
the session cookie with a valid redirect (two lines). The judged
submission code (stage-1..stage-4) is unchanged — byte-identical to
what the factory produced.
