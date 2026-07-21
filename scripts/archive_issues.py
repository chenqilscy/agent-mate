#!/usr/bin/env python3
"""Compact terminal AgentMate issues into deterministic Markdown archives.

Active issues remain as one file per issue under ``docs/issues``. Fixed and
wontfix issues are preserved verbatim (metadata + body) in numbered archive
volumes with stable ``#wb-NNN`` anchors. Run with ``--apply`` after closing an
issue and with ``--check`` in validation/CI.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ISSUES = ROOT / "docs" / "issues"
ARCHIVE = ISSUES / "archive"
TERMINAL = {"fixed", "wontfix"}
ACTIVE = {"open", "in-progress", "deferred"}
STATUS_ICON = {
    "open": "⬜",
    "in-progress": "🟡",
    "fixed": "✅",
    "deferred": "⏸",
    "wontfix": "🚫",
}
ISSUE_NAME_RE = re.compile(r"^WB-(\d{3,})-[A-Za-z0-9-]+\.md$")
RECORD_RE = re.compile(
    r"<!-- issue-record:start (?P<meta>\{.*?\}) -->\n"
    r"(?P<body>.*?)"
    r"<!-- issue-record:end (?P<id>WB-\d{3,}) -->",
    re.DOTALL,
)
LINK_RE = re.compile(r"(?P<prefix>\]\()(?P<target>[^)\s]+)(?P<suffix>\))")


@dataclass(frozen=True)
class Issue:
    id: str
    number: int
    source: str
    title: str
    severity: str
    area: str
    status: str
    created: str
    frontmatter: str
    body: str


def _frontmatter_value(frontmatter: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*(.*?)\s*$", frontmatter, re.MULTILINE)
    return match.group(1).strip() if match else ""


def parse_issue(path: Path) -> Issue:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = re.match(r"^---\n(?P<frontmatter>.*?)\n---\n(?P<body>.*)$", text, re.DOTALL)
    if not match:
        raise ValueError(f"invalid issue frontmatter: {path.relative_to(ROOT)}")
    frontmatter = match.group("frontmatter").strip()
    issue_id = _frontmatter_value(frontmatter, "id")
    file_match = ISSUE_NAME_RE.match(path.name)
    if not file_match or issue_id != f"WB-{int(file_match.group(1)):03d}":
        raise ValueError(f"issue id/file mismatch: {path.relative_to(ROOT)}")
    status_raw = _frontmatter_value(frontmatter, "status")
    status = status_raw.split()[0]
    if status not in ACTIVE | TERMINAL:
        raise ValueError(f"invalid status {status_raw!r}: {path.relative_to(ROOT)}")
    return Issue(
        id=issue_id,
        number=int(file_match.group(1)),
        source=path.name,
        title=_frontmatter_value(frontmatter, "title"),
        severity=_frontmatter_value(frontmatter, "severity"),
        area=_frontmatter_value(frontmatter, "area"),
        status=status,
        created=_frontmatter_value(frontmatter, "created"),
        frontmatter=frontmatter,
        body=match.group("body").strip(),
    )


def volume_path(number: int, year: str) -> Path:
    start = 1 if number < 100 else (number // 100) * 100
    end = 99 if number < 100 else start + 99
    return ARCHIVE / year / f"WB-{start:03d}-{end:03d}.md"


def issue_year(created: str, source: str) -> str:
    match = re.match(r"^(\d{4})", created or "")
    if match:
        return match.group(1)
    try:
        year = subprocess.check_output(
            ["git", "log", "-1", "--format=%ad", "--date=format:%Y", "--", f"docs/issues/{source}"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        ).strip()
    except subprocess.CalledProcessError:
        year = ""
    return year if re.fullmatch(r"\d{4}", year) else "undated"


def record_meta(issue: Issue) -> dict[str, object]:
    return {
        "id": issue.id,
        "number": issue.number,
        "source": issue.source,
        "title": issue.title,
        "severity": issue.severity,
        "area": issue.area,
        "status": issue.status,
        "created": issue.created,
    }


def render_record(issue: Issue) -> str:
    meta = json.dumps(record_meta(issue), ensure_ascii=False, separators=(",", ":"))
    body = re.sub(r"^(#{2,5})(?=\s)", r"#\1", issue.body, flags=re.MULTILINE)
    return (
        f"<!-- issue-record:start {meta} -->\n"
        f'<a id="{issue.id.lower()}"></a>\n\n'
        f"## {issue.id} · {issue.title}\n\n"
        "<details>\n<summary>原始元数据</summary>\n\n"
        f"```yaml\n{issue.frontmatter}\n```\n\n</details>\n\n"
        f"{body}\n\n"
        f"<!-- issue-record:end {issue.id} -->"
    )


def load_archive_records() -> dict[str, tuple[dict[str, object], str, Path]]:
    records: dict[str, tuple[dict[str, object], str, Path]] = {}
    if not ARCHIVE.exists():
        return records
    for path in sorted(ARCHIVE.rglob("WB-*.md")):
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        for match in RECORD_RE.finditer(text):
            meta = json.loads(match.group("meta"))
            issue_id = str(meta.get("id") or "")
            if issue_id != match.group("id") or issue_id in records:
                raise ValueError(f"duplicate or invalid archive record {issue_id}: {path.relative_to(ROOT)}")
            records[issue_id] = (meta, match.group(0).strip(), path)
    return records


def tracked_markdown() -> list[Path]:
    output = subprocess.check_output(
        ["git", "-c", "core.quotepath=false", "ls-files", "-z", "*.md"], cwd=ROOT
    ).decode("utf-8")
    return [ROOT / line for line in output.split("\0") if line]


def relative_link(source: Path, destination: Path, issue_id: str) -> str:
    rel = os.path.relpath(destination, source.parent).replace("\\", "/")
    return f"{rel}#{issue_id.lower()}" if destination.parent != ISSUES else rel


def rewrite_issue_links(
    text: str,
    source: Path,
    source_destinations: dict[str, tuple[str, Path]],
) -> str:
    def replace(match: re.Match[str]) -> str:
        target = match.group("target")
        path_part = target.split("#", 1)[0]
        basename = Path(path_part.replace("\\", "/")).name
        destination = source_destinations.get(basename)
        if not destination:
            return match.group(0)
        issue_id, destination_path = destination
        return f"{match.group('prefix')}{relative_link(source, destination_path, issue_id)}{match.group('suffix')}"

    return LINK_RE.sub(replace, text)


def volume_header(path: Path, metas: list[dict[str, object]]) -> str:
    ids = sorted(metas, key=lambda item: int(item["number"]))
    first = str(ids[0]["id"])
    last = str(ids[-1]["id"])
    rows = ["| ID | 状态 | 严重度 | 领域 | 标题 |", "|---|---|---|---|---|"]
    for meta in ids:
        issue_id = str(meta["id"])
        rows.append(
            f"| [{issue_id}](#{issue_id.lower()}) | {STATUS_ICON[str(meta['status'])]} | "
            f"{meta['severity']} | {meta['area']} | {meta['title']} |"
        )
    return (
        f"# AgentMate 已关闭 Issues：{first}～{last}\n\n"
        "> 本文件由 `scripts/archive_issues.py` 维护。每条记录保留原始元数据、完整正文和稳定锚点；"
        "不要手工拆回单文件。\n\n"
        f"共 {len(ids)} 条终态记录。\n\n"
        + "\n".join(rows)
        + "\n\n---\n\n"
    )


def render_active_readme(active: list[Issue], archive_count: int, max_id: int) -> str:
    rows = ["| ID | 状态 | 严重度 | 领域 | 标题 |", "|----|------|--------|------|------|"]
    for issue in sorted(active, key=lambda item: item.number):
        rows.append(
            f"| [{issue.id}]({issue.source}) | {STATUS_ICON[issue.status]} | {issue.severity} | "
            f"{issue.area} | {issue.title} |"
        )
    if not active:
        rows.append("| — | — | — | — | 当前没有活动 issue |")
    return f"""# AgentMate Issues 登记册

本目录只保留**活动 issue**。所有发现的问题先登记、再处理；终态记录会合并归档，但不会删除审计内容。
完整流程由 `.agents/skills/issue-tracker/SKILL.md` 定义。

## 约定

- 活动状态 `open` / `in-progress` / `deferred`：每个问题一个 `WB-<编号>-<slug>.md` 文件。
- 终态 `fixed` / `wontfix`：运行 `python scripts/archive_issues.py --apply` 后进入 [`archive/`](archive/README.md)。
- 编号全局递增且不复用；当前最大编号是 `WB-{max_id:03d}`，可用 `python scripts/archive_issues.py --next-id` 查询。
- 活动文件 frontmatter 是权威状态；下表是活动状态镜像。

## 活动台账

> 状态：⬜ open · 🟡 in-progress · ⏸ deferred

{chr(10).join(rows)}

## 已关闭归档

共 {archive_count} 条 `fixed` / `wontfix` 记录，按年份和编号段合并保存。详情、处理记录和原始文件名见
[`archive/README.md`](archive/README.md)。Git 历史仍可追溯迁移前的独立文件。
"""


def render_archive_readme(records: dict[str, tuple[dict[str, object], str, Path]]) -> str:
    grouped: dict[Path, list[dict[str, object]]] = {}
    for meta, _record, path in records.values():
        grouped.setdefault(path, []).append(meta)
    rows = ["| 归档卷 | 数量 | fixed | wontfix | 编号范围 |", "|---|---:|---:|---:|---|"]
    for path in sorted(grouped):
        metas = sorted(grouped[path], key=lambda item: int(item["number"]))
        fixed = sum(meta["status"] == "fixed" for meta in metas)
        wontfix = sum(meta["status"] == "wontfix" for meta in metas)
        rel = path.relative_to(ARCHIVE).as_posix()
        rows.append(
            f"| [{rel}]({rel}) | {len(metas)} | {fixed} | {wontfix} | "
            f"{metas[0]['id']}～{metas[-1]['id']} |"
        )
    return (
        "# AgentMate 已关闭 Issue 归档\n\n"
        "终态 issue 按编号段合并，全文、frontmatter、处理记录和稳定锚点均保留。"
        "活动 issue 请回到 [`../README.md`](../README.md)。\n\n"
        + "\n".join(rows)
        + "\n"
    )


def collect_root_issues() -> list[Issue]:
    return [parse_issue(path) for path in sorted(ISSUES.glob("WB-*.md"))]


def validate() -> list[str]:
    errors: list[str] = []
    root_issues = collect_root_issues()
    terminal_root = [issue.id for issue in root_issues if issue.status in TERMINAL]
    if terminal_root:
        errors.append(f"terminal issues remain in root: {', '.join(terminal_root)}")
    archived = load_archive_records()
    active_ids = {issue.id for issue in root_issues}
    overlap = active_ids & set(archived)
    if overlap:
        errors.append(f"active/archive duplicates: {', '.join(sorted(overlap))}")
    all_numbers = [issue.number for issue in root_issues] + [int(key.split("-")[1]) for key in archived]
    max_id = max(all_numbers, default=0)
    expected_root = render_active_readme(root_issues, len(archived), max_id)
    if not (ISSUES / "README.md").exists() or (ISSUES / "README.md").read_text(encoding="utf-8").replace("\r\n", "\n") != expected_root:
        errors.append("docs/issues/README.md is not synchronized")
    expected_archive = render_archive_readme(archived)
    archive_index = ARCHIVE / "README.md"
    if not archive_index.exists() or archive_index.read_text(encoding="utf-8").replace("\r\n", "\n") != expected_archive:
        errors.append("docs/issues/archive/README.md is not synchronized")
    known_sources = {issue.source for issue in root_issues}
    known_sources.update(str(meta["source"]) for meta, _record, _path in archived.values())
    for path in tracked_markdown() + list(ARCHIVE.rglob("*.md")):
        if not path.exists() or path.name in known_sources and path.parent == ISSUES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in LINK_RE.finditer(text):
            basename = Path(match.group("target").split("#", 1)[0].replace("\\", "/")).name
            if basename not in known_sources:
                continue
            target = match.group("target").split("#", 1)[0]
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                errors.append(f"stale issue link: {path.relative_to(ROOT)} -> {match.group('target')}")
    return errors


def apply_archive() -> None:
    root_issues = collect_root_issues()
    existing = load_archive_records()
    active = [issue for issue in root_issues if issue.status in ACTIVE]
    terminal = [issue for issue in root_issues if issue.status in TERMINAL]
    records: dict[str, tuple[dict[str, object], str, Path]] = {}
    for issue_id, (meta, record, _old_path) in existing.items():
        path = volume_path(
            int(meta["number"]), issue_year(str(meta.get("created") or ""), str(meta["source"]))
        )
        records[issue_id] = (meta, record, path)
    for issue in terminal:
        if issue.id in records:
            raise ValueError(f"issue already archived: {issue.id}")
        path = volume_path(issue.number, issue_year(issue.created, issue.source))
        records[issue.id] = (record_meta(issue), render_record(issue), path)

    destinations: dict[str, tuple[str, Path]] = {
        issue.source: (issue.id, ISSUES / issue.source) for issue in active
    }
    for issue_id, (meta, _record, path) in records.items():
        destinations[str(meta["source"])] = (issue_id, path)

    grouped: dict[Path, list[tuple[dict[str, object], str]]] = {}
    for meta, record, path in records.values():
        grouped.setdefault(path, []).append((meta, record))
    for path, entries in grouped.items():
        entries.sort(key=lambda item: int(item[0]["number"]))
        metas = [item[0] for item in entries]
        records_text = "\n\n---\n\n".join(item[1] for item in entries)
        content = volume_header(path, metas) + records_text + "\n"
        content = rewrite_issue_links(content, path, destinations)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    expected_volumes = set(grouped)
    for stale in ARCHIVE.rglob("WB-*.md") if ARCHIVE.exists() else []:
        if stale not in expected_volumes:
            stale.unlink()

    for path in tracked_markdown():
        if not path.exists() or path.parent == ISSUES and ISSUE_NAME_RE.match(path.name):
            continue
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        rewritten = rewrite_issue_links(text, path, destinations)
        if rewritten != text:
            path.write_text(rewritten, encoding="utf-8", newline="\n")

    for issue in terminal:
        path = ISSUES / issue.source
        if path.parent != ISSUES or not ISSUE_NAME_RE.match(path.name):
            raise ValueError(f"refusing unsafe delete: {path}")
        path.unlink()

    archive_records = load_archive_records()
    all_numbers = [issue.number for issue in active] + [int(key.split("-")[1]) for key in archive_records]
    (ISSUES / "README.md").write_text(
        render_active_readme(active, len(archive_records), max(all_numbers, default=0)),
        encoding="utf-8",
        newline="\n",
    )
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    (ARCHIVE / "README.md").write_text(
        render_archive_readme(archive_records), encoding="utf-8", newline="\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true", help="archive terminal root issues")
    mode.add_argument("--check", action="store_true", help="validate active/archive invariants")
    mode.add_argument("--next-id", action="store_true", help="print the next global WB id")
    args = parser.parse_args()
    if args.next_id:
        ids = [issue.number for issue in collect_root_issues()]
        ids.extend(int(key.split("-")[1]) for key in load_archive_records())
        print(f"WB-{max(ids, default=0) + 1:03d}")
        return 0
    if args.apply:
        apply_archive()
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    archived = len(load_archive_records())
    active = len(collect_root_issues())
    print(f"issue archive check passed: active={active}, archived={archived}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
