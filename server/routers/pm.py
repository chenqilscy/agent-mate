"""Project PM completion: custom fields, dependencies, sprints, burndown and CSV export (WB-112f)."""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

import db
from auth import CurrentAccount
from models import Account, can_manage, can_write

router = APIRouter(prefix="/api", tags=["pm"])
_FIELD_TYPES = {"text", "number", "date", "select", "boolean"}
_SPRINT_STATUSES = {"planned", "active", "closed"}


def _access(project_id: str, account: Account, *, write: bool = False):
    role = db.project_access_role(project_id, account.id)
    if role is None:
        raise HTTPException(404, "project not found")
    if write and not can_write(role):
        raise HTTPException(403, "Viewer is read-only")
    if write and db.project_is_archived(project_id):
        raise HTTPException(409, "archived project is read-only")
    return role


def _iso_date(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(400, f"invalid {name}") from exc


class CustomFieldBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    field_type: str = "text"
    options: list[str] = Field(default_factory=list, max_length=50)
    required: bool = False


@router.get("/projects/{project_id}/custom-fields")
def list_custom_fields(project_id: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account)
    return {"fields": db.list_project_custom_fields(project_id)}


@router.post("/projects/{project_id}/custom-fields")
def create_custom_field(project_id: str, body: CustomFieldBody, account: Account = CurrentAccount) -> dict:
    _access(project_id, account, write=True)
    if body.field_type not in _FIELD_TYPES:
        raise HTTPException(400, "invalid custom field type")
    options = list(dict.fromkeys(str(value).strip()[:80] for value in body.options if str(value).strip()))
    if body.field_type == "select" and not options:
        raise HTTPException(400, "select custom field requires options")
    existing = db.list_project_custom_fields(project_id)
    if any(item["name"].casefold() == body.name.strip().casefold() for item in existing):
        raise HTTPException(409, "custom field name already exists")
    return db.create_project_custom_field(
        project_id=project_id, name=body.name.strip(), field_type=body.field_type,
        options=options if body.field_type == "select" else [], required=body.required,
    )


class CustomFieldUpdateBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    field_type: str | None = None
    options: list[str] | None = Field(default=None, max_length=50)
    required: bool | None = None


@router.patch("/projects/{project_id}/custom-fields/{field_id}")
def update_custom_field(project_id: str, field_id: str, body: CustomFieldUpdateBody,
                        account: Account = CurrentAccount) -> dict:
    _access(project_id, account, write=True)
    current = next((item for item in db.list_project_custom_fields(project_id) if item["id"] == field_id), None)
    if not current:
        raise HTTPException(404, "custom field not found")
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes:
        changes["name"] = str(changes["name"]).strip()
        if any(item["id"] != field_id and item["name"].casefold() == changes["name"].casefold()
               for item in db.list_project_custom_fields(project_id)):
            raise HTTPException(409, "custom field name already exists")
    next_type = str(changes.get("field_type", current["field_type"]))
    if next_type not in _FIELD_TYPES:
        raise HTTPException(400, "invalid custom field type")
    options = changes.get("options", current["options"])
    options = list(dict.fromkeys(str(value).strip()[:80] for value in options if str(value).strip()))
    if next_type == "select" and not options:
        raise HTTPException(400, "select custom field requires options")
    existing_values = [
        (item.get("custom_fields") or {}).get(field_id)
        for item in db.list_work_items(project_id)
        if field_id in (item.get("custom_fields") or {})
    ]
    if existing_values and next_type != current["field_type"]:
        raise HTTPException(409, "clear existing task values before changing field type")
    if next_type == "select" and any(value not in options for value in existing_values):
        raise HTTPException(409, "an option is still used by existing tasks")
    changes["options"] = options if next_type == "select" else []
    updated = db.update_project_custom_field(field_id, project_id, **changes)
    assert updated is not None
    return updated


@router.delete("/projects/{project_id}/custom-fields/{field_id}")
def delete_custom_field(project_id: str, field_id: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account, write=True)
    if not db.delete_project_custom_field(field_id, project_id):
        raise HTTPException(404, "custom field not found")
    return {"ok": True}


class PmTemplate(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    values: dict = Field(default_factory=dict)


class PmView(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    filters: dict = Field(default_factory=dict)


class PmPreferencesBody(BaseModel):
    templates: list[PmTemplate] | None = Field(default=None, max_length=30)
    wip: dict[str, int] | None = None
    views: list[PmView] | None = Field(default=None, max_length=30)


@router.get("/projects/{project_id}/pm-preferences")
def get_pm_preferences(project_id: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account)
    return db.get_project_pm_preferences(project_id, account.id)


@router.put("/projects/{project_id}/pm-preferences")
def update_pm_preferences(project_id: str, body: PmPreferencesBody,
                          account: Account = CurrentAccount) -> dict:
    role = _access(project_id, account, write=True)
    values = body.model_dump(exclude_unset=True)
    if len(json.dumps(values, ensure_ascii=False)) > 200_000:
        raise HTTPException(413, "PM preferences are too large")
    if "templates" in values:
        allowed_template_keys = {
            "description", "status", "source", "assignee", "priority", "due_date", "start_date",
            "labels", "parent_id", "milestone_id", "estimate_h", "spent_h", "custom_fields",
            "dependency_ids", "sprint_id",
        }
        template_ids = [item["id"] for item in values["templates"]]
        if len(template_ids) != len(set(template_ids)):
            raise HTTPException(400, "duplicate template id")
        for item in values["templates"]:
            if set(item["values"]) - allowed_template_keys:
                raise HTTPException(400, "unsupported task template field")
    if "views" in values:
        view_ids = [item["id"] for item in values["views"]]
        if len(view_ids) != len(set(view_ids)):
            raise HTTPException(400, "duplicate view id")
        for item in values["views"]:
            if set(item["filters"]) - {"group", "assignee", "source", "search"}:
                raise HTTPException(400, "unsupported saved view filter")
            if item["filters"].get("group") not in (None, "none", "assignee", "milestone"):
                raise HTTPException(400, "invalid saved view group")
    if "wip" in values:
        if not can_manage(role):
            raise HTTPException(403, "requires Admin/Owner to change WIP limits")
        if set(values["wip"]) - {"todo", "doing", "paused", "done"}:
            raise HTTPException(400, "invalid WIP status")
        if any(not isinstance(limit, int) or isinstance(limit, bool) or limit < 0 or limit > 100000
               for limit in values["wip"].values()):
            raise HTTPException(400, "WIP limit must be an integer between 0 and 100000")
    if "templates" in values:
        db.save_project_pm_shared(project_id, account.id, templates=values["templates"])
    if "wip" in values:
        db.save_project_pm_shared(project_id, account.id, wip=values["wip"])
    if "views" in values:
        db.save_project_pm_views(project_id, account.id, values["views"])
    return db.get_project_pm_preferences(project_id, account.id)


class SprintBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    goal: str = Field(default="", max_length=1000)
    start_date: str
    end_date: str
    status: str = "planned"


class SprintUpdateBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    goal: str | None = Field(default=None, max_length=1000)
    start_date: str | None = None
    end_date: str | None = None
    status: str | None = None


def _validate_sprint_dates(start: str, end: str) -> None:
    start_day, end_day = _iso_date(start, "sprint start_date"), _iso_date(end, "sprint end_date")
    if end_day < start_day or (end_day - start_day).days > 366:
        raise HTTPException(400, "sprint date range must be 0..366 days")


@router.get("/projects/{project_id}/sprints")
def list_sprints(project_id: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account)
    return {"sprints": db.list_sprints(project_id)}


@router.post("/projects/{project_id}/sprints")
def create_sprint(project_id: str, body: SprintBody, account: Account = CurrentAccount) -> dict:
    _access(project_id, account, write=True)
    _validate_sprint_dates(body.start_date, body.end_date)
    if body.status not in _SPRINT_STATUSES:
        raise HTTPException(400, "invalid sprint status")
    return db.create_sprint(project_id=project_id, name=body.name.strip(), goal=body.goal.strip(),
                            start_date=body.start_date, end_date=body.end_date, status=body.status)


@router.patch("/projects/{project_id}/sprints/{sprint_id}")
def update_sprint(project_id: str, sprint_id: str, body: SprintUpdateBody,
                  account: Account = CurrentAccount) -> dict:
    _access(project_id, account, write=True)
    current = db.get_sprint(sprint_id)
    if not current or current["project_id"] != project_id:
        raise HTTPException(404, "sprint not found")
    changes = body.model_dump(exclude_unset=True)
    start = str(changes.get("start_date", current["start_date"]))
    end = str(changes.get("end_date", current["end_date"]))
    _validate_sprint_dates(start, end)
    if "status" in changes and changes["status"] not in _SPRINT_STATUSES:
        raise HTTPException(400, "invalid sprint status")
    return db.update_sprint(sprint_id, **changes)  # type: ignore[return-value]


@router.delete("/projects/{project_id}/sprints/{sprint_id}")
def delete_sprint(project_id: str, sprint_id: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account, write=True)
    if not db.delete_sprint(sprint_id, project_id):
        raise HTTPException(404, "sprint not found")
    return {"ok": True}


@router.get("/projects/{project_id}/sprints/{sprint_id}/burndown")
def sprint_burndown(project_id: str, sprint_id: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account)
    sprint = db.get_sprint(sprint_id)
    if not sprint or sprint["project_id"] != project_id:
        raise HTTPException(404, "sprint not found")
    start, end = _iso_date(sprint["start_date"], "start_date"), _iso_date(sprint["end_date"], "end_date")
    tasks = [item for item in db.list_work_items(project_id) if item.get("sprint_id") == sprint_id]
    weights = {item["id"]: max(1.0, float(item.get("estimate_h") or 0)) for item in tasks}
    total = sum(weights.values())
    completion: dict[str, date] = {}
    for event in db.list_work_item_activity(project_id):
        if event.get("work_item_id") in weights and event.get("kind") == "status" and str(event.get("detail") or "").endswith("→done"):
            completion[event["work_item_id"]] = datetime.fromtimestamp(float(event["created_at"]), timezone.utc).date()
    for item in tasks:
        if item["status"] == "done" and item["id"] not in completion:
            completion[item["id"]] = datetime.fromtimestamp(float(item["updated_at"]), timezone.utc).date()
    days = (end - start).days + 1
    points = []
    for offset in range(days):
        current = start + timedelta(days=offset)
        actual = total - sum(weights[item_id] for item_id, finished in completion.items() if finished <= current)
        ideal = total * (days - 1 - offset) / max(1, days - 1)
        points.append({"date": current.isoformat(), "ideal_remaining": round(ideal, 2),
                       "actual_remaining": round(max(0.0, actual), 2)})
    return {"sprint": sprint, "total": total, "points": points}


@router.get("/projects/{project_id}/pm-export.csv")
def export_pm_csv(project_id: str, account: Account = CurrentAccount) -> Response:
    _access(project_id, account)
    fields = db.list_project_custom_fields(project_id)
    sprints = {item["id"]: item["name"] for item in db.list_sprints(project_id)}
    items = db.list_work_items(project_id)
    titles = {item["id"]: item["title"] for item in items}
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["id", "title", "status", "priority", "assignee", "start_date", "due_date",
                     "sprint", "dependencies", "estimate_h", "spent_h", *[field["name"] for field in fields]])
    for item in items:
        values = item.get("custom_fields") or {}
        writer.writerow([
            item["id"], item["title"], item["status"], item["priority"], item["assignee"],
            item["start_date"], item["due_date"], sprints.get(item.get("sprint_id", ""), ""),
            " | ".join(titles.get(dep, dep) for dep in item.get("dependency_ids", [])),
            item["estimate_h"], item["spent_h"], *[values.get(field["id"], "") for field in fields],
        ])
    return Response(content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="project-{project_id}-pm.csv"'})
