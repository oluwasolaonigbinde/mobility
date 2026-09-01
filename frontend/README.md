# Mobility Frontend — Next.js BFF

Next.js 16 (App Router) frontend for the Mobility AdTech platform: advertiser
portal (`/advertiser`), admin console (`/admin`), and the installable Cardvert
Driver PWA (`/driver`). See `../docs/architecture.md` §8 for the full frontend
architecture and invariants.

## BFF architecture

The browser never calls FastAPI directly. All backend access happens on the
Next.js server (Server Components and Server Actions) through a typed
`openapi-fetch` client (`src/lib/api/client.ts`) that sends
`Authorization: Bearer <JWT>` over the internal network.

- The backend JWT lives in an httpOnly `mobility_session` cookie
  (`src/lib/auth/session.ts`, options in `src/lib/auth/cookie-options.ts`).
  Client JavaScript can never read it.
- `src/proxy.ts` is the Next.js middleware (Next 16 renamed `middleware.ts` to
  `proxy.ts`): it fast-path-redirects cookieless visits to protected routes and
  rotates near-expiry session cookies on GET navigation.
- Server layouts call `requireRole(role)` (`src/lib/auth/current-user.ts`),
  which authorizes against `GET /api/v1/me`. Frontend checks are UX only; every
  proxied call is re-authorized by FastAPI.
- `server-only` guards `env.ts`, `client.ts`, `session.ts`, and
  `current-user.ts`. Client components receive data via props or call Server
  Actions; they never import the API client.

## Local setup

Prerequisites: Node 22+, plus the backend stack from the repo root
(`docker compose up -d db redis`, migrations, seed — see the root README).

```bash
npm install
printf 'API_BASE_URL=http://localhost:8000\n' > .env.local
npm run dev
```

The dev server runs on port 3000 by default and expects FastAPI on
`API_BASE_URL`.

## Environment variables

Server-only (zod-validated in `src/lib/env.ts`; never `NEXT_PUBLIC_`):

| Variable | Purpose |
|---|---|
| `API_BASE_URL` | FastAPI base URL for the server-side client |
| `SESSION_COOKIE_NAME` | Session cookie name (default `mobility_session`) |
| `LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER` | Relay the edge-created `X-Client-IP` header on login calls (default `false`; see `../docs/runbook.md` trusted-edge preconditions) |
| `SENTRY_DSN` | Server-runtime Sentry DSN (inert when empty) |

Build-time (inlined by `next build`):

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_SENTRY_DSN` | Browser Sentry DSN — changing it requires a rebuild, not a restart |
| `NEXT_PUBLIC_MAP_STYLE_URL` | MapLibre style URL for map surfaces |

## API types — generated, never edited

`src/lib/api/schema.d.ts` is generated from the repo-root `openapi.json`:

```bash
npm run api:types
```

The canonical contract serialization comes from the backend:
`python scripts/update_openapi_snapshot.py` (repo root) writes `openapi.json`
and `docs/api/openapi.snapshot.json` as identical sorted, pretty-printed JSON;
`npm run api:types` then regenerates the types. CI fails on any drift between
the committed `openapi.json` and `schema.d.ts`. Never hand-edit `schema.d.ts`.

## Authentication and session behavior

- Login (`/login`) exchanges credentials for a JWT via the BFF; 401/403 render
  a generic failure and 429 renders the backend's retry delay.
- Sessions slide: the middleware refreshes a near-expiry cookie on GET
  navigation via `POST /api/v1/auth/refresh`, up to a 12-hour absolute
  lifetime from login (backend-enforced). The driver tracker also pings
  `/driver/keepalive` every 10 minutes while tracking (fail-open).
- Admin-created accounts carry `must_change_password` and are forced to
  `/change-password` (advertiser/admin) or `/driver/change-password` (driver,
  inside the PWA scope) before using the app.
- A password change revokes every other session (`session_version` claim);
  stale cookies land back on the login form without redirect loops.

## Testing

```bash
npm run lint
npm run typecheck
npm run test        # vitest unit tests
npm run test:e2e    # Playwright, real backend required
```

Playwright runs two projects (desktop `chromium`, `mobile-chrome` Pixel 7)
against a real seeded stack: start the backend, run migrations and the demo
seed, then either let Playwright spawn `npm run dev` or point
`PLAYWRIGHT_BASE_URL` at a running frontend. Export the relaxed local rate-limit
thresholds first — see "Local Playwright reset and overrides" in
`../docs/runbook.md`.

## Production build

```bash
npm run build && npm run start
```

`frontend/Dockerfile` produces a standalone non-root image; compose builds it
under the `full` profile (host port 3100). `NEXT_PUBLIC_SENTRY_DSN` is a Docker
build arg — set it during `docker compose build frontend`, not at container
start. Server-side `SENTRY_DSN` is runtime config; both are inert when empty.
