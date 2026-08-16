# Pendientes — NEXUS CRM

Fuente: Documento Maestro v1.0 (levantamiento de requerimientos).  
Última revisión: 2026-08-16.

Lo que **ya está en `master`**: Foundation (alta, tenancy, auth/MFA, RBAC, ARCO, auditoría), M1 núcleo (contactos/cuentas + habeas data por contacto) y M2 núcleo (pipelines, Kanban, deals, historial de etapa, forecast, rotting).

Orden sugerido para lo que sigue: **M4 → M7 → M3**, o el que decida producto.

---

## Siguiente corte (decidir)

- [ ] **M4 Inbox WhatsApp-first** — bandeja unificada, hilo por contacto, plantillas (RF-019+ del bloque comunicaciones; paridad WhatsApp-first del roadmap MVP).
- [ ] **M7 Dashboard** — widgets de deals creados/ganados/perdidos, valor de pipeline, embudo por etapa (se apoya en M2).
- [ ] **M3 Copilot** — asistente en lenguaje natural; depende de M1+M2 (y gana con M4).

---

## M1 — Contactos y cuentas (huecos del núcleo)

| ID | Qué falta | Prioridad |
|---|---|---|
| RF-003 | Historial de interacciones (llamadas, emails, reuniones, notas) | Crítica |
| RF-004 | Campos personalizados (texto, número, fecha, lista, booleano) | Alta |
| RF-005 | Segmentación: etiquetas, industria, región, ciclo de vida | Alta |
| RF-006 | Importación CSV/Excel con mapeo y validación | Alta |
| RF-007 | Detección y fusión de duplicados | Media |
| RF-008 | Vista 360° (historial + negocios + tickets + comunicaciones) | Alta |

## M2 — Pipeline (huecos del núcleo)

| ID | Qué falta | Prioridad | Bloqueo |
|---|---|---|---|
| RF-014 | Alertas por N días **sin actividad** | Alta | Hace falta RF-003 (actividades) |
| RF-017 | Productos/servicios del catálogo en el deal | Alta | Hace falta módulo Catálogo |
| RF-018 | Propuesta comercial PDF desde el deal | Alta | Hace falta render de documentos |
| — | Arrastrar tarjetas en el Kanban | — | Hoy se mueve con control accesible |

## M3 — Copilot (todo)

Asistente conversacional, redacción de seguimientos, scoring, acciones con autonomía configurable. No hay código de este módulo.

## M4 — Comunicaciones (todo)

Inbox WhatsApp-first, email, plantillas, hilo único por contacto. No hay código de este módulo.

## M5 — Marketing (todo)

Campañas, secuencias, formularios, landings.

## M6 — Helpdesk (todo)

Tickets, SLA, categorías, escalamiento.

## M7 — Analítica (todo)

Dashboard configurable, embudo de conversión, proyección de ingresos. El forecast de M2 es un precursor, no el dashboard.

## M8 — API pública e integraciones (todo)

Tokens de API, WhatsApp Business, Google Workspace, DIAN, contabilidad.

---

## Deuda conocida (Foundation)

- `PATCH /me` está en el contrato OpenAPI; la API solo implementa `GET /me`.
- `GET /api/v1/readyz` existe en código y no está en el contrato.
- `PATCH /tenant` acepta `policyVersion` en el schema; el servicio solo aplica `companyName` y `slug`.
- El código de problema `forbidden` no está en el enum de `Problem.code` del OpenAPI.
- En GitHub existe una rama `main` con historial de **otro producto**. Decidir: borrarla o no tocarla. La rama de trabajo de NEXUS es `master`.

## Fuera de git (a propósito)

- El `.docx` de levantamiento vive en la máquina local y está en `.gitignore`.
- Datos locales de Postgres (`.pgdata/`) y secretos (`.env`) no se versionan.
