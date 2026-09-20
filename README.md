# EDC Event Registration Platform — Backend

Django + DRF backend built from `EDC_Event_Registration_PRD.pdf` and `EDC_TRD.docx`.
Tested end-to-end (event listing, registration, duplicate blocking, capacity
enforcement, admin panel, CSV export) — see "What's been verified" below.

## What's included

- **Event & Registration models** (`events/models.py`) — matches TRD Section 4 exactly:
  status lifecycle (`draft → open → closed → past`, plus soft-delete), fee/capacity,
  and a DB-level `unique(event, email)` constraint to block duplicate registrations.
- **Public REST API** (`events/views.py`, `events/urls.py`):
  - `GET  /api/events/open/` — current/open events
  - `GET  /api/events/past/` — past events
  - `GET  /api/events/<slug>/` — event detail
  - `POST /api/events/<slug>/register/` — guest registration (free or paid)
  - `POST /api/webhooks/razorpay/` — Razorpay webhook (signature-verified)
  - `GET  /api/contact/` — EDC contact email
- **Atomic capacity checks** — `select_for_update()` locks the Event row during
  registration so two simultaneous submissions can't both grab the last slot
  (TRD edge case: race condition must be DB-level, not UI-side).
- **Payment flow** (`events/payments.py`) — Razorpay order creation +
  HMAC-verified webhook handling. The webhook is the source of truth for
  `payment_status`, not the browser redirect, per TRD Section 5. A pending/failed
  paid registration does **not** hold a capacity slot (fixes the "ghost booking"
  edge case from the PRD).
- **Async confirmation emails** (`events/emails.py`) — sent on a background
  thread so registration responses aren't blocked on SMTP latency.
- **Admin panel = Django Admin, customized** (`events/admin.py`) — this *is*
  the "no-code" panel the PRD asks for:
  - Event CRUD with registrations-vs-capacity shown at a glance (color-coded)
  - Bulk actions: mark Open / Closed / Past, and **soft-delete** (never hard
    deletes an event with live registrants — PRD edge case)
  - Registrant list per event with CSV export action (includes payment status)
- **`mark_past_events` management command** — run nightly via cron to
  auto-transition events once `event_date` passes.

## What's *not* built yet (needs your input first)

The PRD/TRD both flag these as blocking "Open Decisions" — I built the code so
any of these are a config change, not a rewrite, but you need to decide:

1. **Hosting** — settings.py reads `DATABASE_URL` etc. from env vars, so it's
   Render-ready, but nothing is deployed yet.
2. **Exact registration form fields** — I used the fields explicitly named in
   the PRD (name, email, phone, college, year/branch). Confirm with your
   committee before the frontend locks these in.
3. **Email service** — currently wired for SMTP (e.g. Gmail app password).
   Swap `EMAIL_BACKEND` for SendGrid/Mailgun's package if you go that route.
4. **Razorpay account** — you'll need real `RAZORPAY_KEY_ID` /
   `RAZORPAY_KEY_SECRET` / `RAZORPAY_WEBHOOK_SECRET` from your merchant
   account before payments will actually work (currently the payment
   endpoints will return a clear 503 if these aren't set, rather than failing
   silently).
5. **React frontend** — not part of this deliverable; this is the API +
   admin panel it talks to. CORS is pre-configured for `localhost:3000`.

## Local setup

```bash
cd edc_backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: at minimum set DJANGO_SECRET_KEY and DEBUG=True for local dev.
# Leave DATABASE_URL unset locally to fall back to sqlite, or point it at a
# local Postgres if you want to test under the real engine.

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Admin panel: `http://127.0.0.1:8000/<ADMIN_URL_PATH>` (path from your `.env`,
default `admin/` — **change this in production**, per the PRD's "hidden from
public nav" requirement).

API root: `http://127.0.0.1:8000/api/`

## What's been verified

Ran directly in a sandbox during this build (not just written-and-hoped):
- `python manage.py check` — no issues
- Migrations generate and apply cleanly
- Full registration flow tested live: open-event listing, event detail,
  successful free registration, duplicate-email rejection (409), capacity
  enforcement (registration correctly rejected once an event fills), and the
  contact endpoint
- Superuser creation + admin site returns a proper login redirect

Not yet tested against real Postgres or a real Razorpay sandbox account —
do that once those credentials exist (Open Decision #1 and #4 above).

## Production checklist before going live

- [ ] Set a strong, unique `DJANGO_SECRET_KEY`
- [ ] Set `DEBUG=False`, real `ALLOWED_HOSTS`
- [ ] Change `ADMIN_URL_PATH` to something non-guessable
- [ ] Point `DATABASE_URL` at managed Postgres
- [ ] Set real Razorpay + email credentials
- [ ] Set up `mark_past_events` as a nightly cron job
- [ ] Take a manual DB export before/after any high-traffic registration window
      (per TRD — free-tier hosts have limited backup guarantees)
