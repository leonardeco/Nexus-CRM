# Bitácora — NEXUS CRM

Registro de trabajo sobre este repositorio. Autor de los commits: Jose Leonardo Guzman.  
Rama publicada: `master` → `https://github.com/leonardeco/Nexus-CRM`.

---

## 2026-08-15 — Corte A · Foundation

**Objetivo.** Dejar el suelo que el resto del CRM no puede improvisar: un tenant por empresa, un correo = un tenant en la plataforma, sesiones, roles y Ley 1581.

**Hecho.**

- Monolito modular: FastAPI + React/Vite, PostgreSQL 16 (schema `catalog` + un schema por tenant), Redis, Docker Compose.
- Alta self-serve con consentimiento de privacidad y habeas data, verificación de correo, provisionamiento del schema del tenant **después** de verificar.
- Login email/contraseña, cookie `nexus_session` (httpOnly, SameSite=Lax), CSRF por header `X-Nexus-Client: web`.
- MFA TOTP obligatorio para Administrador y Gerente; códigos de respaldo de un solo uso; rate limit de MFA a nivel de cuenta.
- Invitaciones, cupo Starter (2 asientos), cambio de rol, desactivación, protección del último admin.
- Roles `administrador`, `gerente`, `vendedor` con RBAC a nivel de módulo (sin visibilidad por registro).
- ARCO: formulario público por slug, solicitud del usuario logueado, bandeja admin (responder/cerrar).
- Auditoría append-only en el schema del tenant.
- Outbox de correo con token cifrado en reposo y reintento si falla SMTP.
- SPA en español (login, registro, MFA, perfil, configuración, usuarios, ARCO, auditoría).
- Contrato OpenAPI 3.1 en `api/openapi.yaml`. README de producto.

**Cierre.** Tests de aceptación AC-1 a AC-8 en pytest; Vitest del SPA; hallazgos de revisión de seguridad/correctitud cerrados (IP detrás de proxy de confianza, rate limit MFA, caché de sesión al login/logout, Redis no publicado al host). Publicado en `master`.

---

## 2026-08-15 — Corte B · M1 Contactos y cuentas (núcleo)

**Decisiones.** Visibilidad de todo el tenant (el owner es asignación, no filtro). Los tres roles leen y escriben. Borrado suave (`archived_at`). Habeas data por contacto.

**Hecho.**

- Migración tenant `002_tenant`: tablas `accounts` y `contacts` (emails/phones JSONB + primarios indexados, consentimiento, CHECKs).
- Permisos `contacts.read` / `contacts.write` para los tres roles.
- API: listado con búsqueda y paginación keyset, alta/edición/archivo de cuentas y contactos, consentimiento, asignación de responsable, contactos de una cuenta.
- Eventos de auditoría: `account.*`, `contact.*`, `contact.consent.recorded`, `contact.assigned`.
- SPA: `/app/contactos`, `/app/contactos/:id`, `/app/cuentas`, `/app/cuentas/:id` y enlaces en la barra para todos los roles.
- OpenAPI 1.1.0 y notas en `docs/API.md`.

**Cierre.** 92 tests backend (76 de A + 16 de B), 3 Vitest, build OK. RF-003 a RF-008 quedaron fuera a propósito (ver `pendientes.md`). Publicado en `master`.

---

## 2026-08-16 — Corte C · M2 Pipeline de ventas (núcleo)

**Decisiones.** Varios pipelines desde el día uno, con uno por defecto sembrado (“Ventas”, 5 etapas). Admin y gerente gestionan etapas/pipelines; los tres roles crean y mueven deals. Ganado/perdido es `status`, no una etapa. Forecast ponderado (RF-015). Rotting por tiempo en etapa (RF-016); las alertas por actividad (RF-014) esperan el módulo de actividades.

**Hecho.**

- Migración tenant `003_tenant`: `pipelines`, `stages`, `deals`, `deal_stage_events` + semilla del pipeline por defecto.
- Permisos `pipeline.read`, `deal.write` (tres roles) y `pipeline.manage` (admin + gerente).
- API: CRUD de pipelines/etapas (reordenar, borrar con guardas), tablero, forecast, deals (alta, edición, mover con motivo e historial, ganado/perdido, archivo).
- Dinero como string decimal; `daysInStage` e `isRotting` en la serialización.
- SPA: `/app/pipeline` (Kanban), `/app/pipeline/:dealId`, `/app/forecast`; `/app/pipelines` solo admin/gerente.
- OpenAPI 1.2.0.

**Cierre.** 112 tests backend, 4 Vitest, build OK. RF-014, RF-017 y RF-018 fuera (bloqueados por módulos que no existen). Publicado en `master`.

---

## 2026-08-16 — Higiene del repositorio

**Hecho.**

- Mensajes de commit sin trailers de herramientas; autor = identidad local de git.
- Hook `commit-msg` en `.githooks/` (`git config core.hooksPath .githooks` en este clone).
- `.gitignore`: se ignora el IDE local (salvo `.cursor/rules/`), `*.docx` y locks de Word, `.pgdata/`.
- Este archivo y `pendientes.md` para retomar el hilo en la siguiente sesión.

**Commits de higiene (esta máquina).** `e0d0b31`, `ff13cac` y el commit que añade estos documentos.

---

## Cómo está el árbol hoy

| Área | Estado |
|---|---|
| Tenancy + auth + MFA + RBAC + ARCO + auditoría | En `master` |
| Contactos / cuentas + consentimiento | En `master` |
| Pipeline / deals / forecast / rotting | En `master` |
| Actividades, inbox, copilot, dashboard, marketing, tickets, API pública | No iniciado |
| Tests | pytest + Vitest en verde al cierre de C |
| Contrato | `api/openapi.yaml` 1.2.0 |

Siguiente sesión: abrir `pendientes.md` y elegir el corte (M4, M7 o M3) antes de tocar código.
