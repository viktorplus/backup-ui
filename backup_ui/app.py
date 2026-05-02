from __future__ import annotations

import argparse
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import state
from .backup_runner import start_backup_job
from .db_browser import discover_database_containers, list_tables
from .discovery import discover_all
from .profiles import current_server_profile
from .restore_runner import start_restore_job
from .retention import apply_retention, plan_retention
from .server_status import directory_listing, list_processes, server_overview
from .settings import DEFAULT_BACKUP_ROOT, ensure_dirs


BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

app = FastAPI(title="Backup UI")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


@app.on_event("startup")
def startup() -> None:
    ensure_dirs()
    state.init_db()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    plans = state.list_plans()
    jobs = state.list_jobs()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"plans": plans, "jobs": jobs},
    )


@app.get("/discovery", response_class=HTMLResponse)
def discovery(request: Request) -> HTMLResponse:
    data = discover_all()
    return templates.TemplateResponse(request, "discovery.html", {"data": data})


@app.get("/server", response_class=HTMLResponse)
def server_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "server.html", {"server": server_overview()})


@app.get("/server/processes", response_class=HTMLResponse)
def processes_page(request: Request, limit: int = 200) -> HTMLResponse:
    safe_limit = min(max(limit, 20), 1000)
    return templates.TemplateResponse(
        request,
        "processes.html",
        {"processes": list_processes(limit=safe_limit), "limit": safe_limit},
    )


@app.get("/server/files", response_class=HTMLResponse)
def files_page(request: Request, path: str = "/") -> HTMLResponse:
    return templates.TemplateResponse(request, "files.html", {"listing": directory_listing(path)})


@app.get("/databases", response_class=HTMLResponse)
def databases_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "databases.html",
        {"containers": discover_database_containers()},
    )


@app.get("/databases/{container}/{engine}/{database}", response_class=HTMLResponse)
def database_detail_old(request: Request, container: str, engine: str, database: str) -> RedirectResponse:
    return RedirectResponse(f"/databases/detail?container={container}&engine={engine}&database={database}", status_code=303)


@app.get("/databases/detail", response_class=HTMLResponse)
def database_detail(request: Request, container: str, engine: str, database: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "database_detail.html",
        {
            "container": container,
            "engine": engine,
            "database": database,
            "tables": list_tables(container, engine, database),
        },
    )


@app.get("/profiles/current", response_class=HTMLResponse)
def current_profile_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "profile.html",
        {"profile": current_server_profile(), "saved_profiles": state.list_server_profiles()},
    )


@app.post("/profiles/current/save")
def save_current_profile() -> RedirectResponse:
    state.save_server_profile(current_server_profile())
    return RedirectResponse("/profiles/current", status_code=303)


@app.get("/plans", response_class=HTMLResponse)
def plans(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "plans.html", {"plans": state.list_plans()})


@app.get("/plans/new", response_class=HTMLResponse)
def new_plan(request: Request) -> HTMLResponse:
    data = discover_all()
    return templates.TemplateResponse(
        request,
        "plan_form.html",
        {
            "plan": None,
            "data": data,
            "default_root": str(DEFAULT_BACKUP_ROOT),
        },
    )


@app.post("/plans", response_class=HTMLResponse)
async def create_plan(request: Request) -> RedirectResponse:
    form = await request.form()
    plan = _plan_from_form(form)
    state.save_plan(plan)
    return RedirectResponse("/plans", status_code=303)


@app.get("/plans/{plan_id}/edit", response_class=HTMLResponse)
def edit_plan(request: Request, plan_id: int) -> HTMLResponse:
    plan = state.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, "План не найден")
    data = discover_all()
    return templates.TemplateResponse(
        request,
        "plan_form.html",
        {"plan": plan, "data": data, "default_root": plan["backup_root"]},
    )


@app.post("/plans/{plan_id}", response_class=HTMLResponse)
async def update_plan(request: Request, plan_id: int) -> RedirectResponse:
    form = await request.form()
    plan = _plan_from_form(form)
    plan["id"] = plan_id
    state.save_plan(plan)
    return RedirectResponse("/plans", status_code=303)


@app.post("/plans/{plan_id}/delete")
def delete_plan(plan_id: int) -> RedirectResponse:
    state.delete_plan(plan_id)
    return RedirectResponse("/plans", status_code=303)


@app.post("/plans/{plan_id}/run")
def run_plan(plan_id: int) -> RedirectResponse:
    plan = state.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, "План не найден")
    job_id = start_backup_job(plan)
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(request: Request, job_id: int) -> HTMLResponse:
    job = state.get_job(job_id)
    if not job:
        raise HTTPException(404, "Задание не найдено")
    logs = state.get_job_logs(job_id)
    return templates.TemplateResponse(request, "job.html", {"job": job, "logs": logs})


@app.get("/backups", response_class=HTMLResponse)
def backups(request: Request) -> HTMLResponse:
    plans = state.list_plans()
    selected_root = plans[0]["backup_root"] if plans else str(DEFAULT_BACKUP_ROOT)
    snapshots = state.snapshot_dirs(selected_root)
    return templates.TemplateResponse(
        request,
        "backups.html",
        {"plans": plans, "selected_root": selected_root, "snapshots": snapshots},
    )


@app.get("/restore", response_class=HTMLResponse)
def restore_page(request: Request, root: str | None = None) -> HTMLResponse:
    plans = state.list_plans()
    selected_root = root or (plans[0]["backup_root"] if plans else str(DEFAULT_BACKUP_ROOT))
    snapshots = state.snapshot_dirs(selected_root)
    return templates.TemplateResponse(
        request,
        "restore.html",
        {"plans": plans, "selected_root": selected_root, "snapshots": snapshots},
    )


@app.post("/restore")
def restore_run(
    snapshot: Annotated[str, Form()],
    component: Annotated[str, Form()],
    mode: Annotated[str, Form()],
    target: Annotated[str, Form()],
    confirmation: Annotated[str, Form()],
) -> RedirectResponse:
    job_id = start_restore_job(snapshot, component, mode, target, confirmation)
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.get("/retention", response_class=HTMLResponse)
def retention_page(request: Request) -> HTMLResponse:
    plans = state.list_plans()
    return templates.TemplateResponse(request, "retention.html", {"plans": plans, "result": None})


@app.post("/retention", response_class=HTMLResponse)
def retention_apply(
    request: Request,
    root: Annotated[str, Form()],
    keep_last: Annotated[int, Form()] = 0,
    max_total_gb: Annotated[float, Form()] = 0,
    dry_run: Annotated[str | None, Form()] = "on",
) -> HTMLResponse:
    rules = {"keep_last": keep_last, "max_total_gb": max_total_gb}
    result = apply_retention(root, rules, dry_run=dry_run == "on")
    return templates.TemplateResponse(
        request,
        "retention.html",
        {"plans": state.list_plans(), "result": result, "root": root, "dry_run": dry_run == "on"},
    )


def _plan_from_form(form) -> dict:
    projects = []
    configs = []
    databases = []

    project_names = form.getlist("project_name")
    project_paths = form.getlist("project_path")
    project_enabled = set(form.getlist("project_enabled"))
    for idx, name in enumerate(project_names):
        if str(idx) in project_enabled:
            projects.append({"name": name, "path": project_paths[idx]})

    config_names = form.getlist("config_name")
    config_paths = form.getlist("config_path")
    config_enabled = set(form.getlist("config_enabled"))
    for idx, name in enumerate(config_names):
        if str(idx) in config_enabled:
            configs.append({"name": name, "path": config_paths[idx]})

    db_names = form.getlist("db_name")
    db_containers = form.getlist("db_container")
    db_enabled = set(form.getlist("db_enabled"))
    db_skip = set(form.getlist("db_skip"))
    for idx, name in enumerate(db_names):
        if str(idx) in db_enabled:
            databases.append(
                {
                    "name": name,
                    "container": db_containers[idx],
                    "user": form.get("postgres_user") or "signal",
                    "skip": str(idx) in db_skip,
                }
            )

    storage = []
    if form.get("storage_local_enabled"):
        storage.append({"type": "local", "path": form.get("storage_local_path")})
    if form.get("storage_ssh_enabled"):
        storage.append(
            {
                "type": "ssh",
                "remote": form.get("storage_ssh_remote"),
                "path": form.get("storage_ssh_path"),
            }
        )

    return {
        "name": form.get("name") or "Новый план",
        "enabled": bool(form.get("enabled")),
        "schedule": form.get("schedule") or "",
        "backup_root": form.get("backup_root") or str(DEFAULT_BACKUP_ROOT),
        "storage": storage,
        "include": {"projects": projects, "configs": configs, "databases": databases},
        "retention": {
            "keep_last": int(form.get("keep_last") or 0),
            "max_total_gb": float(form.get("max_total_gb") or 0),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8090, type=int)
    args = parser.parse_args()
    uvicorn.run("backup_ui.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
