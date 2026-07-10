# fablev1-work.md — Vantage Frontend Build Log

Working log for the production frontend of the Mobility AdTech platform
("Vantage"). Maintained by Claude (Fable) as the build progresses so OJ can
see what exists, why it's built that way, and what's next.

- **Repo:** `github.com/oluwasolaonigbinde/mobility`
- **Backend:** slices 1–13 complete (`slice-13-mvp-hardening` = frozen 78-endpoint MVP contract)
- **Frontend:** `frontend/` — built branch-per-phase (`frontend-00-…`, `frontend-01-…`, …)
- **Design source:** the Vantage pitch prototype (https://oluwasolaonigbinde.github.io/vantage/) — the client bought this look; the app ports it faithfully.

---

## How to run everything locally

```bash
# 1. Backend (repo root) — API on :8000
docker compose up -d                       # api + PostGIS + Redis
docker compose exec api alembic upgrade head
docker compose exec api python -m app.seeds.demo   # needs ALLOW_DEMO_SEED=true in .env

# 2. Frontend — app on :3000
cd frontend && npm install && npm run dev
```

Demo logins (local only):

| Role       | Email                              | Password               |
|------------|------------------------------------|------------------------|
| Advertiser | advertiser@demo.mobility.local     | DemoAdvertiser12345!   |
| Admin      | admin@demo.mobility.local          | DemoAdmin12345!        |
| Driver     | driver@demo.mobility.local         | DemoDriver12345!       |

Useful scripts (run in `frontend/`):

| Command             | What it does                                        |
|---------------------|-----------------------------------------------------|
| `npm run dev`       | Dev server                                          |
| `npm run test`      | Vitest unit tests                                   |
| `npm run test:e2e`  | Playwright e2e (backend must be up + seeded)        |
| `npm run typecheck` | Strict `tsc --noEmit`                               |
| `npm run lint`      | ESLint                                              |
| `npm run api:sync`  | Re-pull `openapi.json` from :8000 + regenerate types |

> **Local quirk:** host port 5433 is taken by the microfinance project's
> Postgres, so mobility's DB maps to **5434** via a gitignored
> `docker-compose.override.yml`. In-container networking is unaffected.

---

## Architecture decisions (the "why")

These were made for go-live, not for demos:

1. **BFF pattern — the browser never talks to FastAPI.**
   All API calls happen server-side (Server Components / Server Actions).
   The JWT lives in an **httpOnly, SameSite=Lax cookie** — browser JS can
   never read it (XSS-safe). No localStorage tokens, ever.
   - `src/lib/api/client.ts` — server-only typed client
   - `src/lib/auth/session.ts` — cookie read/write
   - `src/proxy.ts` — fast-path redirects (signed-out → /login)
   - `requireRole()` in server layouts — role guards backed by `/api/v1/me`;
     the backend remains the authority on every call.

2. **Zero hand-written API contracts.**
   `src/lib/api/schema.d.ts` (~6.4k lines) is **generated** from the
   backend's `openapi.json` via `openapi-typescript`, consumed through
   `openapi-fetch`. If the backend contract drifts, `npm run api:sync`
   + `tsc` breaks the build instead of production. Every non-OK response
   is normalized to one `ApiError` shape from the backend's error envelope.

3. **Validation is duplicated on purpose.**
   zod schemas in `src/lib/**/schema.ts` run in the browser (instant
   feedback) AND in the server action (authoritative gate). The server
   never trusts the client.

4. **Design system = the prototype, tokenized.**
   Vantage palette/typography as Tailwind v4 `@theme` CSS variables.
   **Clash Display + Satoshi self-hosted** (Fontshare woff2 vendored in
   `src/fonts/`, ITF Free Font License — see `src/fonts/LICENSE-NOTE.md`),
   IBM Plex Mono via `next/font/google`. Zero external font requests.
   Dark-only by design (ops product). A11y: visible focus rings, skip
   links, aria-wired forms, `role="alert"` errors.

5. **Money and decimals stay strings.**
   The API serializes decimals as strings for precision; the frontend
   parses them only at the display boundary (`src/lib/format.ts`) and
   never does arithmetic on them.

6. **Stack:** Next.js 16 (App Router) · React 19 · TypeScript strict
   (`noUncheckedIndexedAccess` etc.) · Tailwind v4 · TanStack Query
   (installed; for polling surfaces later) · react-hook-form + zod ·
   Vitest + Testing Library · Playwright (desktop + mobile projects).

---

## Phase log

### ✅ F0 — Foundation (`frontend-00-foundation`)

- Next.js scaffold, strict TS, ESLint/Prettier, Vitest, Playwright config
- Vantage design tokens + fonts (see decision 4)
- Generated API layer + error envelope normalization (decision 2)
- Auth BFF: login server action → httpOnly cookie → role redirect;
  sign-out; `proxy.ts` guards; per-request-cached `getCurrentUser()`
- Role shells (advertiser / driver / admin) with sidebar/topbar/mobile nav
- First real-data pages: advertiser dashboard summary (6 KPI tiles),
  driver earnings, admin ops counts
- **Verified in browser:** login flows for all three roles, cross-role
  guard bounce, live seeded data rendering. 11 unit tests.

### ✅ F1 — Advertiser campaigns (`frontend-01-campaigns`)

- **List** `/advertiser/campaigns`: status filter tabs + offset pagination
  as URL searchParams (shareable, back-button-safe), empty states
- **Detail** `/advertiser/campaigns/[id]`: 6-KPI performance row
  (impressions, confidence, distance-in-target-zones, quality, spend vs
  budget, fraud flags), details panel, creatives list, 404 handling
- **Status lifecycle**: product-level transition map in
  `src/lib/campaigns/status.ts` (terminal states stay terminal — the API
  allows any transition; the UI is deliberately stricter), confirm on
  destructive moves, server-action PATCH + `revalidatePath`
- **Create wizard** `/advertiser/campaigns/new`: Basics → Creatives →
  Review with per-step validation gates; RHF + zod (shared schemas,
  decision 3); honest partial-failure reporting (campaign created but a
  creative failed → says exactly that, links to the campaign)
- **Tests:** 19 unit + 5-scenario Playwright e2e against the real seeded
  stack (login, guard redirect, bad-credentials, full
  create→launch→pause lifecycle, wizard validation) — green on desktop
  **and** mobile viewports.
- Notable debugging: two e2e failures were harness races, not app bugs —
  Next's route announcer shares `role="alert"` (filter the locator), and
  Playwright's click-retry can hang when the submit button detaches on
  redirect (bound the click timeout; assert on URL).

### ✅ F2 — Campaign zones map editor (`frontend-02-zones`)

Draw target / bonus / exclusion polygons on a real map, wired to the
GeoJSON zones endpoints.

- **Map stack:** MapLibre GL (no vendor lock-in, no billing dependency) +
  Terra Draw for polygon drawing. Basemap style is configurable via
  `NEXT_PUBLIC_MAP_STYLE_URL`; defaults to Carto dark-matter (fits the
  Vantage dark theme, attribution included).
  > ⚠️ **Go-live decision needed:** free keyless dark basemaps sit in a
  > licensing gray zone for commercial use. Before launch, pick one:
  > MapTiler (free tier w/ key), Mapbox, or self-hosted OpenFreeMap tiles.
  > It's a one-line env change.
- **Editor** `/advertiser/campaigns/[id]/zones`: zones rendered as colored
  fills matching the prototype (amber target / cyan bonus / coral
  exclusion), draw-polygon flow → name/type dialog → `POST zones`,
  select-zone list panel with zoom-to, edit (name/type), delete with
  confirm — all server actions with revalidation.
- **Geometry safety:** `src/lib/zones/geometry.ts` mirrors the backend's
  GeoJSON rules (closed rings, ≥4 positions, finite lon/lat bounds) so
  invalid shapes are caught before the request; the backend remains the
  authority (5,000 km² area cap enforced server-side).
- **Tests:** 7 unit tests for geometry validation + bounds; e2e smoke
  proving the seeded campaign's 3 zones render on a live map, reached via
  the detail-page link. Full CRUD (draw→create, rename, retype, delete)
  verified manually in the browser against the running backend.
- Notable debugging: Terra Draw must initialize **after** MapLibre's
  `load` event ("Style is not done loading" otherwise), and it listens
  for **pointer** events — synthetic `MouseEvent`s don't register, which
  is also why polygon drawing is covered manually + by unit tests rather
  than flaky synthetic-pointer e2e.

---

### ✅ F3 — Analytics & exposure heatmap (`frontend-03-analytics`)

The pitch's "wow" screens with real numbers.

- **Attribution report** `/advertiser/campaigns/[id]/report`: headline KPIs
  (impressions + confidence, trips analyzed, spend, open fraud flags),
  **daily impressions area chart** (amber) and **daily spend bars** (green),
  and a full daily-breakdown table (the charts' accessible source of truth).
- **Charts are dependency-free SVG** (`src/components/charts/timeseries.tsx`)
  built by the dataviz method: single series → no legend, thin marks,
  recessive mono grid, crosshair + tooltip hover, selective direct label on
  the last point, text in ink tokens. Palette validated with the dataviz
  validator against the panel surface (chroma + ≥3:1 contrast pass; the
  categorical lightness band doesn't apply to lone series).
- **Exposure heatmap** `/advertiser/campaigns/[id]/map`: backend heatmap
  cells on MapLibre with a **single-hue amber sequential ramp** (monotonic
  lightness; low cells recede via alpha, hot cells lift toward light),
  honest min→max legend per view, metric picker (impressions / pings /
  trips / distance), dashed zones overlay toggle, per-cell hover tooltip,
  "Scan this view" for viewport-driven exploration.
- Campaign detail now links Report · Exposure map · Zones.
- **Tests:** e2e for both pages against seeded data (charts render, table
  values match backend, heatmap loads 12 cells at 500m grid, metric
  switch rescans) — 8 e2e green on desktop + mobile.
- Notable debugging: (1) server pages can't pass **functions** to client
  chart components (RSC boundary) — formatters became a serializable
  `currency` prop; (2) the initial heatmap scan raced the camera fit in
  headless and scanned the wrong city — first scan now derives its bbox
  from the campaign's zones deterministically, viewport scans stay manual.

### ✅ F4 — Vantage Driver PWA (`frontend-04-driver-app`)

Per OJ's call: the driver side is **its own installable app, not a portal**.
Same codebase (shared design system, typed API layer, one deploy), but a
separately-scoped PWA:

- **Installability:** scoped manifest at `/driver/manifest.webmanifest`
  ("Vantage Driver", `scope: /driver`, standalone, portrait, own amber-V
  icons generated dependency-free), apple-touch/status-bar meta, theme
  color. **Lesson:** browsers fetch manifests *without cookies* — the
  manifest must be excluded from auth redirects or installability silently
  breaks (fixed in `src/proxy.ts`).
- **Service worker** (`public/driver-sw.js`): deliberately minimal and
  auth-safe — immutable `_next/static` assets cache-first, navigations
  network-only with an offline fallback; API responses are NEVER cached
  (they're personal and authenticated).
- **App chrome:** slim header + bottom tab bar (Home / Jobs / Track /
  Earnings / Profile), safe-area insets, one-primary-button-per-screen
  design for use in traffic.
- **Trip tracking** (`/driver/track`): foreground geolocation →
  `watchPosition` → local buffer → **idempotent batches** (UUID key,
  flush every 15s or 20 pings, failed batches re-queued). Start/end trip
  with confirm; buffer drained before end. **Honest limitation
  (documented for the client):** a PWA tracks only while on-screen;
  background GPS is the future native app's job — same backend contract.
- **Jobs:** assignment lifecycle (offered → Accept, accepted → Activate,
  active → Deactivate) as single-action cards.
- **Earnings:** pending/available/lifetime + ledger, every naira traced
  to a trip. **Profile:** self-service licence/city/country + vehicles.
- **Verified live end-to-end:** simulated a drive through Wuse II with
  stubbed geolocation — the app streamed **42 pings** in idempotent
  batches, ended the trip cleanly, and the backend analyzed it into **13
  new heatmap cells in Abuja** visible on the advertiser's exposure map.
  That's the full advertiser↔driver loop working.
- **Tests:** 6 driver e2e (chrome + manifest publicness + every tab with
  real data); full suite now 28 e2e green on desktop + mobile viewports.
  Also fixed a brittleness of mine: heatmap e2e asserted an exact cell
  count against a *living* dataset — now asserts shape, not snapshot.

### ✅ F5 — Admin console (`frontend-05-admin`)

The ops brain — seven sections in the desktop shell:

- **Users** (`/admin/users`): list with role filter, suspend/reactivate, and
  **the onboarding flow**: one create-user form that provisions the account
  and (for advertisers) the organization with owner membership in one step.
  Verified live: created "Amina Yusuf" + "Wuse Media Group" through the UI,
  then confirmed she can sign in and lands in her own org.
- **Drivers**: onboarding-state machine per profile (approve / reject /
  suspend / reinstate / re-review), create profile for a driver-role user.
- **Vehicles**: fleet list with status transitions, register-vehicle form
  attached to its driver.
- **Assignments**: offer a campaign to a driver+vehicle pairing (the vehicle
  select narrows to the chosen driver's vehicles), cancel active offers.
- **Fraud console**: severity/status-filtered flag list. **Read-only by
  contract** — the MVP backend exposes no acknowledge/dismiss endpoint;
  flagged as a backend addition for the client.
- **Payouts**: calculations table (gross → quality× → fraud× → final →
  ledger status) plus **the process-trip pipeline**: paste a trip ID →
  recompute analytics → estimate impressions → calculate payout, with a
  step-by-step receipt. A payout-rules editor UI is queued (rules work via
  API; defaults apply).
- **The loop, closed and verified live:** processed the F4 trip through the
  UI — analytics validated 77/77 pings but flagged the simulated drive's
  ~63 m/s speed (over the 55 m/s impossible-speed threshold), zeroed the
  billable distance, and the campaign's min-payout rule still floored the
  payout at ₦1,500 → pending ledger. Driver's earnings: ₦13,389 → ₦14,889.
  The anti-gaming engine and payout rules both did their jobs on real data.
- **Tests:** 6 admin e2e; full suite now **40 e2e** green on desktop +
  mobile viewports. The generated types caught 3 more contract truths
  during the build (no `full_name` on assignment driver summaries, no
  `created_at` on the users list, optional `fraud_flags`).
- Local quirk: port 3000 is now held by the microfinance project's dev
  server, so `vantage-frontend` uses `autoPort` (Playwright reuses the
  live server via `PLAYWRIGHT_BASE_URL`).

## Deviations from the pitch prototype (agreed constraints)

The backend contract is the truth; these prototype effects are simulated
or deferred:

- **No realtime** — no WebSockets in the MVP. "Live" surfaces use honest
  request-time data now; polling via TanStack Query where it earns its
  keep later.
- **Creatives are metadata + URL** — no file-upload pipeline in the MVP;
  the wizard takes an asset URL.
- **No self-registration** — users are admin-created (matches the
  backend's security model). Onboarding is operator-led: admin creates
  the user + org and hands over credentials; names are set at creation,
  not at a public sign-up screen. Self-serve signup would be a deliberate
  backend addition (registration + email verification), flagged for the
  client if ever wanted.

## Roadmap

- [x] F0 Foundation
- [x] F1 Advertiser campaigns
- [x] F2 Zones map editor
- [x] F3 Advertiser analytics & heatmaps (report charts, daily metrics,
      exposure heatmap)
- [x] F4 Vantage Driver PWA (installable app: chrome, jobs, live trip
      tracking with idempotent ping batches, earnings, profile)
- [x] F5 Admin console (users+orgs onboarding, drivers/vehicles,
      assignments, fraud console, payout pipeline)
- [ ] F6 Hardening (loading/error states audit, a11y pass, contract-drift
      CI, deploy story)
