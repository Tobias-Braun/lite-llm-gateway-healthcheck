import type { ModelFamily } from "./types";

/** Relative URL so it works both behind the Vite dev proxy and when served by the backend. */
export const FAMILIES_URL = "/api/families";

export async function fetchFamilies(signal?: AbortSignal): Promise<ModelFamily[]> {
  const response = await fetch(FAMILIES_URL, { signal });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as ModelFamily[];
}
