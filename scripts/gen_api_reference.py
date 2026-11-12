#!/usr/bin/env python3
"""Regenerate docs/API_REFERENCE.md from the FastAPI app. Run from backend/: ../scripts/gen_api_reference.py > ../docs/API_REFERENCE.md (use the backend venv)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
from fastapi.routing import APIRoute
from app.main import app
from app.core import deps
LEVEL = {id(deps.require_customer): "customer", id(deps.require_staff): "staff", id(deps.require_manager): "manager", id(deps.require_admin): "admin", id(deps.get_principal): "signed-in user"}
def access(dep):
    found = []
    for d in dep.dependencies:
        if id(d.call) in LEVEL: found.append(LEVEL[id(d.call)])
        found += access(d)
    return found
def walk(routes):
    for r in routes:
        if isinstance(r, APIRoute): yield r
        elif hasattr(r, "original_router"): yield from walk(r.original_router.routes)
print("# API reference\n")
print("Generated from the running FastAPI app (interactive docs at `http://localhost:8000/docs`, schema at `/openapi.json`). Regenerate with `cd backend && .venv/bin/python ../scripts/gen_api_reference.py > ../docs/API_REFERENCE.md`.\n")
print("- Auth: `Authorization: Bearer <access token>` from `POST /api/auth/login` (refresh with `POST /api/auth/refresh`).")
print("- Tenant isolation: every staff route is scoped to the caller's business; customers only see their own records.")
print("- Errors: `{\"error\": {\"code\": str, \"message\": str, \"details\": any}}` with a matching HTTP status.")
print("- Access levels: **customer**; **staff** = support agent, manager or admin; **manager** = manager or admin; **admin**; **public**.\n")
groups = {}
for r in walk(app.routes):
    tag = (r.tags or ["system"])[0]
    lv = access(r.dependant)
    lv = [x for x in lv if x != "signed-in user"] or lv
    a = lv[0] if lv else ("public, PayPal signature verified" if "webhook" in r.path else "public")
    doc = " ".join((r.description or "").strip().split("\n")[0:1])
    for m in sorted(r.methods - {"HEAD"}):
        groups.setdefault(tag, []).append((r.path, m, a, doc.replace("|", "\\|")))
for tag, rows in groups.items():
    print(f"## {tag}\n")
    print("| Method | Path | Access | Notes |")
    print("| --- | --- | --- | --- |")
    for path, m, a, doc in sorted(rows):
        print(f"| {m} | `{path}` | {a} | {doc} |")
    print()
