# EDC Event Registration

Frontend for the Entrepreneurship Development Club event platform (PRD + student/admin login).

## Run

```bash
npm install
npm run dev
```

## Demo accounts

- Student: `student@edc.edu` / `student123`
- Admin: `admin@edc.edu` / `admin123`

Data is stored in the browser (`localStorage`) until a Flask/Django API is added.

## Student

Home, event listings, registration (guest form + mock payment), contact.

## Admin

Dashboard, listings with CSV export, create event from templates (workshop, speaker, hackathon, pitch, mixer, blank), analytics.
