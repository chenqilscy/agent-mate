"""SkillHub 已安装技能 —— 真实安装 / 发现 / 管理（WB-055）。

技能是**每机器**的磁盘资源（~/.workbuddy/skills/），不按 owner 隔离；安装走真实
skillhub CLI 下载解压（agent/skills_store.py）。清单/详情来自真实文件，非模拟。
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

import hub_client
from agent import skills, skills_store

router = APIRouter(prefix="/api", tags=["skills"])


def _bearer(authorization: str) -> str:
    return authorization[7:].strip() if authorization[:7].lower() == "bearer " else ""


class InstallBody(BaseModel):
    slug: str = ""
    name: str = ""  # 展示名/搜索词；无 slug 时用它去 SkillHub 搜索解析


class ToggleBody(BaseModel):
    disabled: bool


class ImportDirectoryFile(BaseModel):
    path: str
    content: str


class ImportDirectoryBody(BaseModel):
    files: list[ImportDirectoryFile]


@router.get("/skills")
def list_installed() -> dict:
    return {"skills": skills_store.scan(), "cli": skills_store.cli_available()}


@router.get("/skills/builtin")
def list_builtin() -> dict:
    """内置技能（真工具包 / 真提示词），不在磁盘上，磁盘扫描列不出 —— 供 loadout 选择器（WB-180）。

    路由顺序：必须定义在 `/skills/{key}` 之前，否则会被它当成 key="builtin" 吃掉。
    """
    return {"skills": skills.builtin_list()}


@router.get("/skills/search")
def search_skills(q: str = "", limit: int = 8, authorization: str = Header(default="")) -> dict:
    # WB-070：优先经 Hub 查询代理（富字段：下载/星/图标），未接/不可达/空 → 回退本地 CLI 搜索（离线兜底）。
    if q.strip() and hub_client.hub_enabled():
        proxied = hub_client.search_skillhub(_bearer(authorization), q, limit)
        if proxied:
            return {"results": proxied, "source": "hub"}
    return {"results": skills_store.search(q, limit), "source": "local"}


@router.get("/skills/rankings")
def skills_rankings(
    type: str = "featured", category: str = "", limit: int = 0, authorization: str = Header(default="")
) -> dict:
    # skillhub.cn 实时目录（WB-064）：featured/hot/recommended/newest/trending/all/paid。
    # WB-186：与 search/preview 同口径（WB-130「App 不直连 SkillHub，统一经 Manager」）——
    # 接了 Hub 就走代理；未接/不可达/无果 → 回退本地 CLI 直连（离线兜底）。
    # Manager 走 HTTP showcase 无需 CLI，故本机没装 CLI 时也能拿到真实榜单（此前只能吃前端静态假数据）。
    if hub_client.hub_enabled():
        proxied = hub_client.skill_rankings(_bearer(authorization), type, 0)
        if proxied:
            # 「已安装」是本机磁盘的知识，Manager 给不出来 → 本地加工后再返回。
            return {"type": type, "skills": skills_store.decorate_cards(proxied, category, limit),
                    "source": "hub"}
    return {"type": type, "skills": skills_store.rankings(type, category, limit), "source": "local"}


@router.get("/skills/preview")
def preview_skill(slug: str = "", name: str = "", authorization: str = Header(default="")) -> dict:
    # 安装前预览：未安装的技能也能看 SKILL.md（临时下载，不落 ~/.workbuddy/skills）。
    # WB-130：优先经 Manager 取数（App 不直连 SkillHub）——有 slug 且已接 Hub → 走代理；
    # 未接/不可达/Manager 无果 → 回退本地 CLI 直连预览（离线兜底）。
    slug, name = slug.strip(), name.strip()
    if slug and not skills_store.valid_slug(slug):
        # WB-185：早拦——slug 还会被拼进发往 Manager 的代理 URL。
        raise HTTPException(400, "非法 slug（仅允许字母、数字与 . _ -）")
    if slug and hub_client.hub_enabled():
        proxied = hub_client.skill_preview(_bearer(authorization), slug, name)
        if proxied:
            return {"skill": proxied, "source": "hub"}
    d = skills_store.preview(slug=slug, name=name)
    if not d:
        raise HTTPException(404, f"SkillHub 未找到「{name or slug}」或预览失败")
    return {"skill": d, "source": "local"}


@router.get("/skills/{key}")
def get_detail(key: str) -> dict:
    d = skills_store.detail(key)
    if not d:
        raise HTTPException(404, "skill not found")
    return {"skill": d}


@router.post("/skills/install")
def install_skill(body: InstallBody) -> dict:
    if not skills_store.cli_available():
        raise HTTPException(503, "SkillHub CLI 未安装（~/.skillhub/skills_store_cli.py）")
    slug = body.slug.strip()
    display = body.name.strip()
    if slug and not skills_store.valid_slug(slug):  # WB-185：客户端错误 → 400，而非 install 的 502
        raise HTTPException(400, "非法 slug（仅允许字母、数字与 . _ -）")
    if not slug:
        slug = skills_store.resolve_slug(display) or ""
        if not slug:
            raise HTTPException(404, f"SkillHub 未找到「{display or body.slug}」")
    res = skills_store.install(slug, display_name=display)
    if not res.get("ok"):
        raise HTTPException(502, res.get("error") or "安装失败")
    return res


@router.post("/skills/import")
async def import_skill(request: Request, filename: str = "") -> dict:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > skills_store.MAX_IMPORT_BYTES:
        raise HTTPException(413, "技能包过大（最多 20MB）")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > skills_store.MAX_IMPORT_BYTES:
            raise HTTPException(413, "技能包过大（最多 20MB）")
    try:
        return skills_store.import_skill_file(filename, bytes(data))
    except skills_store.SkillImportError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.post("/skills/import-directory")
def import_skill_directory(body: ImportDirectoryBody) -> dict:
    try:
        return skills_store.import_skill_directory([item.model_dump() for item in body.files])
    except skills_store.SkillImportError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.post("/skills/{key}/uninstall")
def uninstall_skill(key: str) -> dict:
    if not skills_store.uninstall(key):
        raise HTTPException(404, "skill not found")
    return {"ok": True}


@router.post("/skills/{key}/toggle")
def toggle_skill(key: str, body: ToggleBody) -> dict:
    if not skills_store.set_disabled(key, body.disabled):
        raise HTTPException(404, "skill not found")
    return {"ok": True, "disabled": body.disabled}


@router.post("/skills/{key}/reveal")
def reveal_skill(key: str) -> dict:
    if not skills_store.reveal(key):
        raise HTTPException(400, "无法打开该技能目录")
    return {"ok": True}
