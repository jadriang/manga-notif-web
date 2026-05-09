# Whitelist Signup Design

**Date:** 2026-05-09

## Summary

Only pre-approved emails can sign up. Managed via a DB table, enforced on both the frontend (UX) and backend (security). Google OAuth is removed.

## Database

New table `allowed_emails`:

```sql
CREATE TABLE allowed_emails (
    email TEXT PRIMARY KEY
);
```

- `email` is stored lowercase.
- Rows are added/removed manually via the Supabase dashboard table editor.
- Owner seeds their own email immediately after migration.

## Backend

### New endpoint: `GET /api/auth/check-email`

- Public — no auth required.
- Query param: `email`
- Lowercases the email before querying.
- Returns `{"allowed": true}` or `{"allowed": false}`.
- Used by the frontend before calling Supabase signup.

### `get_current_user` hardening

When creating a new `User` row (i.e. first-ever login for that Supabase UID), check `allowed_emails`. If the email is not present, return HTTP 403. This is the non-bypassable security gate — even direct API calls cannot create an app user without being whitelisted.

### Alembic migration

New migration creates the `allowed_emails` table.

## Frontend

### Remove Google OAuth

- Remove the "Continue with Google" button and the divider from `LoginPage.tsx`.
- Remove the `handleGoogleLogin` function.

### Whitelist pre-check on signup

On signup form submit:
1. Call `GET /api/auth/check-email?email=<input>` before touching Supabase.
2. If `allowed: false` → show error `"You're not on the access list."` and stop.
3. If `allowed: true` → proceed with `supabase.auth.signUp()` as normal.

Sign-in flow is unchanged — the check only runs when `isSignUp` is true.

## Data Flow

```
User submits signup form
  → Frontend: GET /api/auth/check-email?email=...
    → Not allowed: show error, stop
    → Allowed: supabase.auth.signUp()
      → First API call hits backend
        → get_current_user: check allowed_emails (hard gate)
          → Not allowed: 403
          → Allowed: create User row, proceed
```

## Error States

| Scenario | Behaviour |
|----------|-----------|
| Email not in whitelist (signup attempt) | Frontend shows "You're not on the access list." — Supabase never called |
| Whitelisted email signs up, backend check fails (race/bug) | 403 returned, user sees API error |
| Non-whitelisted user somehow gets a Supabase token | 403 on every backend call |
| Sign-in (not signup) | No whitelist check — existing users always allowed |
