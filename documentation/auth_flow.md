Authentication & MFA developer notes
===================================

Overview
--------
This project contains a minimal local authentication system used for demo
and development. It supports:

- username/password registration and login
- short-lived temporary MFA tokens during login
- TOTP-based MFA (Time-based One-Time Password compatible with Authenticator apps)
- simple session tokens stored in a SQLite `users.db` file

This document outlines the runtime flow, relevant endpoints, and quick
commands to exercise the flow locally.

Auth flow (normal user, no MFA)
-------------------------------
1. Client POSTs to `/api/auth/login` with `{ "username", "password" }`.
2. Server verifies password and returns a session token (`token`) when
   the user does not have MFA enabled.
3. Client stores `auth_token` in localStorage and uses it for verified endpoints.

Auth flow (user with MFA enabled)
---------------------------------
1. Client POSTs to `/api/auth/login` with credentials.
2. Server verifies credentials and, because `mfa_enabled` is true for the
   user, issues a short-lived temporary token: `{ "mfa_required": true, "tmp_token": "..." }`.
3. Client displays a second-factor UI and asks user to provide the TOTP
   code from their authenticator app.
4. Client POSTs to `/api/auth/mfa/login` with `{ "tmp_token", "code" }`.
5. Server verifies the TOTP code using the user's stored Base32 `mfa_secret`.
   On success the temporary token is deleted and a session token is issued
   (returned as `token`).

MFA setup (enrollment)
----------------------
1. A logged-in user requests `/api/auth/mfa/setup` with a valid session `token`.
2. Server generates a new Base32 secret and returns `{ "secret", "otpauth_url" }`.
3. Client shows a QR (otpauth_url) for the user to scan in their authenticator.
4. The user scans the QR and the client asks the user to verify by entering
   a TOTP code to `/api/auth/mfa/verify` (with the session `token` and `code`).
5. On success the server sets `mfa_enabled = 1` for the user.

Key endpoints
-------------
- `POST /api/auth/register` -- register new user (body: `username`, `password`)
- `POST /api/auth/login` -- authenticate credentials; may return `mfa_required` and `tmp_token`
- `POST /api/auth/mfa/login` -- exchange `tmp_token` + `code` for session `token`
- `POST /api/auth/mfa/setup` -- generate secret & otpauth URL (requires session token)
- `POST /api/auth/mfa/verify` -- verify enrollment TOTP code and enable MFA
- `POST /api/auth/verify` -- verify a session `token` and get username

Developer testing (local)
-------------------------
Run the backend with Uvicorn:

```bash
python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Use `curl` to test a full MFA login flow for a user who is already enrolled:

```bash
# login -> get tmp_token
curl -s -X POST http://127.0.0.1:8000/api/auth/login -H 'Content-Type: application/json' -d '{"username":"alice","password":"secret"}' | jq

# exchange tmp_token + code -> get session token
curl -s -X POST http://127.0.0.1:8000/api/auth/mfa/login -H 'Content-Type: application/json' -d '{"tmp_token":"<tmp>","code":"123456"}' | jq
```

Notes & caveats
----------------
- This is a demo-level implementation: tokens are opaque random strings
  stored in SQLite.
- TOTP uses HMAC-SHA1 to remain compatible with common authenticators.
- The code intentionally separates `mfa_enabled` (user chooses to enable)
  from secret generation. When a new secret is set it is not active until
  the user verifies the OTP.