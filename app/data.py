"""Read-only queries on the DuckDB marts used by the web app."""

import difflib
import json
import re
from contextlib import contextmanager

import duckdb
from markupsafe import Markup, escape

from pipeline.config import EVAL_FILE, WAREHOUSE

CATEGORY_LABELS = {
    "esg_to_vague": "ESG term replaced by a vaguer word",
    "esg_removed": "ESG term removed",
    "esg_reworded": "ESG claim reworded",
    "esg_added": "ESG term added",
    "not_esg": "Keyword, but not an ESG claim",
    "other_rename": "Other rename",
}
CATEGORY_SHORT = {
    "esg_to_vague": "Replaced by vaguer word",
    "esg_removed": "ESG term removed",
    "esg_reworded": "Reworded",
    "esg_added": "ESG term added",
    "not_esg": "Not an ESG claim",
    "other_rename": "Other rename",
}
PHASES = ["1. Before ESMA guidelines", "2. Transition period", "3. After the deadline"]


class WarehouseMissing(RuntimeError):
    pass


@contextmanager
def connect():
    if not WAREHOUSE.exists():
        raise WarehouseMissing(str(WAREHOUSE))
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    try:
        yield con
    finally:
        con.close()


def rows(con, sql: str, params=None) -> list[dict]:
    cur = con.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def one(con, sql: str, params=None) -> dict:
    r = rows(con, sql, params)
    return r[0] if r else {}


# --------------------------------------------------------------------------- name diff (the "redline")
_TOKEN = re.compile(r"\S+")


def _norm(tok: str) -> str:
    return re.sub(r"[^a-z0-9]", "", tok.lower())


def name_diff(old: str, new: str, esg_terms=(), vague_terms=()) -> Markup:
    """Word-level diff of two legal names: removed words struck through, added words underlined.
    Words that are ESG or vague terms get a stronger colour."""
    a, b = _TOKEN.findall(old or ""), _TOKEN.findall(new or "")
    sm = difflib.SequenceMatcher(None, [_norm(t) for t in a], [_norm(t) for t in b], autojunk=False)
    esg_words = {w for t in esg_terms for w in t.split()}
    vague_words = {w for t in vague_terms for w in t.split()}

    def kind(tok: str, words: set) -> str:
        n = _norm(tok)
        return " key" if any(n.startswith(w.replace(" ", "")[:5]) for w in words if w) else ""

    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out.append(escape(" ".join(b[j1:j2])))
            continue
        if op in ("delete", "replace"):
            out.append(
                Markup(" ").join(Markup(f'<del class="rl-del{kind(t, esg_words)}">{escape(t)}</del>') for t in a[i1:i2])
            )
        if op in ("insert", "replace"):
            out.append(
                Markup(" ").join(
                    Markup(f'<ins class="rl-ins{kind(t, vague_words)}">{escape(t)}</ins>') for t in b[j1:j2]
                )
            )
    return Markup(" ").join(out)


# --------------------------------------------------------------------------- queries
def kpis(con) -> dict:
    k = one(con, "select * from marts.mart_kpis")
    k["quality"] = one(con, "select * from marts.mart_data_quality")
    return k


def quarters(con) -> list[dict]:
    return rows(
        con,
        """select quarter, quarter_start, renames, esg_removed, esg_to_vague, esg_reworded, esg_added, other_rename
           from marts.agg_renames_by_quarter where quarter_start >= date '2018-01-01' order by quarter_start""",
    )


def esg_share(con) -> list[dict]:
    return rows(
        con,
        """select quarter, quarter_end, funds, funds_with_esg_name, funds_with_vague_name, esg_name_share
           from marts.agg_esg_names_by_quarter where quarter_end >= date '2018-01-01' order by quarter_end""",
    )


def flows(con, limit: int = 40) -> list[dict]:
    return rows(con, "select * from marts.agg_term_flows order by renames desc limit ?", [limit])


def milestones(con) -> list[dict]:
    return rows(con, "select milestone_date, label, detail from reference.esma_milestones order by milestone_date")


def replacement_words(con) -> list[dict]:
    return rows(
        con,
        """select replacement as word, sum(renames) as renames from marts.agg_term_flows
           where replacement_kind = 'vague word' group by 1 order by 2 desc""",
    )


def dropped_terms(con) -> list[dict]:
    return rows(
        con,
        "select dropped_term as term, sum(renames) as renames from marts.agg_term_flows group by 1 order by 2 desc",
    )


def renames(
    con,
    *,
    category=None,
    phase=None,
    q=None,
    prefix=None,
    manager=None,
    review=False,
    esg_only=True,
    limit=50,
    offset=0,
):
    where, params = ["1=1"], []
    if esg_only:
        where.append("is_esg_rename")
    if category:
        where.append("category = ?")
        params.append(category)
    if phase:
        where.append("esma_phase = ?")
        params.append(phase)
    if prefix:
        where.append("name_prefix = ?")
        params.append(prefix)
    if manager:
        where.append("coalesce(manager_lei, 'name:' || manager_name) = ?")
        params.append(manager)
    if review:
        where.append(REVIEW_CLAUSE)
    if q:
        where.append("(old_name ilike ? or new_name ilike ? or lei ilike ?)")
        params += [f"%{q}%"] * 3
    clause = " and ".join(where)
    total = con.execute(f"select count(*) from marts.fct_renames where {clause}", params).fetchone()[0]
    items = rows(
        con,
        f"""select change_id, lei, change_date, old_name, new_name, category, category_source, ai_rationale,
                   ai_confidence, esg_terms_dropped, vague_terms_added, esg_terms_added, entity_status, name_prefix,
                   esma_phase, manager_name
            from marts.fct_renames where {clause}
            order by change_date desc, old_name limit ? offset ?""",
        params + [limit, offset],
    )
    for r in items:
        r["diff"] = name_diff(r["old_name"], r["new_name"], r["esg_terms_dropped"], r["vague_terms_added"])
    return total, items


def category_counts(con, since_esma=True) -> dict:
    sql = "select category, count(*) n from marts.fct_renames where is_esg_rename"
    if since_esma:
        sql += " and change_date >= (select esma_publication_date from marts.mart_kpis)"
    return {r["category"]: r["n"] for r in rows(con, sql + " group by 1")}


def managers(con) -> list[dict]:
    return rows(con, "select * from marts.agg_fund_managers order by dropped_esg_since_esma desc, funds desc")


def manager_name(con, key: str) -> str | None:
    r = one(con, "select manager_name from marts.agg_fund_managers where manager_key = ?", [key])
    return r.get("manager_name")


def prefixes(con) -> list[dict]:
    return rows(con, "select * from marts.agg_name_prefixes order by dropped_esg_since_esma desc, funds desc")


def fund(con, lei: str) -> dict | None:
    f = one(con, "select * from marts.dim_fund where lei = ?", [lei.upper()])
    if not f:
        return None
    f["history"] = rows(
        con,
        """select name, valid_from, valid_to, is_current, has_esg_term, has_vague_term, esg_terms, vague_terms
           from intermediate.int_name_history where lei = ? order by valid_from, valid_to nulls last""",
        [lei.upper()],
    )
    f["changes"] = rows(
        con,
        """select change_date, old_name, new_name, category, category_source, ai_rationale, esg_terms_dropped,
                  vague_terms_added
           from marts.fct_renames where lei = ? order by change_date""",
        [lei.upper()],
    )
    for c in f["changes"]:
        c["diff"] = name_diff(c["old_name"], c["new_name"], c["esg_terms_dropped"], c["vague_terms_added"])
    return f


def featured_rename(con) -> dict | None:
    """The clearest recent example for the hero: an ESG term replaced by a vague word."""
    r = one(
        con,
        """select old_name, new_name, change_date, esg_terms_dropped, vague_terms_added, lei
           from marts.fct_renames
           where category = 'esg_to_vague' and length(new_name) < 60
           order by change_date desc limit 1""",
    )
    return r or None


def search_funds(con, q: str, limit: int = 20) -> list[dict]:
    return rows(
        con,
        """select lei, legal_name, entity_status, real_renames from marts.dim_fund
           where legal_name ilike ? or earliest_known_name ilike ? or lei ilike ?
           order by real_renames desc, legal_name limit ?""",
        [f"%{q}%", f"%{q}%", f"%{q}%", limit],
    )


def eval_report() -> dict | None:
    if EVAL_FILE.exists():
        return json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    return None


def load_log(con) -> list[dict]:
    return rows(
        con,
        """select table_name, source_file, row_count, sha256, loaded_at from raw.load_log
           qualify row_number() over (partition by table_name order by loaded_at desc) = 1 order by table_name""",
    )


def dbt_tests() -> dict:
    """Read dbt's run_results.json to show the data tests on the method page."""
    from pipeline.config import DBT_DIR

    path = DBT_DIR / "target" / "run_results.json"
    if not path.exists():
        return {"total": 0}
    res = json.loads(path.read_text(encoding="utf-8"))
    tests = [r for r in res.get("results", []) if r.get("unique_id", "").startswith("test.")]
    return {
        "total": len(tests),
        "passed": sum(r["status"] == "pass" for r in tests),
        "warned": sum(r["status"] == "warn" for r in tests),
        "failed": sum(r["status"] in ("fail", "error") for r in tests),
        "generated_at": res.get("metadata", {}).get("generated_at", "")[:19].replace("T", " "),
        "models": sum(r.get("unique_id", "").startswith("model.") for r in res.get("results", [])),
    }


# --------------------------------------------------------------------------- overview widgets
AMBIGUOUS_TERMS = ("transition", "social", "impact", "governance", "responsible", "ethical")
REVIEW_CLAUSE = f"""is_esg_rename and (
    (category_source = 'llm' and ai_confidence < 0.75)
    or (category_source = 'rules' and list_has_any(coalesce(esg_terms_dropped, []) || coalesce(esg_terms_added, []),
                                                   {list(AMBIGUOUS_TERMS)}::varchar[])))"""


def review_queue(con, limit: int = 4) -> tuple[int, list[dict]]:
    """ESG renames a person should look at: classified by keyword rules only on an ambiguous term,
    or classified by the AI with low confidence."""
    clause = REVIEW_CLAUSE
    total = con.execute(f"select count(*) from marts.fct_renames where {clause}").fetchone()[0]
    items = rows(
        con,
        f"""select lei, change_date, old_name, new_name, category, category_source, ai_confidence, ai_rationale,
                   esg_terms_dropped, esg_terms_added, vague_terms_added, manager_name
            from marts.fct_renames where {clause} order by change_date desc limit ?""",
        [limit],
    )
    for r in items:
        r["diff"] = name_diff(r["old_name"], r["new_name"], r["esg_terms_dropped"], r["vague_terms_added"])
        terms = (r["esg_terms_dropped"] or []) + (r["esg_terms_added"] or [])
        r["ambiguous"] = [t for t in terms if t in AMBIGUOUS_TERMS]
    return total, items


def manager_trends(con, limit: int = 6) -> list[dict]:
    """Top management companies with a quarterly series of ESG renames since 2024 (for sparklines)."""
    top = rows(
        con,
        """select manager_key, manager_name, manager_lei, funds, dropped_esg_since_esma, esg_named_now
           from marts.agg_fund_managers order by dropped_esg_since_esma desc, funds desc limit ?""",
        [limit],
    )
    if not top:
        return []
    quarters = [
        r[0]
        for r in con.execute(
            "select quarter from marts.agg_renames_by_quarter where quarter_start >= date '2024-01-01' order by 1"
        ).fetchall()
    ]
    counts = rows(
        con,
        """select coalesce(manager_lei, 'name:' || manager_name) as k, change_quarter as q, count(*) as n
           from marts.fct_renames where is_esg_rename and change_date >= date '2024-01-01' group by 1, 2""",
    )
    by = {(c["k"], c["q"]): c["n"] for c in counts}
    for t in top:
        t["series"] = [by.get((t["manager_key"], q), 0) for q in quarters]
        t["share"] = round(100 * t["dropped_esg_since_esma"] / t["funds"], 1) if t["funds"] else 0
    return top


def sparkline(values, width: int = 72, height: int = 22, pad: int = 2) -> str:
    """SVG polyline points for a small trend line."""
    vals = [float(v or 0) for v in values] or [0.0]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    step = (width - 2 * pad) / max(len(vals) - 1, 1)
    return " ".join(
        f"{pad + i * step:.1f},{height - pad - (v - lo) / span * (height - 2 * pad):.1f}" for i, v in enumerate(vals)
    )
