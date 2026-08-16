<p align="center">
  <img src="docs/assets/nexus-banner.svg" alt="NEXUS CRM — Foundation" width="100%">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/slices-A_Foundation_·_B_Contactos_·_C_Pipeline-2563EB?style=flat-square" alt="Slices A, B y C">
  <img src="https://img.shields.io/badge/version-0.1.0-0F172A?style=flat-square" alt="0.1.0">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/FastAPI-async-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=0F172A" alt="React 18">
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL 16">
  <img src="https://img.shields.io/badge/Redis-7-DC382D?style=flat-square&logo=redis&logoColor=white" alt="Redis 7">
</p>

<p align="center">
  <strong>Plataforma de alta para empresas, con tenancy real, MFA y derechos ARCO desde el día uno.</strong><br>
  <sub>UI en español latinoamericano · contrato OpenAPI 3.1 · código, esquema y commits en inglés</sub>
</p>

---

## Por qué existe este repo

NEXUS no arranca como un CRUD genérico. El corte **Foundation** deja listo el suelo que el resto del CRM no puede improvisar después: **una empresa = un tenant**, **un correo = un tenant en toda la plataforma**, sesiones duras, roles de verdad y **Ley 1581** (habeas data + canal ARCO).

Este repositorio contiene los **slices A (Foundation), B (Contactos y cuentas) y C (Pipeline de ventas)**. WhatsApp, copilot NEXUS AI y el dashboard comercial están fuera de este árbol a propósito.

| Listo ahora | Siguiente |
|---|---|
| Alta self-serve + primer Administrador | M4 Inbox WhatsApp-first |
| Consentimiento, verificación de correo, recovery | M3 Copilot (LangGraph) |
| MFA TOTP obligatorio Admin/Gerente | M7 Dashboard |
| Invitaciones, cupo de asientos, RBAC | M5 Marketing |
| ARCO público + bandeja Admin + auditoría inmutable | M6 Helpdesk |
| **M1 Contactos y cuentas** con habeas data por contacto | RF-014 alertas por actividad · RF-017 catálogo · RF-018 propuestas PDF |
| **M2 Pipeline Kanban**: negocios, etapas, historial, forecast, rotting | |

---

## Recorrido de producto

```mermaid
flowchart LR
  A[Registro + consentimiento] --> B[Verificar correo]
  B --> C[Provisionar schema del tenant]
  C --> D[Login]
  D --> E{Rol}
  E -->|Admin / Gerente| F[Enrolar TOTP]
  E -->|Vendedor| G[Sesión completa]
  F --> G
  G --> H[Perfil]
  H --> I[Usuarios · ARCO · Auditoría]
```

**Plan Starter:** 2 asientos. El schema PostgreSQL del tenant (`t_{32-hex}`) se crea **después** de verificar el correo, no en el signup. El signup público siempre responde `202` con cuerpo vacío: no se enumera si el correo ya existe.

---

## Arquitectura

Monolito modular. Un proceso de API, un worker, un SPA. Sin subdominios: el tenant vive en la ruta `/t/:slug/…` y en el schema de base de datos.

```mermaid
flowchart TB
  subgraph edge [Borde]
    WEB["nginx :8080<br/>SPA + proxy /api/"]
  end
  subgraph runtime [Runtime]
    API["FastAPI · uvicorn"]
    WRK["Worker · outbox + provision"]
  end
  subgraph data [Estado]
    PG[("PostgreSQL 16<br/>catalog + t_*")]
    RD[("Redis 7<br/>sesiones · rate limit · MFA")]
    SMTP["SMTP / Mailpit"]
  end
  Browser --> WEB
  WEB --> API
  API --> PG
  API --> RD
  API --> SMTP
  WRK --> PG
  WRK --> RD
  WRK --> SMTP
```

| Pieza | Rol |
|---|---|
| `catalog` | Tenants, usuarios, identidades, tokens hasheados, outbox, consentimiento, auditoría de plataforma |
| `t_*` | Datos de la empresa, aislados por `search_path` |
| Redis | Sesión opaca `nexus_session` (12 h absolutas, 30 min idle), retos MFA, límites |
| nginx | Única puerta al host. La API **no** publica `:8000` |

**Decisiones ya cerradas**

| ADR | Decisión |
|---|---|
| 0001 | Monolito modular FastAPI + React |
| 0002 | Schema-per-tenant + catálogo de plataforma |
| 0003 | Sesiones cookie `httpOnly` + `SameSite=Lax` |
| 0004 | REST `/api/v1` · OpenAPI 3.1 como contrato |
| 0005 | Provisionar schema tras verificar el correo |

---

## Superficie de seguridad

Nada de esto es “fase 2”. Va en Foundation porque un CRM de LATAM que toca PII no puede nacer abierto.

- **Contraseñas** Argon2id (fuera del event loop). **TOTP** `valid_window=0`. Códigos de respaldo de un solo uso, con lock de fila.
- **MFA** obligatorio para `administrador` y `gerente`. `vendedor` no enrola.
- **Cookies** `Secure` por defecto (`SESSION_COOKIE_SECURE=false` solo en HTTP local).
- **CSRF** de first-party: header `X-Nexus-Client: web` en mutaciones. El SPA lo envía solo.
- **Rate limit** atómico en Redis: login, signup, resend, reset, ARCO público, MFA por cuenta.
- **Tokens** de verify / invite / reset: hash en disco; el valor crudo sale por SMTP. Si SMTP falla, el outbox reintenta con el token cifrado bajo `NEXUS_DATA_KEY` (32 bytes, sin default).
- **ARCO** público en `/t/:slug/arco`, bandeja Admin, solicitud propia, ingreso manual. Auditoría append-only (REVOKE + `DO INSTEAD NOTHING`).
- **Un correo, un tenant** en toda la plataforma. Invitar un correo ya ocupado: `409 email_taken`.

> Compose local publica Postgres y Mailpit. Redis queda en la red interna. No uses la `NEXUS_DATA_KEY` de `.env.example` fuera de tu máquina.

---

## Stack

| Capa | Tecnología |
|---|---|
| API / worker | Python 3.12 · FastAPI · SQLAlchemy 2 async · Alembic · Argon2 · PyOTP |
| SPA | React 18 · TypeScript · Vite · Tailwind · TanStack Query · Zustand |
| Datos | PostgreSQL 16 · Redis 7 |
| Contrato | [`api/openapi.yaml`](api/openapi.yaml) · [notas](docs/API.md) |
| UI | Plus Jakarta Sans · primario `#2563EB` · acento `#059669` · fondo `#F8FAFC` |

Errores: RFC 9457 `application/problem+json`. JSON en camelCase. FastAPI `/docs` **no** es el contrato; el YAML sí.

---

## Arranque local

Requisitos: Docker y un `.env` propio.

```bash
cp .env.example .env
# Genera 32 bytes reales para NEXUS_DATA_KEY. No dejes el placeholder.
cd docker
docker compose up --build
```

| Qué | Dónde |
|---|---|
| App (SPA + API proxied) | http://localhost:8080 |
| Health | http://localhost:8080/api/v1/healthz |
| Mailpit | http://localhost:8025 |

Entra por **8080**. No hay API en el host `:8000`.

Sin Docker, el backend de tests usa PostgreSQL embebido (`pgserver`) + `fakeredis`:

```bash
# backend
python -m pytest tests -q

# frontend
cd frontend && npm test && npm run build
```

---

## Mapa del repo

```text
Nexus-CRM/
├── api/openapi.yaml      contrato HTTP (fuente de verdad)
├── backend/              FastAPI (app.main:app) + worker (python -m app.worker)
├── frontend/             SPA Vite
├── docker/               compose, Dockerfiles, nginx
└── docs/                 API notes + identidad visual
```

### Rutas de la SPA

| Ruta | Pantalla |
|---|---|
| `/registro` | Alta de empresa |
| `/verificar-email` | Verificar correo |
| `/ingresar` | Login |
| `/ingresar/mfa` | Reto TOTP / backup |
| `/ingresar/mfa/enrolar` | Enrolamiento TOTP |
| `/restablecer-contrasena` | Recovery |
| `/invitar/aceptar` | Aceptar invitación |
| `/t/:slug/arco` | ARCO público |
| `/app/perfil` | Perfil (todos los roles) |
| `/app/pipeline` | Tablero Kanban de negocios (todos los roles) |
| `/app/pipeline/:dealId` | Detalle del negocio: edición, movimiento e historial |
| `/app/forecast` | Forecast ponderado + proyección mensual (todos los roles) |
| `/app/pipelines` | Gestión de pipelines y etapas (Admin y Gerente) |
| `/app/configuracion` | Empresa (Admin) |
| `/app/usuarios` | Usuarios e invitaciones (Admin) |
| `/app/arco` | Bandeja ARCO (Admin) |
| `/app/auditoria` | Auditoría (Admin) |

Roles: `administrador` · `gerente` · `vendedor`. Gerente y vendedor no ven superficies de Admin, pero sí gestionan contactos, cuentas y negocios. La gestión de pipelines y etapas (`pipeline.manage`) es solo de Admin y Gerente; el Vendedor crea, edita y mueve negocios pero no altera etapas.

---

## Estado

**Slice A (Foundation)**, **Slice B (Contactos y cuentas)** y **Slice C (Pipeline de ventas)** están implementados, cubiertos por pytest y Vitest, y publicados en esta rama. C agrega pipelines con etapas ordenadas (un pipeline "Ventas" por defecto sembrado por migración), negocios (deals) con movimiento entre etapas e historial append-only con motivo, estados ganado/perdido, tablero Kanban, forecast ponderado con proyección mensual e indicador de estancamiento (rotting) —todo aislado por tenant y auditado— más su SPA en español para los tres roles.

Lo que **no** está aquí —y no debe leerse en este README como si lo estuviera—: WhatsApp, IA, facturación, SSO, y —dentro de M2— arrastrar-y-soltar, catálogo de productos (RF-017), propuestas PDF (RF-018) y alertas por actividad (RF-014).

<p align="center">
  <img src="docs/assets/nexus-mark.svg" width="48" alt="NEXUS">
  <br>
  <sub>Lanxa Technology · NEXUS CRM · Foundation + Contactos + Pipeline 0.1.0</sub>
</p>
