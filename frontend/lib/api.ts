"use client";

import { getSupabaseBrowser } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
    public requestId?: string,
  ) {
    super(message);
  }
}

type Method = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

async function token(): Promise<string> {
  const { data: { session } } = await getSupabaseBrowser().auth.getSession();
  if (!session) throw new ApiError(401, "unauthorized", "Session expirée, veuillez vous reconnecter.");
  return session.access_token;
}

async function send(method: Method, path: string, body?: unknown | FormData): Promise<Response> {
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  try {
    return await fetch(`${API_URL}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${await token()}`,
        ...(body !== undefined && !isForm ? { "Content-Type": "application/json" } : {}),
      },
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
      cache: "no-store",
    });
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError(0, "network_error", "Serveur injoignable. Vérifiez votre connexion.");
  }
}

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const res = await send(method, path, body);
  return parse<T>(res);
}

async function parse<T>(res: Response): Promise<T> {
  const supabase = getSupabaseBrowser();
  if (res.status === 204) return undefined as T;

  const payload = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401) {
      await supabase.auth.signOut();
      window.location.href = "/login";
    }
    // Erreurs applicatives { error: {...} } ou erreurs de validation FastAPI { detail: [...] }
    if (payload?.error) {
      const e = payload.error;
      throw new ApiError(res.status, e.code, e.message, e.details, e.request_id);
    }
    if (Array.isArray(payload?.detail)) {
      const msg = payload.detail
        .map((d: { loc?: string[]; msg: string }) => `${d.loc?.slice(1).join(".") || "champ"} : ${d.msg}`)
        .join(" ; ");
      throw new ApiError(422, "validation_error", msg);
    }
    throw new ApiError(res.status, "http_error", `Erreur ${res.status}`);
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  /** Lecture publique, sans jeton (catalogue des offres publiées). */
  publicGet: async <T>(path: string): Promise<T> => {
    let res: Response;
    try {
      res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
    } catch {
      throw new ApiError(0, "network_error", "Serveur injoignable. Vérifiez votre connexion.");
    }
    return parse<T>(res);
  },
  /** Envoi de fichier (multipart/form-data). */
  upload: async <T>(path: string, form: FormData) => parse<T>(await send("POST", path, form)),
  /** Téléchargement authentifié d'un fichier généré par l'API. */
  download: async (path: string, filename: string) => {
    const res = await send("GET", path);
    if (!res.ok) await parse(res);
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: filename });
    a.click();
    URL.revokeObjectURL(url);
  },
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  del: <T = void>(path: string, body?: unknown) => request<T>("DELETE", path, body),
};

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Une erreur inattendue est survenue.";
}
