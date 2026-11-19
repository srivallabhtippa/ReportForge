# ADR 0003: Keep the access token in localStorage (temporary, v1)

**Status:** Accepted for v1, **to be revisited in v4**

## Context
The browser must keep the login token somewhere between page loads.

## Decision
Store the token in `localStorage` (`frontend/src/api.ts`). Storage access is wrapped in try/catch, so a blocked storage behaves as "logged out".

## Alternatives considered
| Option | Upside | Downside |
|---|---|---|
| **localStorage** (chosen) | Simple; survives refresh | Readable by any script on the page, so an XSS bug exposes the token |
| In memory only | Hardest to steal | Lost on every refresh |
| httpOnly + Secure + SameSite cookie | JavaScript cannot read it | Needs backend cookie handling and CSRF protection |

## Consequences
- Acceptable while the app has no user-generated content and runs locally.
- The v4 hardening release moves to an httpOnly cookie (with CSRF protection) and adds a Content-Security-Policy, which also reduces XSS risk.
- When a token expires mid-session the user only sees an error on the next request. A global "session expired" handler is a known gap.
