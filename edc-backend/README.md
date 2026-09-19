# EDC Events — backend

Django + DRF + PostgreSQL. Matches the API this scaffold's serializers/views
expect the React app to call.

## 1. Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file next to `manage.py` (python-decouple reads it):

```
DJANGO_SECRET_KEY=change-me
DEBUG=True
DB_NAME=edc_events
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Create the Postgres database first:

```bash
createdb edc_events
# or, inside psql: CREATE DATABASE edc_events;
```

## 2. Run

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser   # make yourself an admin
python manage.py runserver
```

The `createsuperuser` account gets `is_staff=True` but NOT `role="admin"`
automatically — set that once via `/admin/` (Accounts > Users > your user >
Role) so the React app's admin-only screens work with your account too.

## 3. API reference

| Endpoint | Method | Who | Notes |
|---|---|---|---|
| `/api/auth/register/` | POST | anyone | `{first_name, last_name, email, password}` |
| `/api/auth/login/` | POST | anyone | `{email, password}` → `{access, refresh, user}` |
| `/api/auth/refresh/` | POST | anyone | `{refresh}` → new `access` |
| `/api/events/` | GET | anyone | list events, includes `seats_left`, `is_registered` |
| `/api/events/` | POST | admin | create event |
| `/api/events/<id>/` | PUT/PATCH/DELETE | admin | edit/delete event |
| `/api/registrations/` | GET | logged-in | own registrations (admins: all, or `?event=<id>`) |
| `/api/registrations/` | POST | logged-in | `{event: <id>}` — register for an event |
| `/api/registrations/<id>/` | DELETE | logged-in | cancel own registration |

Auth header for protected routes: `Authorization: Bearer <access_token>`.

## 4. Why some things are built the way they are

- **Login is by email**, not username — `USERNAME_FIELD = "email"` on the
  custom `User` model in `accounts/models.py`.
- **`role` lives on the User model** (`user` / `admin`) rather than using
  Django groups — simpler to check from React (`user.role === 'admin'`) and
  simpler to filter on in `IsAdminOrReadOnly`.
- **`Registration.status`** already has `confirmed` / `pending_payment` /
  `cancelled` even though you're not charging anyone yet — this is the field
  we talked about adding now so a payment step later doesn't need a schema
  migration on data people already registered against.
- **Django admin works out of the box** (`/admin/`) for both `Event` and
  `Registration` — usable as a stopgap admin panel on day one while the React
  admin dashboard gets built.
