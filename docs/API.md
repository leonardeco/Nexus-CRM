# NEXUS CRM — API notes

Contract source of truth: [`api/openapi.yaml`](../api/openapi.yaml) (OpenAPI 3.1, `info.version` 1.2.0). Covers Slice A (Foundation), Slice B (Contacts & Accounts) and Slice C (Sales Pipeline & Deals).

Base path: `/api/v1`. JSON camelCase. Cookie `nexus_session` unless `security: []`. Mutating methods require header `X-Nexus-Client: web` (403 `csrf_rejected` otherwise). Errors: RFC 9457 `application/problem+json`.

This list is the contract, not a guess. Gaps versus running code are in [Drift](#drift).

## Public (no session cookie)

| Method | Path | operationId |
|---|---|---|
| GET | `/healthz` | `healthz` |
| POST | `/public/signups` | `createSignup` |
| POST | `/public/email-verifications` | `verifyEmail` |
| POST | `/public/email-verifications/resend` | `resendVerification` |
| POST | `/public/sessions` | `createSession` |
| POST | `/public/sessions/mfa` | `completeMfa` |
| POST | `/public/password-resets` | `requestPasswordReset` |
| POST | `/public/password-resets/confirm` | `confirmPasswordReset` |
| POST | `/public/invites/accept` | `acceptInvite` |
| POST | `/public/tenants/{slug}/arco-requests` | `submitPublicArco` |

Login `status` values in the contract: `authenticated`, `mfa_required`, `mfa_enrollment_required`.

## Cookie session

| Method | Path | operationId |
|---|---|---|
| DELETE | `/sessions/current` | `logout` |
| GET | `/me` | `getMe` |
| PATCH | `/me` | `patchMe` |
| POST | `/me/mfa/totp` | `startTotpEnroll` |
| POST | `/me/mfa/totp/confirm` | `confirmTotpEnroll` |
| POST | `/me/arco-requests` | `submitSelfArco` |
| GET | `/tenant` | `getTenant` |
| PATCH | `/tenant` | `patchTenant` |
| GET | `/users` | `listUsers` |
| POST | `/invites` | `createInvite` |
| POST | `/users/{id}/deactivation` | `deactivateUser` |
| PATCH | `/users/{id}/role` | `changeUserRole` |
| GET | `/arco-requests` | `listArco` |
| POST | `/arco-requests` | `intakeManualArco` |
| POST | `/arco-requests/{id}/response` | `respondArco` |
| POST | `/arco-requests/{id}/closure` | `closeArco` |
| GET | `/audit-events` | `listAudit` |

Roles in the contract: `administrador`, `gerente`, `vendedor`. ARCO types: `acceso`, `rectificacion`, `cancelacion`, `oposicion`.

## Contacts & Accounts (Slice B)

Reads require `contacts.read`; writes require `contacts.write`. All three roles hold both permissions and see every contact/account in the tenant (`ownerUserId` is for assignment, not filtering). Lists are keyset-paginated `{ items, nextCursor? }` ordered by `(createdAt, id)` DESC. Archived rows are soft-deleted (`archivedAt`) and excluded from lists and GET-by-id (404).

| Method | Path | operationId |
|---|---|---|
| GET | `/accounts` | `listAccounts` |
| POST | `/accounts` | `createAccount` |
| GET | `/accounts/{id}` | `getAccount` |
| PATCH | `/accounts/{id}` | `updateAccount` |
| POST | `/accounts/{id}/archive` | `archiveAccount` |
| GET | `/accounts/{id}/contacts` | `listAccountContacts` |
| GET | `/contacts` | `listContacts` |
| POST | `/contacts` | `createContact` |
| GET | `/contacts/{id}` | `getContact` |
| PATCH | `/contacts/{id}` | `updateContact` |
| POST | `/contacts/{id}/archive` | `archiveContact` |
| POST | `/contacts/{id}/consent` | `recordContactConsent` |
| POST | `/contacts/{id}/assignment` | `assignContact` |

Habeas data: recording consent with `status: granted` requires a `basis` (`consentimiento`, `contrato`, `interes_legitimo`, `obligacion_legal`); otherwise `422 validation_error`. Audit events: `account.created/updated/archived`, `contact.created/updated/archived`, `contact.consent.recorded`, `contact.assigned`.

## Pipeline & Deals (Slice C)

Reads (list/board/forecast/history/get) require `pipeline.read`; deal writes (create/update/move/status/archive) require `deal.write`; pipeline & stage management (create/update/archive pipeline, add/update/reorder/delete stage) require `pipeline.manage`. `administrador` and `gerente` hold `pipeline.manage`; `vendedor` reads and writes deals but cannot manage pipelines/stages. Scope must be `full`. Deal lists are keyset-paginated `{ items, nextCursor? }` ordered by `(createdAt, id)` DESC; only active (non-archived) deals appear and archived deals return 404 on GET.

Each tenant is seeded (migration `003_tenant`) with one default pipeline **"Ventas"** and five stages: Prospecto (10%), Calificado (30%), Propuesta (60%), Negociación (80%), Cierre (95%). At most one active default pipeline (partial unique index).

| Method | Path | operationId | Permission |
|---|---|---|---|
| GET | `/pipelines` | `listPipelines` | pipeline.read |
| POST | `/pipelines` | `createPipeline` | pipeline.manage |
| PATCH | `/pipelines/{id}` | `updatePipeline` | pipeline.manage |
| POST | `/pipelines/{id}/archive` | `archivePipeline` | pipeline.manage |
| POST | `/pipelines/{id}/stages` | `addStage` | pipeline.manage |
| POST | `/pipelines/{id}/stages/reorder` | `reorderStages` | pipeline.manage |
| PATCH | `/stages/{id}` | `updateStage` | pipeline.manage |
| DELETE | `/stages/{id}` | `deleteStage` | pipeline.manage |
| GET | `/pipelines/{id}/board` | `pipelineBoard` | pipeline.read |
| GET | `/pipelines/{id}/forecast` | `pipelineForecast` | pipeline.read |
| GET | `/deals` | `listDeals` | pipeline.read |
| POST | `/deals` | `createDeal` | deal.write |
| GET | `/deals/{id}` | `getDeal` | pipeline.read |
| PATCH | `/deals/{id}` | `updateDeal` | deal.write |
| POST | `/deals/{id}/stage` | `moveDealStage` | deal.write |
| POST | `/deals/{id}/status` | `setDealStatus` | deal.write |
| POST | `/deals/{id}/archive` | `archiveDeal` | deal.write |
| GET | `/deals/{id}/history` | `dealHistory` | pipeline.read |

Rules:

- **Validation (`422 validation_error`):** `pipelineId` must resolve to an active pipeline; `stageId`/`toStageId` must belong to that pipeline; `contactId`/`accountId` must resolve to active rows; `probability` 0–100; `value` ≥ 0. Archiving the default pipeline, archiving a pipeline with open deals, or deleting a stage that holds active deals or is the pipeline's last stage → `422`.
- **Money as strings.** `value`, and forecast `sum`/`weighted`, are Decimal strings quantized to 2 places to avoid float drift.
- **Forecast.** Only `status='open'`, non-archived deals count. `weighted = Σ value × probability / 100`. `months` groups by `to_char(closeDate,'YYYY-MM')`; deals without `closeDate` are excluded from `months` but included in `stages`/`totals`.
- **Rotting (RF-016).** Deal serializer adds `daysInStage` (`EXTRACT(DAY FROM now() - stageChangedAt)`) and `isRotting` = status `open` AND the stage's `rottingDays` is set AND `daysInStage > rottingDays`.
- **Stage moves (RF-013).** `createDeal` writes an initial `deal_stage_events` row (null → first/target stage); `moveDealStage` appends an event, stamps `stageChangedAt=now()`, and sets `probability` from the target stage. `setDealStatus` `open` clears `lostReason`.
- **Audit events:** `pipeline.created/updated/archived`, `stage.created/updated/reordered/deleted`, `deal.created/updated/stage_changed/status_changed/archived`. Payloads carry ids only (+ from/to stage ids for moves, + status for status changes).

## Drift

Contract vs code as of this sync. Not filled in by guessing.

### Still open

- **`PATCH /me` (`patchMe`)** is in the contract (`PatchMeRequest.fullName`). The API implements `GET /me` only. The SPA profile screen does not call PATCH. `Permission.PROFILE_WRITE` has no matching handler.
- **`GET /api/v1/readyz`** is implemented (Redis ping + `SELECT 1`) and CSRF-skipped. It is **not** in the contract. Not listed as a public operation above.
- **`PATCH /tenant` `policyVersion`:** the contract schema includes `policyVersion`. The request model accepts it; `UserService.patch_tenant` applies `companyName` and `slug` only.
- **Problem `code` `forbidden`:** RBAC returns this code. It is not in the contract `Problem.code` enum.
- **Version strings:** Python/JS packages are `0.1.0`; OpenAPI `info.version` is `1.0.0`. The live HTTP contract is `api/openapi.yaml` in this repo.

### Matched

- Remaining contract paths and methods have handlers under `/api/v1` (identity, arco, audit routers, plus `healthz` on the app).
- Audit `eventType` enum values in the contract are the types the services append.
