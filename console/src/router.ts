import { useEffect, useState } from "react";

export function normalizePath(pathname: string): string {
  const trimmed = pathname.replace(/\/+$/, "");
  return trimmed || "/";
}

export function navigate(path: string, replace = false): void {
  const target = normalizePath(path);
  if (normalizePath(window.location.pathname) === target) return;
  window.history[replace ? "replaceState" : "pushState"](null, "", target);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function usePathname(): string {
  const [pathname, setPathname] = useState(() => normalizePath(window.location.pathname));
  useEffect(() => {
    const update = () => setPathname(normalizePath(window.location.pathname));
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);
  return pathname;
}
