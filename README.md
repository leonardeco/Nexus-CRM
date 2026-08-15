# NEXUS CRM

Self-serve multi-tenant CRM foundation: FastAPI API + worker, React/Vite SPA, PostgreSQL, Redis.

## Stack

- Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic
- React 18, TypeScript, Vite, Tailwind
- PostgreSQL 16, Redis 7, Docker Compose

## Local setup

1. Copy `.env.example` to `.env`.
2. From `docker/`, run `docker compose up --build`.
3. App: http://localhost:8080 — API: http://localhost:8000/api/v1/healthz

## Layout

- `backend/` — FastAPI app (`app.main:app`)
- `frontend/` — SPA
- `api/openapi.yaml` — OpenAPI 3.1 contract
- `docker/` — Compose, Dockerfiles, nginx
