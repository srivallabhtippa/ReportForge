# ADR 0002: Argon2id passwords and short-lived JWT access tokens

**Status:** Accepted (v1, 2026-11)

## Context
Users must log in, and every later request must prove who they are without resending the password. Stolen database contents must not reveal passwords.

## Decision
- Passwords are hashed with **Argon2id** (argon2-cffi defaults), with a random salt per password.
- Login returns a **JWT** signed with HS256 using one server secret (`SECRET_KEY`). Claims: `sub` (user id), `org` (organization id), `iat`, `exp`. Lifetime: **30 minutes**.
- The algorithm is **pinned** when verifying, so tokens claiming `alg: none` are refused.
- On every request the user is **reloaded from the database** and must still exist, be active, and belong to the organization named in the token.
- Login gives one identical error for unknown email, wrong password and disabled account, and always runs one password check (dummy hash for unknown emails) so response times match.

## Alternatives considered
| Option | Why not |
|---|---|
| bcrypt | Acceptable, but Argon2id is the current recommendation and is memory-hard |
| Server-side sessions | Simple to revoke, but needs shared session storage as the backend scales. Possible later |
| RS256 / asymmetric JWT | Useful when other services verify tokens. Unnecessary with one backend |
| External identity provider (Keycloak, Auth0) | Right for production, but hides the mechanics this project exists to teach |

## Consequences
- Disabling a user takes effect on the next request, despite the token still being valid.
- Tokens **cannot be revoked** before they expire, and there is no refresh token: users log in again after 30 minutes.
- No rate limiting yet, so passwords can be guessed online. Planned for v4 hardening.
- Leaking `SECRET_KEY` lets an attacker forge tokens for anyone. It lives only in `.env` files, never in git.
