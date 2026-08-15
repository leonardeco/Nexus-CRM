import type { Problem } from "./types";

const MUTATING = new Set(["POST", "PATCH", "PUT", "DELETE"]);

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly title: string;
  readonly detail: string;

  constructor(problem: Partial<Problem>, status: number) {
    const detail = problem.detail ?? "No se pudo completar la solicitud.";
    super(detail);
    this.name = "ApiError";
    this.status = problem.status ?? status;
    this.code = problem.code ?? "validation_error";
    this.title = problem.title ?? "Error";
    this.detail = detail;
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  if (MUTATING.has(method)) {
    headers.set("X-Nexus-Client", "web");
  }
  if (init.body !== undefined && init.body !== null && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`/api/v1${path}`, {
    ...init,
    method,
    headers,
    credentials: "include",
  });

  const text = await response.text();
  if (!response.ok) {
    let parsed: unknown;
    try {
      parsed = text.length === 0 ? {} : JSON.parse(text);
    } catch {
      throw new Error("Respuesta inválida del servidor.");
    }
    throw new ApiError(isRecord(parsed) ? parsed : {}, response.status);
  }
  if (response.status === 202 || response.status === 204 || text.length === 0) {
    return undefined as T;
  }
  return parseBody(text) as T;
}

function parseBody(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new Error("Respuesta inválida del servidor.");
  }
}

function isRecord(value: unknown): value is Partial<Problem> {
  return typeof value === "object" && value !== null;
}

export function problemMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "No se pudo completar la solicitud.";
}
