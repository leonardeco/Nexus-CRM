# NEXUS CRM

Self-serve multi-tenant CRM **Foundation** (slice A): FastAPI API + worker, React/Vite SPA, PostgreSQL, Redis.

Package version: `0.1.0` (`backend/pyproject.toml`, `frontend/package.json`). The OpenAPI `info.version` field is `1.0.0` (see [docs/API.md](docs/API.md)).

## What this slice includes

- **Tenancy:** platform `catalog` schema plus one PostgreSQL schema per tenant (`t_{32-hex}`), created after email verification (not at signup). Starter plan, seat cap 2.
- **Auth:** signup with privacy + habeas-data consent, email verification / resend, login, logout, password reset, invite accept. Opaque `httpOnly` `SameSite=Lax` cookies (`nexus_session`, `nexus_preauth` for MFA enroll).
- **MFA:** TOTP required for `administrador` and `gerente`; backup codes; `vendedor` is not required.
- **RBAC:** roles `administrador`, `gerente`, `vendedor`. Admin-only UI for settings, users, ARCO inbox, and audit. Gerente and vendedor use Perfil only.
- **ARCO (Ley 1581):** public form at `/t/:slug/arco`, logged-in self request, Admin manual intake, respond, and close.
- **Audit:** append-only event list for Administrators.

Contacts, pipeline, WhatsApp, AI, billing, and SSO are not in this slice.

UI copy is Latin-American Spanish. Code, schema, logs, and commits are English.

## Stack

- Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic
- React 18, TypeScript, Vite, Tailwind, TanStack Query, Zustand
- PostgreSQL 16, Redis 7, Mailpit (local mail), Docker Compose
- Ingress: nginx serves the SPA and proxies `/api/` to the API (first-party cookies)

## Local setup

1. Copy `.env.example` to `.env`.
2. From `docker/`, run `docker compose up --build`.
3. App (SPA + proxied API): http://localhost:8080
4. Health: http://localhost:8080/api/v1/healthz
5. Mailpit UI: http://localhost:8025

The API container publishes no host port; use nginx on **8080**, not `:8000`.

Mutating requests require header `X-Nexus-Client: web` (the SPA sends it). CSRF middleware skips `/api/v1/healthz` and `/api/v1/readyz`.

## Layout

- `backend/` — FastAPI app (`app.main:app`) and worker (`python -m app.worker`)
- `frontend/` — SPA
- `api/openapi.yaml` — OpenAPI 3.1 contract (source of truth for the HTTP surface)
- `docs/API.md` — operation list and contract-vs-code notes
- `docker/` — Compose, Dockerfiles, nginx

## SPA routes

| Path | Screen |
|---|---|
| `/registro` | Signup |
| `/verificar-email` | Email verification |
| `/ingresar` | Login |
| `/ingresar/mfa` | MFA challenge |
| `/ingresar/mfa/enrolar` | TOTP enrollment |
| `/restablecer-contrasena` | Password reset |
| `/invitar/aceptar` | Accept invite |
| `/t/:slug/arco` | Public ARCO form |
| `/politica-privacidad` | Privacy policy text |
| `/habeas-data` | Habeas data text |
| `/app/perfil` | Profile (all roles) |
| `/app/configuracion` | Tenant settings (Admin) |
| `/app/usuarios` | Users and invites (Admin) |
| `/app/arco` | ARCO inbox (Admin) |
| `/app/auditoria` | Audit log (Admin) |

## API

REST at `/api/v1`. JSON camelCase. Errors are RFC 9457 `application/problem+json`. Cookie auth plus explicit public operations.

See [docs/API.md](docs/API.md) and [`api/openapi.yaml`](api/openapi.yaml). Do not treat FastAPI’s auto `/docs` as the contract; that schema is generated from code and can differ.

## Tests

- Backend: from `backend/`, `pytest` (API cases mapped to AC-1…AC-8, plus isolation and audit immutability).
- Frontend: from `frontend/`, `npm test` (Vitest).

## Architecture decisions

ADRs live outside this git tree (Hydraia artifacts `adr/`). Accepted:

| ID | Decision |
|---|---|
| 0001 | Modular monolith: FastAPI + React SPA |
| 0002 | PostgreSQL schema-per-tenant plus catalog |
| 0003 | Opaque httpOnly cookie sessions in Redis |
| 0004 | REST + OpenAPI 3.1 at `/api/v1` |
| 0005 | Tenant schema after email verification; API + worker |
