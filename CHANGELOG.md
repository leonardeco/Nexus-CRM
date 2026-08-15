# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Foundation (slice A) self-serve tenant: signup with privacy and habeas-data consent, email verification and resend, worker-driven schema provision after verify.
- Cookie sessions (`nexus_session`, `nexus_preauth`), login, logout, password reset, and invite accept.
- TOTP MFA for Administrador and Gerente, including enrollment, challenge, and one-time backup codes.
- Admin invites, Starter seat cap (2), user list, deactivation, and role change with last-Admin protection.
- Roles `administrador`, `gerente`, `vendedor` with module-level RBAC.
- ARCO intake: public per-tenant form, logged-in self request, Admin manual intake, respond, and close.
- Append-only audit event list for Administrators.
- Spanish SPA (React/Vite) behind nginx, with policy pages and Admin settings / users / ARCO / audit screens.
