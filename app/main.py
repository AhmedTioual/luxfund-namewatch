"""LuxFund NameWatch - web dashboard.

    uvicorn app.main:app --reload       then open http://localhost:8000

Reads the DuckDB marts built by `python -m pipeline.run`. Read-only: rebuild the
warehouse with the pipeline, then refresh the page.
"""

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from app import data

BASE = Path(__file__).parent
app = FastAPI(
    title="LuxFund NameWatch",
    description="How Luxembourg funds renamed after the ESMA guidelines on ESG fund names. Public GLEIF data.",
    version="0.1.0",
)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


def _json_default(o):
    if isinstance(o, date | datetime):
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    raise TypeError(type(o))


def to_json(value) -> str:
    return json.dumps(value, default=_json_default)


def fmt_int(n) -> str:
    return f"{int(n or 0):,}".replace(",", " ")  # thin space, as in European finance


def fmt_date(d) -> str:
    if not d:
        return ""
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return d.strftime("%d %b %Y")


def script_json(value) -> Markup:
    """JSON safe to embed in a <script> block."""
    return Markup(to_json(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


def asset(path: str) -> str:
    """Static file URL with a version stamp, so browsers never reuse an old stylesheet or script."""
    f = BASE / "static" / path
    v = int(f.stat().st_mtime) if f.exists() else 0
    return f"/static/{path}?v={v}"


templates.env.filters.update(tojson_safe=script_json, int=fmt_int, date=fmt_date)
templates.env.globals.update(
    asset=asset,
    sparkline=data.sparkline,
    now=datetime.now,
    CATEGORY_LABELS=data.CATEGORY_LABELS,
    CATEGORY_SHORT=data.CATEGORY_SHORT,
    PHASES=data.PHASES,
)


def shell_info() -> dict:
    """Data for the app frame: last load time and the number of renames to review."""
    try:
        with data.connect() as con:
            ts = con.execute("select max(loaded_at) from raw.load_log").fetchone()[0]
            to_review = data.review_queue(con, limit=0)[0]
        return {"fresh": ts.strftime("%d %b, %H:%M UTC") if ts else None, "to_review": to_review}
    except Exception:
        return {"fresh": None, "to_review": 0}


def page(request: Request, name: str, active: str, **ctx) -> HTMLResponse:
    response = templates.TemplateResponse(request, name, {"active": active, **shell_info(), **ctx})
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(data.WarehouseMissing)
async def no_warehouse(request: Request, exc: data.WarehouseMissing):
    if request.url.path.startswith("/api"):
        return JSONResponse({"detail": "Warehouse not built. Run: python -m pipeline.run"}, status_code=503)
    return templates.TemplateResponse(request, "empty.html", {"active": "", "path": str(exc)}, status_code=503)


# --------------------------------------------------------------------------- pages
@app.get("/", response_class=HTMLResponse)
def overview(request: Request):
    with data.connect() as con:
        k = data.kpis(con)
        ctx = {
            "k": k,
            "featured": data.featured_rename(con),
            "quarters": data.quarters(con),
            "share": data.esg_share(con),
            "flows": data.flows(con),
            "milestones": data.milestones(con),
            "words": data.replacement_words(con)[:10],
            "dropped": data.dropped_terms(con)[:10],
            "cats": data.category_counts(con),
            "latest": data.renames(con, limit=6)[1],
            "managers": data.manager_trends(con),
        }
        ctx["review_total"], ctx["review"] = data.review_queue(con, limit=20)
        ctx["tests"] = data.dbt_tests()
        f = ctx["featured"]
        ctx["featured_diff"] = (
            data.name_diff(f["old_name"], f["new_name"], f["esg_terms_dropped"], f["vague_terms_added"]) if f else ""
        )
    return page(request, "overview.html", "overview", **ctx)


@app.get("/insights", response_class=HTMLResponse)
def insights(request: Request):
    with data.connect() as con:
        ctx = {
            "k": data.kpis(con),
            "flows": data.flows(con),
            "share": data.esg_share(con),
            "words": data.replacement_words(con)[:10],
            "dropped": data.dropped_terms(con)[:10],
            "milestones": data.milestones(con),
        }
    return page(request, "insights.html", "insights", **ctx)


@app.get("/renames", response_class=HTMLResponse)
def renames_page(
    request: Request,
    category: str = "",
    phase: str = "",
    q: str = "",
    prefix: str = "",
    manager: str = "",
    review: str = "",
    scope: str = "esg",
    page_no: int = 1,
):
    size = 40
    page_no = max(1, page_no)
    with data.connect() as con:
        total, items = data.renames(
            con, category=category or None, phase=phase or None, q=q.strip() or None, prefix=prefix or None,
            manager=manager or None, review=bool(review), esg_only=scope != "all",
            limit=size, offset=(page_no - 1) * size,
        )  # fmt: skip
        k = data.kpis(con)
        manager_label = data.manager_name(con, manager) if manager else None
    filters = {
        "category": category,
        "phase": phase,
        "q": q,
        "prefix": prefix,
        "manager": manager,
        "review": review,
        "scope": scope,
    }
    return page(
        request, "renames.html", "renames", items=items, total=total, page_no=page_no, pages=max(1, -(-total // size)),
        filters=filters, k=k, manager_label=manager_label,
    )  # fmt: skip


@app.get("/funds", response_class=HTMLResponse)
def funds_search(request: Request, q: str = ""):
    with data.connect() as con:
        results = data.search_funds(con, q.strip()) if q.strip() else []
    return page(request, "funds.html", "funds", q=q, results=results)


@app.get("/funds/{lei}", response_class=HTMLResponse)
def fund_page(request: Request, lei: str):
    with data.connect() as con:
        f = data.fund(con, lei)
    if f is None:
        raise HTTPException(404, "Fund not found")
    return page(request, "fund.html", "funds", f=f)


@app.get("/houses", response_class=HTMLResponse)
def houses(request: Request, by: str = ""):
    with data.connect() as con:
        k = data.kpis(con)
        if not by:
            by = "manager" if k.get("funds_with_manager") else "prefix"
        items = data.managers(con) if by == "manager" else data.prefixes(con)
    return page(request, "houses.html", "houses", items=items, k=k, by=by)


@app.get("/method", response_class=HTMLResponse)
def method(request: Request):
    with data.connect() as con:
        ctx = {"k": data.kpis(con), "log": data.load_log(con), "cats": data.category_counts(con, since_esma=False)}
    return page(request, "method.html", "method", tests=data.dbt_tests(), ev=data.eval_report(), **ctx)


# --------------------------------------------------------------------------- JSON API
@app.get("/api/kpis")
def api_kpis():
    with data.connect() as con:
        return JSONResponse(json.loads(to_json(data.kpis(con))))


@app.get("/api/renames")
def api_renames(category: str = "", q: str = "", limit: int = 100, offset: int = 0):
    with data.connect() as con:
        total, items = data.renames(con, category=category or None, q=q or None, limit=min(limit, 500), offset=offset)
    for i in items:
        i.pop("diff", None)
    return JSONResponse(json.loads(to_json({"total": total, "items": items})))


@app.get("/api/funds/{lei}")
def api_fund(lei: str):
    with data.connect() as con:
        f = data.fund(con, lei)
    if f is None:
        raise HTTPException(404, "Fund not found")
    for c in f["changes"]:
        c.pop("diff", None)
    return JSONResponse(json.loads(to_json(f)))


@app.get("/health")
def health():
    return {"status": "ok", "warehouse": data.WAREHOUSE.exists()}
