import type { LocalAgentDevice } from "./types";

const readinessLabels = {
  ready: { label: "就绪", color: "success" },
  busy: { label: "容量已满", color: "processing" },
  offline: { label: "离线", color: "default" },
  incompatible: { label: "能力不兼容", color: "warning" },
  unverified: { label: "未验证", color: "warning" },
  revoked: { label: "已撤销", color: "error" },
} as const;

export function localAgentVerified(device: LocalAgentDevice): boolean {
  return device.verified ?? Number(device.authenticated_at || 0) > 0;
}

export function localAgentReadiness(device: LocalAgentDevice): {
  key: keyof typeof readinessLabels | "upgrading";
  label: string;
  color: string;
} {
  if (device.readiness && device.readiness in readinessLabels) {
    return { key: device.readiness, ...readinessLabels[device.readiness] };
  }
  if (device.status === "revoked" || Number(device.revoked_at || 0) > 0) {
    return { key: "revoked", ...readinessLabels.revoked };
  }
  if (!localAgentVerified(device)) {
    return { key: "unverified", ...readinessLabels.unverified };
  }
  return { key: "upgrading", label: "等待 Server 更新", color: "warning" };
}

export function localAgentCapacity(device: LocalAgentDevice): {
  active: number;
  parallel: number;
  resident: number;
  resident_limit: number;
} {
  const declaredParallel = Math.max(1, Number(device.capabilities?.max_parallel_runs || 1));
  const parallel = Math.max(1, Number(device.capacity?.parallel || declaredParallel));
  return {
    active: Math.max(0, Number(device.capacity?.active || 0)),
    parallel,
    resident: Math.max(0, Number(device.capacity?.resident || 0)),
    resident_limit: Math.max(
      parallel,
      Number(device.capacity?.resident_limit || device.capabilities?.max_resident_runs || parallel * 4),
    ),
  };
}
