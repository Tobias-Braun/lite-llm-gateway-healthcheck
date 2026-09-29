import type { AppConfig, ModelFamily } from "./types";

/** Relative URL so it works both behind the Vite dev proxy and when served by the backend. */
export const FAMILIES_URL = "/api/families";
export const CONFIG_URL = "/api/config";

export async function fetchFamilies(signal?: AbortSignal): Promise<ModelFamily[]> {
  const response = await fetch(FAMILIES_URL, { signal });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as ModelFamily[];
}

export async function fetchConfig(signal?: AbortSignal): Promise<AppConfig> {
  const response = await fetch(CONFIG_URL, { signal });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as AppConfig;
}
