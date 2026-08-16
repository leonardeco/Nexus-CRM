# NEXUS CRM — API notes

Contract source of truth: [`api/openapi.yaml`](../api/openapi.yaml) (OpenAPI 3.1, `info.version` 1.1.0). Covers Slice A (Foundation) and Slice B (Contacts & Accounts).

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
