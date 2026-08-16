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

export type ConsentStatus = "unknown" | "granted" | "denied";

export type ConsentBasis =
  | "consentimiento"
  | "contrato"
  | "interes_legitimo"
  | "obligacion_legal";

export type Account = {
  id: string;
  name: string;
  industry?: string | null;
  region?: string | null;
  website?: string | null;
  phone?: string | null;
  notes?: string | null;
  ownerUserId?: string | null;
  createdAt: string;
  updatedAt: string;
};

export type Contact = {
  id: string;
  accountId?: string | null;
  fullName: string;
  jobTitle?: string | null;
  primaryEmail?: string | null;
  primaryPhone?: string | null;
  emails: string[];
  phones: string[];
  social: Record<string, string>;
  address?: string | null;
  notes?: string | null;
  ownerUserId?: string | null;
  consentStatus: ConsentStatus;
  consentBasis?: ConsentBasis | null;
  consentRecordedAt?: string | null;
  createdAt: string;
  updatedAt: string;
};

export type ContactPage = {
  items: Contact[];
  nextCursor?: string;
};

export type AccountPage = {
  items: Account[];
  nextCursor?: string;
};

export type Stage = {
  id: string;
  pipelineId: string;
  name: string;
  position: number;
  probability: number;
  rottingDays?: number | null;
  createdAt: string;
  updatedAt: string;
};

export type Pipeline = {
  id: string;
  name: string;
  isDefault: boolean;
  archivedAt?: string | null;
  createdAt: string;
  updatedAt: string;
  stages: Stage[];
};

export type PipelinePage = {
  items: Pipeline[];
};

export type DealStatus = "open" | "won" | "lost";

export type Deal = {
  id: string;
  pipelineId: string;
  stageId: string;
  name: string;
  value: string;
  currency: string;
  contactId?: string | null;
  accountId?: string | null;
  ownerUserId?: string | null;
  closeDate?: string | null;
  probability?: number | null;
  status: DealStatus;
  lostReason?: string | null;
  stageChangedAt: string;
  daysInStage: number;
  isRotting: boolean;
  createdAt: string;
  updatedAt: string;
};

export type DealPage = {
  items: Deal[];
  nextCursor?: string;
};

export type BoardColumn = {
  stage: Stage;
  deals: Deal[];
};

export type Board = {
  pipeline: Pipeline;
  stages: BoardColumn[];
};

export type ForecastStage = {
  stageId: string;
  name: string;
  count: number;
  sum: string;
  weighted: string;
};

export type ForecastMonth = {
  month: string;
  sum: string;
  weighted: string;
};

export type Forecast = {
  pipelineId: string;
  currency: string;
  stages: ForecastStage[];
  totals: { count: number; sum: string; weighted: string };
  months: ForecastMonth[];
};

export type DealHistoryEvent = {
  id: string;
  fromStageId?: string | null;
  fromStageName?: string | null;
  toStageId?: string | null;
  toStageName?: string | null;
  reason?: string | null;
  actorEmail?: string | null;
  occurredAt: string;
};

export type DealHistory = {
  items: DealHistoryEvent[];
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
