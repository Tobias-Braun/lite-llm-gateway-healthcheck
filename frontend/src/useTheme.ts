import { useState } from "react";

export type Theme = "light" | "dark";

/** Also read by the inline script in `index.html`, which applies the choice before first paint. */
export const THEME_STORAGE_KEY = "theme";

function storedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

function systemTheme(): Theme {
  // jsdom (tests) has no matchMedia.
  return typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** The effective theme (stored choice, else the system's) and a toggle that pins and remembers the other one. */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => storedTheme() ?? systemTheme());

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Storage blocked: the choice still applies for this page view.
    }
  }

  return { theme, toggle };
}
