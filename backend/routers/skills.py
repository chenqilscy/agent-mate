"""SkillHub 已安装技能 —— 真实安装 / 发现 / 管理（WB-055）。

技能是**每机器**的磁盘资源（~/.agentmate/skills/），不按 owner 隔离；安装走真实
skillhub CLI 下载解压（agent/skills_store.py）。清单/详情来自真实文件，非模拟。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agent import skills, skills_store

router = APIRouter(prefix="/api", tags=["skills"])


class InstallBody(BaseModel):
    slug: str = ""
    name: str = ""  # 展示名/搜索词；无 slug 时用它去 SkillHub 搜索解析


class ToggleBody(BaseModel):
    disabled: bool


class UpdateSkillBody(BaseModel):
    name: str
    description: str
    instructions: str


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
    """已安装的 AgentMate 目录技能，供 loadout 选择器（兼容旧路由名）。

    路由顺序：必须定义在 `/skills/{key}` 之前，否则会被它当成 key="builtin" 吃掉。
    """
    return {"skills": skills.builtin_list()}


@router.get("/skills/search")
def search_skills(q: str = "", limit: int = 8) -> dict:
    """由本地 App 直接查询第三方 SkillHub；Server 不参与市场数据流（WB-215）。"""
    return {"results": skills_store.search(q, limit), "source": "app"}


@router.get("/skills/rankings")
def skills_rankings(
    type: str = "featured", category: str = "", limit: int = 0
) -> dict:
    """由本地 App 直接读取第三方榜单；Server 登录状态不影响浏览（WB-215）。"""
    return {"type": type, "skills": skills_store.rankings(type, category, limit), "source": "app"}


@router.get("/skills/catalog/{key}")
def catalog_skill_detail(key: str) -> dict:
    """AgentMate 推荐目录定义；与同 slug 的 SkillHub 商品显式隔离（WB-214）。"""
    d = skills.catalog_detail(key)
    if not d:
        raise HTTPException(404, "catalog skill not found")
    return {"skill": d, "source": "catalog"}


@router.post("/skills/catalog/{key}/install")
def install_catalog_skill(key: str) -> dict:
    """Install an AgentMate recommended definition into the local skill directory."""
    from storage import db

    spec = db.skill_spec_for(key)
    if not spec or not spec.get("instructions"):
        raise HTTPException(404, "catalog skill not found")
    try:
        return skills_store.install_catalog_skill(
            str(spec["slug"]),
            str(spec["name"]),
            str(spec.get("description") or ""),
            str(spec["instructions"]),
            str(spec.get("version") or ""),
            spec.get("files") if isinstance(spec.get("files"), list) else [],
        )
    except skills_store.SkillImportError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.post("/skills/catalog/{key}/upgrade")
def upgrade_catalog_skill(key: str) -> dict:
    """把已安装的 AgentMate 目录技能原子升级到当前 Server 定义。"""
    from storage import db

    spec = db.skill_spec_for(key)
    if not spec or not spec.get("instructions"):
        raise HTTPException(404, "catalog skill not found")
    try:
        return skills_store.upgrade_catalog_skill(
            str(spec["slug"]), str(spec["name"]), str(spec.get("description") or ""),
            str(spec["instructions"]), str(spec.get("version") or ""),
            spec.get("files") if isinstance(spec.get("files"), list) else [],
        )
    except skills_store.SkillImportError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.get("/skills/{key}")
def get_detail(key: str) -> dict:
    d = skills_store.detail(key)
    if not d:
        raise HTTPException(404, "skill not found")
    if d.get("source") == "agentmate":
        catalog = skills.catalog_detail(str(d.get("slug") or key))
        if catalog:
            d = catalog
    return {"skill": d}


@router.patch("/skills/{key}")
def update_skill(key: str, body: UpdateSkillBody) -> dict:
    try:
        return skills_store.update_skill(key, body.name, body.description, body.instructions)
    except skills_store.SkillImportError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


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
