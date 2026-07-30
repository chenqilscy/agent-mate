"""Deterministic, fail-closed security scan for installable Skill packages.

This is deliberately a static policy gate, not an LLM review.  It scans every
text file in the package, records stable finding codes and never executes
scripts.  A human may acknowledge warning findings for community/local Skills;
dangerous findings cannot be overridden.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath
from typing import Any, Iterable

SCHEMA_VERSION = 1
TRUST_LEVELS = {"agentmate", "trusted", "community", "local"}
TRUSTED_LEVELS = {"agentmate", "trusted"}

_DANGEROUS_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "destructive-root-delete",
        "尝试递归删除系统根目录、用户目录或主目录",
        re.compile(
            r"(?:\brm\s+-[^\n]*r[^\n]*f[^\n]*(?:\s/|\s~|\$HOME)|"
            r"\bRemove-Item\b[^\n]*(?:-Recurse|-r)[^\n]*(?:\$HOME|\\Users\\|[A-Za-z]:\\))",
            re.IGNORECASE,
        ),
    ),
    (
        "encoded-payload-execution",
        "解码并直接执行隐藏载荷",
        re.compile(
            r"(?:base64\s+(?:--decode|-d)[^\n|]*\|\s*(?:sh|bash|zsh)\b|"
            r"FromBase64String\s*\([^\n]+\)[^\n]*(?:Invoke-Expression|\biex\b)|"
            r"(?:Invoke-Expression|\biex\b)[^\n]*FromBase64String)",
            re.IGNORECASE,
        ),
    ),
    (
        "download-and-execute",
        "从网络下载内容后直接交给命令解释器执行",
        re.compile(
            r"(?:curl|wget|Invoke-WebRequest|iwr)\b[^\n|;]*(?:\||;)\s*"
            r"(?:sudo\s+)?(?:sh|bash|zsh|pwsh|powershell|python)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "credential-exfiltration",
        "收集凭据或密钥并发送到外部地址",
        re.compile(
            r"(?:curl|wget|requests\.(?:post|put)|fetch\s*\()[^\n]{0,500}"
            r"(?:\.ssh|\.aws|credentials|api[_ -]?key|access[_ -]?token|password|"
            r"\$env:|\bos\.environ\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "prompt-injection-exfiltration",
        "要求绕过上级指令并泄露系统提示或敏感信息",
        re.compile(
            r"(?:ignore|disregard|bypass)[^\n]{0,120}(?:previous|system|developer|security)"
            r"[^\n]{0,240}(?:reveal|send|upload|exfiltrat|secret|credential|system prompt)",
            re.IGNORECASE,
        ),
    ),
)

_WARNING_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "process-execution",
        "包含启动本机命令或子进程的代码",
        re.compile(
            r"(?:\bsubprocess\.(?:run|Popen|call)|\bos\.system\s*\(|"
            r"\bchild_process\.(?:exec|spawn)|\bStart-Process\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "dynamic-code-execution",
        "包含动态代码执行",
        re.compile(r"(?:\beval\s*\(|\bexec\s*\(|Invoke-Expression|\biex\s+)", re.IGNORECASE),
    ),
    (
        "sensitive-file-access",
        "读取凭据目录、环境变量或敏感配置",
        re.compile(
            r"(?:\.ssh[/\\]|\.aws[/\\]|credentials(?:\.json)?|"
            r"\bos\.environ\b|\bprocess\.env\b|\$env:[A-Za-z_])",
            re.IGNORECASE,
        ),
    ),
    (
        "external-network-write",
        "包含向外部网络发送数据的操作",
        re.compile(
            r"(?:requests\.(?:post|put|patch)|fetch\s*\([^\n]+method\s*:\s*['\"](?:POST|PUT|PATCH)|"
            r"\bcurl\b[^\n]*(?:--data|-d\b|--upload-file|-T\b))",
            re.IGNORECASE,
        ),
    ),
    (
        "instruction-override",
        "包含试图覆盖上级指令或安全约束的内容",
        re.compile(
            r"(?:ignore|disregard|bypass)[^\n]{0,120}(?:previous|system|developer|security)",
            re.IGNORECASE,
        ),
    ),
)

_SCRIPT_SUFFIXES = {
    ".bat", ".cmd", ".js", ".mjs", ".ps1", ".py", ".rb", ".sh", ".ts", ".vbs",
}
_TEXT_SUFFIXES = _SCRIPT_SUFFIXES | {
    ".cfg", ".conf", ".ini", ".json", ".md", ".rst", ".toml", ".txt", ".yaml", ".yml",
}


def _content_hash(files: Iterable[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for path, data in sorted(files, key=lambda item: item[0].casefold()):
        digest.update(path.replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
    return digest.hexdigest()


def _decode_text(path: str, data: bytes) -> str | None:
    suffix = PurePosixPath(path.replace("\\", "/")).suffix.casefold()
    if suffix not in _TEXT_SUFFIXES and b"\x00" in data[:4096]:
        return None
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def scan_package(
    files: Iterable[tuple[str, bytes]],
    *,
    trust_level: str,
) -> dict[str, Any]:
    """Scan package bytes and return a stable, serializable report."""
    trust = (trust_level or "").strip().lower()
    if trust not in TRUST_LEVELS:
        raise ValueError(f"unknown Skill trust level: {trust_level}")
    material = [(path.replace("\\", "/"), data) for path, data in files]
    findings: list[dict[str, Any]] = []
    scanned_bytes = 0
    scanned_files = 0
    for path, data in sorted(material, key=lambda item: item[0].casefold()):
        text = _decode_text(path, data)
        if text is None:
            continue
        scanned_files += 1
        scanned_bytes += len(data)
        lines = text.splitlines() or [""]
        for severity, rules in (("dangerous", _DANGEROUS_RULES), ("warning", _WARNING_RULES)):
            for code, message, pattern in rules:
                match = pattern.search(text)
                if not match:
                    continue
                line = text.count("\n", 0, match.start()) + 1
                findings.append({
                    "code": code,
                    "severity": severity,
                    "path": path,
                    "line": line,
                    "message": message,
                })
        suffix = PurePosixPath(path).suffix.casefold()
        if suffix in _SCRIPT_SUFFIXES or "/scripts/" in f"/{path.casefold()}":
            findings.append({
                "code": "bundled-script",
                "severity": "warning",
                "path": path,
                "line": 1,
                "message": "技能包包含脚本文件；AgentMate 只把它当作静态资源，不会自动执行",
            })

    # One stable finding per code/path/line, with dangerous findings first.
    unique = {
        (item["code"], item["path"], item["line"]): item
        for item in findings
    }
    findings = sorted(
        unique.values(),
        key=lambda item: (
            0 if item["severity"] == "dangerous" else 1,
            item["path"].casefold(),
            item["line"],
            item["code"],
        ),
    )
    verdict = (
        "dangerous" if any(item["severity"] == "dangerous" for item in findings)
        else "warning" if findings
        else "safe"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "trust_level": trust,
        "verdict": verdict,
        "findings": findings,
        "scanned_files": scanned_files,
        "scanned_bytes": scanned_bytes,
        "content_hash": _content_hash(material),
        "scripts_executable": False,
    }


def requires_confirmation(report: dict[str, Any]) -> bool:
    return (
        report.get("verdict") == "warning"
        and str(report.get("trust_level") or "") not in TRUSTED_LEVELS
    )


def allows_runtime(report: dict[str, Any], warnings_accepted: bool) -> bool:
    verdict = str(report.get("verdict") or "")
    if verdict == "dangerous" or verdict not in {"safe", "warning"}:
        return False
    return not requires_confirmation(report) or warnings_accepted
