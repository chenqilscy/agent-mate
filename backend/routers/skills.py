"""SkillHub 已安装技能 —— 真实安装 / 发现 / 管理（WB-055）。

技能包是**每机器共享**的磁盘资源（~/.agentmate/skills/），owner 的安装/启停/卸载状态独立入库；
安装走真实 skillhub CLI 下载解压（agent/skills_store.py）。清单/详情来自真实文件与持久状态，非模拟。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agent import skills, skills_store
from auth.deps import current_user
import server_client

router = APIRouter(prefix="/api", tags=["skills"])


def _scope_owner() -> str:
    owner = current_user().id
    skills_store.set_owner(owner)
    return owner


def _report_release_metric(owner_id: str, release_id: str, event: str) -> None:
    from storage import db
    token = db.get_server_identity(owner_id) or ""
    if token and release_id:
        server_client.record_skill_release_metric(token, release_id, event)


def _skill_error_detail(exc: skills_store.SkillImportError) -> str | dict:
    if exc.code or exc.report:
        return {
            "code": exc.code or "skill_security_rejected",
            "message": str(exc),
            "security_scan": exc.report or {},
        }
    return str(exc)


class InstallBody(BaseModel):
    slug: str = ""
    name: str = ""  # 展示名/搜索词；无 slug 时用它去 SkillHub 搜索解析
    accept_security_warnings: bool = False


class ToggleBody(BaseModel):
    disabled: bool
    accept_security_warnings: bool = False


class UpgradeCatalogBody(BaseModel):
    accept_permissions: list[str] = []


class UpdateSkillBody(BaseModel):
    name: str
    description: str
    instructions: str
    accept_security_warnings: bool = False


class ImportDirectoryFile(BaseModel):
    path: str
    content: str


class ImportDirectoryBody(BaseModel):
    files: list[ImportDirectoryFile]
    accept_security_warnings: bool = False


class SkillCandidateBody(BaseModel):
    source_run_id: str
    target_scope: str = "local"
    slug: str
    name: str
    description: str
    instructions: str
    tools: list[str] = []


class SkillCandidateTestBody(BaseModel):
    test_run_id: str


class SkillCandidateApproveBody(BaseModel):
    accept_security_warnings: bool = False


class SkillCandidateRejectBody(BaseModel):
    reason: str = ""


class SkillRatingBody(BaseModel):
    rating: str


class SkillBundleBody(BaseModel):
    name: str
    description: str = ""
    skills: list[str]


def _candidate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(404, "skill candidate not found")
    if isinstance(exc, PermissionError):
        return HTTPException(404, "run not found")
    return HTTPException(409, str(exc))


@router.get("/skill-candidates")
def list_skill_candidates() -> dict:
    from agent import skill_learning

    owner = _scope_owner()
    return {"candidates": skill_learning.list_candidates(owner)}


@router.post("/skill-candidates")
def create_skill_candidate(body: SkillCandidateBody) -> dict:
    from agent import skill_learning

    owner = _scope_owner()
    try:
        candidate = skill_learning.create_candidate(
            owner_id=owner,
            source_run_id=body.source_run_id,
            target_scope=body.target_scope,
            slug=body.slug,
            name=body.name,
            description=body.description,
            instructions=body.instructions,
            tools=body.tools,
        )
        return {"candidate": candidate}
    except (KeyError, PermissionError, ValueError) as exc:
        raise _candidate_error(exc) from exc


@router.get("/skill-candidates/{candidate_id}")
def get_skill_candidate(candidate_id: str) -> dict:
    from agent import skill_learning

    candidate = skill_learning.get_candidate(candidate_id, _scope_owner())
    if not candidate:
        raise HTTPException(404, "skill candidate not found")
    return {"candidate": candidate}


@router.post("/skill-candidates/{candidate_id}/test")
def test_skill_candidate(candidate_id: str, body: SkillCandidateTestBody) -> dict:
    from agent import skill_learning

    owner = _scope_owner()
    try:
        return {"candidate": skill_learning.record_test(candidate_id, owner, body.test_run_id)}
    except (KeyError, PermissionError, ValueError) as exc:
        raise _candidate_error(exc) from exc


@router.post("/skill-candidates/{candidate_id}/approve")
def approve_skill_candidate(
    candidate_id: str,
    body: SkillCandidateApproveBody | None = None,
) -> dict:
    from agent import skill_learning

    owner = _scope_owner()
    try:
        return {
            "candidate": skill_learning.approve(
                candidate_id,
                owner,
                accept_security_warnings=bool(body and body.accept_security_warnings),
            )
        }
    except (KeyError, ValueError) as exc:
        raise _candidate_error(exc) from exc


@router.post("/skill-candidates/{candidate_id}/reject")
def reject_skill_candidate(candidate_id: str, body: SkillCandidateRejectBody) -> dict:
    from agent import skill_learning

    owner = _scope_owner()
    try:
        return {"candidate": skill_learning.reject(candidate_id, owner, body.reason)}
    except (KeyError, ValueError) as exc:
        raise _candidate_error(exc) from exc


@router.post("/skill-candidates/{candidate_id}/install")
def install_skill_candidate(candidate_id: str) -> dict:
    from agent import skill_learning

    owner = _scope_owner()
    try:
        return {"candidate": skill_learning.install_local(candidate_id, owner)}
    except (KeyError, ValueError, skills_store.SkillImportError) as exc:
        raise _candidate_error(exc) from exc


@router.post("/skill-candidates/{candidate_id}/rollback")
def rollback_skill_candidate(candidate_id: str) -> dict:
    from agent import skill_learning

    owner = _scope_owner()
    try:
        return {"candidate": skill_learning.rollback_local(candidate_id, owner)}
    except (KeyError, ValueError) as exc:
        raise _candidate_error(exc) from exc


@router.get("/skill-candidates/{candidate_id}/platform-release-payload")
def skill_candidate_platform_payload(candidate_id: str) -> dict:
    from agent import skill_learning

    owner = _scope_owner()
    try:
        return {"release": skill_learning.platform_release_payload(candidate_id, owner)}
    except (KeyError, ValueError) as exc:
        raise _candidate_error(exc) from exc


@router.get("/skills")
def list_installed() -> dict:
    _scope_owner()
    return {"skills": skills_store.scan(), "cli": skills_store.cli_available()}


@router.get("/skill-bundles")
def list_skill_bundles() -> dict:
    from agent import skill_bundles

    owner = _scope_owner()
    return {"bundles": skill_bundles.list_bundles(owner)}


@router.post("/skill-bundles")
def create_skill_bundle(body: SkillBundleBody) -> dict:
    from agent import skill_bundles

    owner = _scope_owner()
    try:
        return {
            "bundle": skill_bundles.create(
                owner, body.name, body.description, body.skills,
            )
        }
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.put("/skill-bundles/{bundle_id}")
def update_skill_bundle(bundle_id: str, body: SkillBundleBody) -> dict:
    from agent import skill_bundles

    owner = _scope_owner()
    try:
        return {
            "bundle": skill_bundles.update(
                bundle_id,
                owner,
                name=body.name,
                description=body.description,
                skills=body.skills,
            )
        }
    except KeyError as exc:
        raise HTTPException(404, "skill bundle not found") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.delete("/skill-bundles/{bundle_id}")
def delete_skill_bundle(bundle_id: str) -> dict:
    from agent import skill_bundles

    if not skill_bundles.delete(bundle_id, _scope_owner()):
        raise HTTPException(404, "skill bundle not found")
    return {"ok": True}


@router.post("/skill-bundles/{bundle_id}/resolve")
def resolve_skill_bundle(bundle_id: str) -> dict:
    from agent import skill_bundles

    owner = _scope_owner()
    result = skill_bundles.resolve(owner, [bundle_id])
    if result["missing_bundles"]:
        raise HTTPException(404, "skill bundle not found")
    return result


@router.get("/skill-usage")
def skill_usage_summary() -> dict:
    from agent import skill_usage

    owner = _scope_owner()
    return {"skills": skill_usage.summaries(owner)}


@router.get("/skill-governance")
def skill_governance_suggestions() -> dict:
    from agent import skill_usage

    owner = _scope_owner()
    return {
        "suggestions": skill_usage.suggestions(owner),
        "policy": {
            "automatic_delete": False,
            "automatic_merge": False,
            "umbrella_skill_requires_candidate_flow": True,
        },
    }


@router.post("/skill-governance/{suggestion_id}/ignore")
def ignore_skill_governance_suggestion(suggestion_id: str) -> dict:
    from agent import skill_usage

    owner = _scope_owner()
    try:
        skill_usage.ignore_suggestion(owner, suggestion_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@router.post("/skills/{key}/rating")
def rate_skill(key: str, body: SkillRatingBody) -> dict:
    from agent import skill_usage

    owner = _scope_owner()
    item = next(
        (
            skill for skill in skills_store.scan(owner)
            if key in {str(skill.get("key") or ""), str(skill.get("slug") or "")}
        ),
        None,
    )
    if not item:
        raise HTTPException(404, "skill not found")
    try:
        return {"rating": skill_usage.rate(owner, item, body.rating)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/skills/builtin")
def list_builtin() -> dict:
    """已安装的 AgentMate 目录技能，供 loadout 选择器（兼容旧路由名）。

    路由顺序：必须定义在 `/skills/{key}` 之前，否则会被它当成 key="builtin" 吃掉。
    """
    _scope_owner()
    return {"skills": skills.builtin_list()}


@router.get("/skills/search")
def search_skills(q: str = "", limit: int = 8) -> dict:
    """由本地 App 直接查询第三方 SkillHub；Server 不参与市场数据流（WB-215）。"""
    _scope_owner()
    return {"results": skills_store.search(q, limit), "source": "app"}


@router.get("/skills/rankings")
def skills_rankings(
    type: str = "featured", category: str = "", limit: int = 0
) -> dict:
    """由本地 App 直接读取第三方榜单；Server 登录状态不影响浏览（WB-215）。"""
    _scope_owner()
    return {"type": type, "skills": skills_store.rankings(type, category, limit), "source": "app"}


@router.get("/skills/catalog/{key}")
def catalog_skill_detail(key: str) -> dict:
    """AgentMate 推荐目录定义；与同 slug 的 SkillHub 商品显式隔离（WB-214）。"""
    _scope_owner()
    d = skills.catalog_detail(key)
    if not d:
        raise HTTPException(404, "catalog skill not found")
    return {"skill": d, "source": "catalog"}


@router.post("/skills/catalog/{key}/install")
def install_catalog_skill(key: str) -> dict:
    """Install an AgentMate recommended definition into the local skill directory."""
    from storage import db
    owner = _scope_owner()

    state = db.skill_catalog_state(key)
    if state.get("withdrawn"):
        raise HTTPException(410, "catalog skill withdrawn")
    spec = db.skill_spec_for(key)
    if not spec or not spec.get("instructions"):
        raise HTTPException(404, "catalog skill not found")
    if not spec.get("compatible", True):
        raise HTTPException(409, spec.get("compatibility_error") or "current App is incompatible with this skill")
    try:
        required_permissions = skills.tool_permissions(
            spec.get("tools") if isinstance(spec.get("tools"), list) else []
        )
        result = skills_store.install_catalog_skill(
            str(spec["slug"]),
            str(spec["name"]),
            str(spec.get("description") or ""),
            str(spec["instructions"]),
            str(spec.get("version") or ""),
            spec.get("files") if isinstance(spec.get("files"), list) else [],
            spec.get("tools") if isinstance(spec.get("tools"), list) else [],
            required_permissions,
            str(spec.get("tool_contract_version") or "1"),
            str(spec.get("server_release_id") or ""),
            spec.get("platforms") if isinstance(spec.get("platforms"), list) else [],
            spec.get("environments") if isinstance(spec.get("environments"), list) else [],
            spec.get("requires_tools") if isinstance(spec.get("requires_tools"), list) else [],
        )
        _report_release_metric(owner, str(spec.get("server_release_id") or ""), "installed")
        return result
    except skills_store.SkillImportError as exc:
        _report_release_metric(owner, str(spec.get("server_release_id") or ""), "install_failed")
        raise HTTPException(exc.status_code, _skill_error_detail(exc)) from exc


@router.post("/skills/catalog/{key}/upgrade")
def upgrade_catalog_skill(key: str, body: UpgradeCatalogBody | None = None) -> dict:
    """把已安装的 AgentMate 目录技能原子升级到当前 Server 定义。"""
    from storage import db
    owner = _scope_owner()

    state = db.skill_catalog_state(key)
    if state.get("withdrawn"):
        raise HTTPException(410, "catalog skill withdrawn")
    spec = db.skill_spec_for(key)
    if not spec or not spec.get("instructions"):
        raise HTTPException(404, "catalog skill not found")
    if not spec.get("compatible", True):
        raise HTTPException(409, spec.get("compatibility_error") or "current App is incompatible with this skill")
    required_permissions = skills.tool_permissions(
        spec.get("tools") if isinstance(spec.get("tools"), list) else []
    )
    installed = next(
        (item for item in skills_store.scan() if item.get("slug") == spec["slug"]), None,
    )
    snapshot = skills_store.release_snapshot(str(installed["key"])) if installed else None
    current_permissions = set(snapshot.get("permissions") or []) if snapshot else set()
    added_permissions = sorted(set(required_permissions) - current_permissions)
    accepted = set(body.accept_permissions if body else [])
    if added_permissions and not set(added_permissions).issubset(accepted):
        raise HTTPException(409, {
            "code": "permission_confirmation_required",
            "added_permissions": added_permissions,
        })
    try:
        result = skills_store.upgrade_catalog_skill(
            str(spec["slug"]), str(spec["name"]), str(spec.get("description") or ""),
            str(spec["instructions"]), str(spec.get("version") or ""),
            spec.get("files") if isinstance(spec.get("files"), list) else [],
            spec.get("tools") if isinstance(spec.get("tools"), list) else [],
            required_permissions,
            str(spec.get("tool_contract_version") or "1"),
            str(spec.get("server_release_id") or ""),
            spec.get("platforms") if isinstance(spec.get("platforms"), list) else [],
            spec.get("environments") if isinstance(spec.get("environments"), list) else [],
            spec.get("requires_tools") if isinstance(spec.get("requires_tools"), list) else [],
        )
        _report_release_metric(owner, str(spec.get("server_release_id") or ""), "installed")
        return result
    except skills_store.SkillImportError as exc:
        _report_release_metric(owner, str(spec.get("server_release_id") or ""), "install_failed")
        raise HTTPException(exc.status_code, _skill_error_detail(exc)) from exc


@router.get("/skills/{key}")
def get_detail(key: str) -> dict:
    owner = _scope_owner()
    d = skills_store.detail(key)
    if not d:
        raise HTTPException(404, "skill not found")
    if d.get("source") == "agentmate":
        catalog = skills.catalog_detail(str(d.get("slug") or key))
        if catalog:
            d = {
                **catalog,
                "trust_level": d.get("trust_level"),
                "security_scan": d.get("security_scan"),
                "security_warnings_accepted": d.get("security_warnings_accepted"),
            }
    from agent import skill_usage
    usage = next(
        (
            item for item in skill_usage.summaries(owner)
            if item.get("slug") == d.get("slug")
        ),
        None,
    )
    d["usage"] = usage
    return {"skill": d}


@router.patch("/skills/{key}")
def update_skill(key: str, body: UpdateSkillBody) -> dict:
    _scope_owner()
    try:
        return skills_store.update_skill(
            key, body.name, body.description, body.instructions,
            accept_security_warnings=body.accept_security_warnings,
        )
    except skills_store.SkillImportError as exc:
        raise HTTPException(exc.status_code, _skill_error_detail(exc)) from exc


@router.post("/skills/install")
def install_skill(body: InstallBody) -> dict:
    _scope_owner()
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
    reason = skills_store.market_block_reason(slug)
    if reason is not None:
        detail = f"该 SkillHub 技能已由平台下架：{reason}" if reason else "该 SkillHub 技能已由平台下架"
        raise HTTPException(409, detail)
    res = skills_store.install(
        slug,
        display_name=display,
        accept_security_warnings=body.accept_security_warnings,
    )
    if not res.get("ok"):
        if res.get("code") or res.get("security_scan"):
            raise HTTPException(
                int(res.get("status_code") or 409),
                {
                    "code": res.get("code") or "skill_security_rejected",
                    "message": res.get("error") or "安装失败",
                    "security_scan": res.get("security_scan") or {},
                },
            )
        raise HTTPException(int(res.get("status_code") or 502), res.get("error") or "安装失败")
    return res


@router.post("/skills/import")
async def import_skill(
    request: Request,
    filename: str = "",
    accept_security_warnings: bool = False,
) -> dict:
    _scope_owner()
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > skills_store.MAX_IMPORT_BYTES:
        raise HTTPException(413, "技能包过大（最多 20MB）")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > skills_store.MAX_IMPORT_BYTES:
            raise HTTPException(413, "技能包过大（最多 20MB）")
    try:
        return skills_store.import_skill_file(
            filename,
            bytes(data),
            accept_security_warnings=accept_security_warnings,
        )
    except skills_store.SkillImportError as exc:
        raise HTTPException(exc.status_code, _skill_error_detail(exc)) from exc


@router.post("/skills/import-directory")
def import_skill_directory(body: ImportDirectoryBody) -> dict:
    _scope_owner()
    try:
        return skills_store.import_skill_directory(
            [item.model_dump() for item in body.files],
            accept_security_warnings=body.accept_security_warnings,
        )
    except skills_store.SkillImportError as exc:
        raise HTTPException(exc.status_code, _skill_error_detail(exc)) from exc


@router.post("/skills/{key}/uninstall")
def uninstall_skill(key: str) -> dict:
    _scope_owner()
    if not skills_store.uninstall(key):
        raise HTTPException(404, "skill not found")
    return {"ok": True}


@router.post("/skills/{key}/restore")
def restore_skill(key: str) -> dict:
    _scope_owner()
    if not skills_store.restore(key):
        raise HTTPException(404, "recoverable skill installation not found")
    return {"ok": True}


@router.post("/skills/{key}/toggle")
def toggle_skill(key: str, body: ToggleBody) -> dict:
    _scope_owner()
    try:
        if not skills_store.set_disabled(
            key,
            body.disabled,
            accept_security_warnings=body.accept_security_warnings,
        ):
            raise HTTPException(404, "skill not found")
    except skills_store.SkillImportError as exc:
        raise HTTPException(exc.status_code, _skill_error_detail(exc)) from exc
    return {"ok": True, "disabled": body.disabled}


@router.post("/skills/{key}/reveal")
def reveal_skill(key: str) -> dict:
    _scope_owner()
    if not skills_store.reveal(key):
        raise HTTPException(400, "无法打开该技能目录")
    return {"ok": True}
