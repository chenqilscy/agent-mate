const SAFE_ID = /^[A-Za-z0-9._:-]{1,200}$/;

export function desktopRouteFromDeepLink(value: string): string | null {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  if (url.protocol !== "agentmate:" || url.hostname !== "open" || url.pathname !== "/run") {
    return null;
  }
  const sessionId = url.searchParams.get("session_id") || "";
  const projectId = url.searchParams.get("project_id") || "";
  if (!SAFE_ID.test(sessionId) || (projectId && !SAFE_ID.test(projectId))) return null;
  return projectId
    ? `/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(sessionId)}`
    : `/chat/${encodeURIComponent(sessionId)}`;
}

function applyDeepLinks(values: string[] | null, seen: Set<string>): void {
  for (const value of values || []) {
    if (seen.has(value)) continue;
    seen.add(value);
    const route = desktopRouteFromDeepLink(value);
    if (!route) continue;
    window.history.pushState({}, "", route);
    window.dispatchEvent(new PopStateEvent("popstate"));
    break;
  }
}

export async function startDesktopDeepLinks(): Promise<() => void> {
  if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) return () => {};
  const { getCurrent, onOpenUrl } = await import("@tauri-apps/plugin-deep-link");
  const seen = new Set<string>();
  const unlisten = await onOpenUrl((values) => applyDeepLinks(values, seen));
  applyDeepLinks(await getCurrent(), seen);
  return unlisten;
}
