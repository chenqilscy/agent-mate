export interface DesktopRunLocation {
  sessionId: string;
  projectId?: string | null;
}

/**
 * Stable installed-app handoff. The desktop shell validates the scheme, host,
 * path and identifiers again before changing its local route.
 */
export function desktopCompanionRunUrl({
  sessionId,
  projectId,
}: DesktopRunLocation): string {
  const query = new URLSearchParams({ session_id: sessionId });
  if (projectId) query.set("project_id", projectId);
  return `agentmate://open/run?${query.toString()}`;
}
