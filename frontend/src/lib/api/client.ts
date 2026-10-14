import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

const redirectOn401: Middleware = {
  onResponse({ response }) {
    if (
      response.status === 401 &&
      typeof window !== "undefined" &&
      window.location.pathname !== "/login"
    ) {
      window.location.href = "/login";
    }
    return undefined;
  },
};

export const api = createClient<paths>({ baseUrl: "/api" });
api.use(redirectOn401);

/** Extracts a human message from the backend error envelope. */
export function errorMessage(error: unknown, fallback = "Something went wrong"): string {
  const e = error as { error?: { message?: string } } | undefined;
  return e?.error?.message ?? fallback;
}

/** Unwraps an openapi-fetch result, throwing on error so TanStack Query can handle it. */
export function unwrap<T>(res: { data?: T; error?: unknown; response: Response }): T {
  if (res.error !== undefined || res.data === undefined) {
    const err = new Error(errorMessage(res.error)) as Error & { status: number };
    err.status = res.response.status;
    throw err;
  }
  return res.data;
}
