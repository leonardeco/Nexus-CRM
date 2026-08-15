export const POLICY_VERSION = "privacy-2026-08-01";

export type Role = "administrador" | "gerente" | "vendedor";

export type MfaStatus = "not_required" | "pending" | "enrolled";

export type SessionScope = "full" | "mfa_enroll_only";

export type LoginStatus =
  | "authenticated"
  | "mfa_required"
  | "mfa_enrollment_required";

export type ArcoRequestType =
  | "acceso"
  | "rectificacion"
  | "cancelacion"
  | "oposicion";

export type Problem = {
  type: string;
  title: string;
  status: number;
  detail: string;
  code: string;
};

export type SessionPrincipal = {
  userId: string;
  tenantId: string;
  role: Role;
  mfaStatus: MfaStatus;
  scope: SessionScope;
  email: string;
  fullName: string;
  tenantSlug: string;
};

export type LoginResponse = {
  status: LoginStatus;
  mfaChallengeId?: string;
  principal?: SessionPrincipal;
};

export type Tenant = {
  id: string;
  slug: string;
  companyName: string;
  plan: "starter";
  seatCap: number;
  status: "pending_verification" | "provisioning" | "active" | "suspended";
};

export type User = {
  id: string;
  email: string;
  fullName: string;
  role: Role;
  status: "active" | "deactivated" | "pending_invite";
  mfaStatus: MfaStatus;
};

export type ArcoRequest = {
  id: string;
  requestType: ArcoRequestType;
  source: "public_form" | "logged_in_self" | "manual_mail";
  status: "open" | "responded" | "closed";
  requesterName: string;
  requesterEmail: string;
  details?: string;
  responseText?: string;
};

export type AuditEvent = {
  id: string;
  occurredAt: string;
  actorEmail?: string;
  eventType: string;
  ipAddress?: string;
};

export type AuditPage = {
  items: AuditEvent[];
  nextCursor?: string;
};

export type SignupRequest = {
  companyName: string;
  slug: string;
  adminFullName: string;
  email: string;
  password: string;
  acceptPrivacyPolicy: true;
  acceptHabeasData: true;
  policyVersion: string;
};
