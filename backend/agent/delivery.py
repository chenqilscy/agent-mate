"""Deterministic user-facing delivery appendix built from Artifact authority."""
from __future__ import annotations

import json
from typing import Iterable

from storage.models import Artifact


HEADING = "## 权威交付记录"


def build_delivery_summary(artifacts: Iterable[Artifact], *, stopped: bool = False) -> str:
    items = list(artifacts)
    if not items:
        return ""
    lines = ["", "", HEADING, "", "以下信息来自本次 Run 的真实 Artifact 清单：", ""]
    for artifact in items:
        primary = "主产物 · " if artifact.is_primary else ""
        validation = artifact.validation_status
        acceptance = artifact.acceptance_status
        details = json.dumps(artifact.validation, ensure_ascii=False, sort_keys=True)
        if len(details) > 300:
            details = details[:300] + "…"
        lines.append(
            f"- {primary}`{artifact.path}` · {artifact.kind} · {artifact.size} bytes "
            f"· SHA-256 `{artifact.sha256}` · 校验 `{validation}` · 验收 `{acceptance}`"
        )
        if details and details != "{}":
            lines.append(f"  - 校验详情：`{details}`")
    if stopped:
        lines.extend(["", "> 本次运行已停止；上列文件真实存在，但不代表原任务已全部完成。"])
    elif any(item.validation_status != "passed" for item in items):
        lines.extend(["", "> 至少一个产物未通过校验，不能视为完整交付。"])
    elif any(item.acceptance_status != "accepted" for item in items):
        lines.extend(["", "> 产物已经生成并校验，但仍处于待验收状态。"])
    return "\n".join(lines)
