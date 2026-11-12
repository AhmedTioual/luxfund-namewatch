"""LuxFund NameWatch - step 0: is there enough REAL rename data in GLEIF?

What it does (public GLEIF API, no key, standard library only):
  1. Downloads GLEIF's free Golden Copy file once and keeps every Luxembourg FUND
     (the search API stops at 10,000 results; there are about 40,000 LU funds).
  2. Finds funds that have a recorded previous legal name.
  3. Calls each candidate's change history (/lei-records/{lei}/field-modifications)
     to get the DATE of each legal-name change, old name -> new name.
  4. Prints a summary (renames per quarter, ESG terms dropped/added, new words used)
     and writes CSV files you can open in Excel or Power BI.

Usage:
    python check_gleif_renames.py                 # full run (list + history of candidates)
    python check_gleif_renames.py --max-history 300   # quicker first look
    python gleif_extract.py --relationships      # fund managers, umbrellas and master funds
    python check_gleif_renames.py --sample 200    # also check 200 random funds without a
                                                  # recorded previous name (coverage test)

Output (folder ./gleif_check/):
    lu_funds.csv     all Luxembourg funds found
    renames.csv      dated legal-name changes
    history_checked.csv  the funds whose change history was checked
    summary.txt      the numbers printed at the end
    golden_copy_lei2.csv.zip   GLEIF full file, kept so re-runs skip the download
    fund_relationships.csv, related_entities.csv   with --relationships: managers, umbrellas, master funds
    cache/           raw API answers, so a re-run resumes instead of downloading again

Python 3.9+. Respects GLEIF's rate limit (about 60 requests per minute); a full
run can take a while for the history step, and it can be stopped and resumed.
"""

import argparse
import csv
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

API = "https://api.gleif.org/api/v1"
OUT = Path("gleif_check")  # output folder; copy lu_funds.csv, renames.csv, history_checked.csv to data/raw/
CACHE = OUT / "cache"
HEADERS = {"Accept": "application/vnd.api+json", "User-Agent": "luxfund-namewatch/0.1 (portfolio project)"}
MIN_INTERVAL = 1.05  # seconds between calls -> stays under 60 requests/minute

# ESMA guidelines on fund names: terms that trigger the rules
ESG_TERMS = {
    "esg": r"\besg\b",
    "sustainable": r"\bsustainab\w*|\bdurable\b|\bnachhaltig\w*",
    "impact": r"\bimpact\b",
    "environmental": r"\benvironment\w*|\bgreen\b|\bclimate\b|\bclimat\w*|\bvert\b|\bnet[- ]?zero\b|\blow[- ]carbon\b|\bdecarboni\w*|\bparis[- ]aligned\b",
    "social": r"\bsocial\w*|\bsolidar\w*",
    "governance": r"\bgovernance\b",
    "transition": r"\btransition\w*",
    "sri/responsible": r"\bsri\b|\bisr\b|\bresponsib\w*|\bethic\w*",
}
# Words that replaced ESG terms after the guidelines (several listed in ESMA's Jan 2026 study)
VAGUE_TERMS = {
    "screened": r"\bscreen\w*",
    "select": r"\bselect\w*",
    "enhanced": r"\benhanced\b",
    "conscious/aware": r"\bconscious\b|\baware\b",
    "future/tomorrow": r"\bfuture\b|\btomorrow\b",
    "leaders/best-in-class": r"\bleaders?\b|\bbest[- ]in[- ]class\b",
    "quality": r"\bquality\b",
    "exclusion": r"\bexclu\w*",
}

_last_call = 0.0


def get(url: str, cache_key: str | None = None, retries: int = 5) -> dict:
    """GET a GLEIF API URL with caching, throttling and retries."""
    global _last_call
    if cache_key:
        path = CACHE / f"{cache_key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    for attempt in range(retries):
        wait = MIN_INTERVAL - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if cache_key:
                CACHE.mkdir(parents=True, exist_ok=True)
                (CACHE / f"{cache_key}.json").write_text(json.dumps(data), encoding="utf-8")
            return data
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {"data": []}
            if exc.code == 400:
                print(f"  HTTP 400 for {url}", file=sys.stderr)
                return {"data": []}
            if exc.code == 429 or exc.code >= 500:
                pause = 10 * (attempt + 1)
                print(f"  HTTP {exc.code}, pausing {pause}s...", file=sys.stderr)
                time.sleep(pause)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            pause = 5 * (attempt + 1)
            print(f"  network error ({exc}), retrying in {pause}s...", file=sys.stderr)
            time.sleep(pause)
    raise RuntimeError(f"Giving up on {url}")


def terms_in(name: str, vocab: dict) -> set[str]:
    low = (name or "").lower()
    return {label for label, rx in vocab.items() if re.search(rx, low)}


# --------------------------------------------------------------------------- step 1
GOLDEN_INDEX = "https://goldencopy.gleif.org/api/v2/golden-copies/publishes/latest"
GOLDEN_SHORTCUT = "https://goldencopy.gleif.org/api/v2/golden-copies/publishes/lei2/latest.csv"


def _find_csv_url(node, kind: str = "lei2") -> str | None:
    """Search the Golden Copy index JSON for the full CSV file URL of one dataset (lei2, rr...)."""
    if isinstance(node, dict):
        ds = node.get(kind)
        if isinstance(ds, dict):
            url = ((ds.get("full_file") or {}).get("csv") or {}).get("url")
            if url:
                return url
        for v in node.values():
            found = _find_csv_url(v, kind)
            if found:
                return found
    elif isinstance(node, list):
        for v in node:
            found = _find_csv_url(v, kind)
            if found:
                return found
    return None


def download_golden_copy(kind: str = "lei2") -> Path:
    """Download one GLEIF Golden Copy file once (zipped CSV) and keep it for re-runs.
    kind = "lei2" (all LEI records, several hundred MB) or "rr" (relationship records, smaller)."""
    target = OUT / f"golden_copy_{kind}.csv.zip"
    if target.exists() and target.stat().st_size > 1_000_000:
        print(f"Using the Golden Copy already downloaded: {target}")
        return target
    url = None
    try:
        url = _find_csv_url(get(GOLDEN_INDEX), kind)
    except Exception as exc:  # index format changed or unreachable: use the documented shortcut
        print(f"  Golden Copy index not usable ({exc}), using the shortcut URL")
    url = url or GOLDEN_SHORTCUT.replace("/lei2/", f"/{kind}/")
    print(f"Downloading GLEIF Golden Copy ({kind})...\n  {url}")
    tmp = target.with_suffix(".part")
    req = urllib.request.Request(url, headers={"User-Agent": HEADERS["User-Agent"]})
    with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as fh:
        size = int(resp.headers.get("Content-Length") or 0)
        done, last = 0, 0
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
            done += len(chunk)
            if done - last > 50 << 20:
                last = done
                print(f"  {done >> 20} MB" + (f" / {size >> 20} MB" if size else ""))
    tmp.replace(target)
    return target


def _zip_csv_rows(path: Path):
    """Yield (header_index, row) for the CSV inside a Golden Copy zip."""
    import io
    import zipfile

    csv.field_size_limit(10_000_000)
    with zipfile.ZipFile(path) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        with zf.open(name) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
            header = next(reader)
            idx = {h: i for i, h in enumerate(header)}
            for row in reader:
                yield idx, row


def _col(idx: dict, *suffixes: str) -> int | None:
    """Find a column by exact name or by suffix (GLEIF column names are long dotted paths)."""
    for s in suffixes:
        if s in idx:
            return idx[s]
    for s in suffixes:
        for name, i in idx.items():
            if name.endswith(s):
                return i
    return None


FUND_RELATIONSHIPS = {"IS_FUND-MANAGED_BY", "IS_SUBFUND_OF", "IS_FEEDER_TO"}


def extract_relationships(fund_leis: set[str]) -> None:
    """Fund manager, umbrella and master-fund links for the Luxembourg funds.

    1. GLEIF relationship records (RR Golden Copy): IS_FUND-MANAGED_BY, IS_SUBFUND_OF, IS_FEEDER_TO.
    2. The "associated entity" of the fund's own LEI record (older way funds reported their manager).
    3. Names, countries and status of every related entity, from the LEI Golden Copy.
    Writes fund_relationships.csv and related_entities.csv.
    """
    rels: list[dict] = []
    print("Scanning GLEIF relationship records for Luxembourg funds...")
    cols = None
    for i, (idx, row) in enumerate(_zip_csv_rows(download_golden_copy("rr")), 1):
        if cols is None:
            cols = {
                "start": _col(idx, "Relationship.StartNode.NodeID"),
                "end": _col(idx, "Relationship.EndNode.NodeID"),
                "type": _col(idx, "Relationship.RelationshipType"),
                "status": _col(idx, "Relationship.RelationshipStatus"),
                "start_date": _col(
                    idx,
                    "Relationship.Period.1.startDate",
                    "Relationship.RelationshipPeriods.RelationshipPeriod.1.StartDate",
                ),
                "reg_status": _col(idx, "Registration.RegistrationStatus"),
            }
            missing = [k for k in ("start", "end", "type") if cols[k] is None]
            if missing:
                raise SystemExit(f"Unexpected relationship file format, missing {missing}. Columns: {list(idx)[:20]}")
        if i % 200_000 == 0:
            print(f"  {i:,} relationship rows scanned, {len(rels):,} fund links")
        rtype = row[cols["type"]]
        if rtype not in FUND_RELATIONSHIPS or row[cols["start"]] not in fund_leis:
            continue
        get_ = lambda k: row[cols[k]] if cols[k] is not None else ""  # noqa: E731
        rels.append({
            "fund_lei": row[cols["start"]], "related_lei": row[cols["end"]], "related_name": "",
            "relationship_type": rtype, "relationship_status": get_("status"),
            "start_date": get_("start_date")[:10], "registration_status": get_("reg_status"), "source": "relationship_record",
        })  # fmt: skip
    print(f"  {len(rels):,} fund links found in relationship records")

    print("Scanning the LEI Golden Copy for associated entities and related entity names...")
    wanted = {r["related_lei"] for r in rels}
    entities: dict[str, dict] = {}
    assoc_rows = []
    c = None
    for i, (idx, row) in enumerate(_zip_csv_rows(download_golden_copy("lei2")), 1):
        if c is None:
            c = {
                "lei": _col(idx, "LEI"), "name": _col(idx, "Entity.LegalName"),
                "country": _col(idx, "Entity.LegalAddress.Country"), "category": _col(idx, "Entity.EntityCategory"),
                "status": _col(idx, "Entity.EntityStatus"),
                "assoc_lei": _col(idx, "Entity.AssociatedEntity.AssociatedLEI"),
                "assoc_name": _col(idx, "Entity.AssociatedEntity.AssociatedEntityName"),
                "assoc_type": _col(idx, "Entity.AssociatedEntity.type"),
            }  # fmt: skip
        if i % 500_000 == 0:
            print(f"  {i:,} rows scanned")
        lei = row[c["lei"]]
        if lei in fund_leis and c["assoc_type"] is not None and row[c["assoc_type"]]:
            a_lei = row[c["assoc_lei"]] if c["assoc_lei"] is not None else ""
            a_name = row[c["assoc_name"]] if c["assoc_name"] is not None else ""
            if a_lei or a_name:
                assoc_rows.append({
                    "fund_lei": lei, "related_lei": a_lei, "related_name": a_name,
                    "relationship_type": f"ASSOCIATED_{row[c['assoc_type']]}", "relationship_status": "ACTIVE",
                    "start_date": "", "registration_status": "", "source": "lei_record",
                })  # fmt: skip
        if lei in wanted:
            entities[lei] = {
                "lei": lei, "legal_name": row[c["name"]], "country": row[c["country"]],
                "category": row[c["category"]], "entity_status": row[c["status"]],
            }  # fmt: skip
    # second pass only for associated LEIs we have not seen yet (they can appear before the fund in the file)
    extra = {r["related_lei"] for r in assoc_rows if r["related_lei"]} - set(entities)
    if extra:
        for idx, row in _zip_csv_rows(download_golden_copy("lei2")):
            lei = row[c["lei"]]
            if lei in extra:
                entities[lei] = {
                    "lei": lei, "legal_name": row[c["name"]], "country": row[c["country"]],
                    "category": row[c["category"]], "entity_status": row[c["status"]],
                }  # fmt: skip
    rels += assoc_rows
    fields = ["fund_lei", "related_lei", "related_name", "relationship_type", "relationship_status", "start_date",
              "registration_status", "source"]  # fmt: skip
    with open(OUT / "fund_relationships.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rels)
    with open(OUT / "related_entities.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["lei", "legal_name", "country", "category", "entity_status"])
        w.writeheader()
        w.writerows(entities.values())
    by_type = Counter(r["relationship_type"] for r in rels)
    managed = {
        r["fund_lei"] for r in rels if r["relationship_type"] in ("IS_FUND-MANAGED_BY", "ASSOCIATED_FUND_FAMILY")
    }
    print(f"Saved {len(rels):,} links and {len(entities):,} related entities.")
    for t, n in by_type.most_common():
        print(f"  {t}: {n:,}")
    print(f"Funds with a reported manager: {len(managed):,} of {len(fund_leis):,}")


def fetch_lu_funds() -> list[dict]:
    """Every LEI whose legal address is in Luxembourg and whose category is FUND."""
    import io
    import zipfile

    path = download_golden_copy()
    csv.field_size_limit(10_000_000)
    funds = []
    with zipfile.ZipFile(path) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        with zf.open(name) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
            header = next(reader)
            idx = {h: i for i, h in enumerate(header)}

            def col(*names):
                for n in names:
                    if n in idx:
                        return idx[n]
                raise KeyError(f"None of {names} in the Golden Copy header")

            c_lei = col("LEI")
            c_name = col("Entity.LegalName")
            c_country = col("Entity.LegalAddress.Country")
            c_cat = col("Entity.EntityCategory")
            c_form = col("Entity.LegalForm.EntityLegalFormCode")
            c_estatus = col("Entity.EntityStatus")
            c_rstatus = col("Registration.RegistrationStatus")
            c_init = col("Registration.InitialRegistrationDate")
            c_upd = col("Registration.LastUpdateDate")
            other_cols = []
            for k in range(1, 10):
                n, t = (
                    f"Entity.OtherEntityNames.OtherEntityName.{k}",
                    f"Entity.OtherEntityNames.OtherEntityName.{k}.type",
                )
                if n in idx and t in idx:
                    other_cols.append((idx[n], idx[t]))
            print("Filtering Luxembourg funds (about 3 million rows to scan, takes a few minutes)...")
            for i, row in enumerate(reader, 1):
                if i % 500_000 == 0:
                    print(f"  {i:,} rows scanned, {len(funds):,} Luxembourg funds")
                if row[c_country] != "LU" or row[c_cat] != "FUND":
                    continue
                previous, other = [], []
                for ci, ti in other_cols:
                    if row[ci]:
                        (previous if row[ti] == "PREVIOUS_LEGAL_NAME" else other).append(
                            row[ci] if row[ti] == "PREVIOUS_LEGAL_NAME" else f"{row[ti]}: {row[ci]}"
                        )
                funds.append(
                    {
                        "lei": row[c_lei],
                        "legal_name": row[c_name],
                        "previous_names": " | ".join(previous),
                        "other_names": " | ".join(other),
                        "legal_form": row[c_form],
                        "entity_status": row[c_estatus],
                        "registration_status": row[c_rstatus],
                        "initial_registration": row[c_init][:10],
                        "last_update": row[c_upd][:10],
                    }
                )
    print(f"Found {len(funds):,} Luxembourg funds.")
    return funds


# --------------------------------------------------------------------------- step 3
def _pick(d: dict, *needles: str):
    """Find a value whose key contains one of the needles (API field names vary)."""
    for k, v in d.items():
        kl = k.lower()
        if any(n in kl for n in needles):
            return v
    return None


def name_changes(lei: str) -> list[dict]:
    url = f"{API}/lei-records/{lei}/field-modifications?page%5Bsize%5D=200"
    changes, page = [], 1
    while url:
        data = get(url, cache_key=f"mods_{lei}_p{page}")
        for item in data.get("data", []):
            a = item.get("attributes", item)
            field = str(_pick(a, "field") or "")
            if "legalname" not in field.replace("/", "").replace(".", "").lower():
                continue
            if "transliterat" in field.lower() or "othername" in field.lower():
                continue
            if "lang" in field.lower():  # the name's language tag (xml:lang: "en", "de", "lb"), not the name
                continue
            old = _pick(a, "old")
            new = _pick(a, "new")
            date = str(_pick(a, "date") or "")[:10]
            if old and new and old != new:
                changes.append({"lei": lei, "date": date, "old_name": old, "new_name": new, "field": field})
        url = (data.get("links") or {}).get("next")
        page += 1
    return changes


# --------------------------------------------------------------------------- main
def normalize_name(name: str) -> str:
    """Compare names without case, accents, punctuation or legal-form spelling noise."""
    import unicodedata

    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[^a-z0-9]+", " ", n)
    n = re.sub(r"\b(s a r l|s a|sarl|sa|sicav|sicaf|scsp|scs|fcp|sca|raif|sif)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def classify(r: dict) -> None:
    old_t, new_t = terms_in(r["old_name"], ESG_TERMS), terms_in(r["new_name"], ESG_TERMS)
    r["change_type"] = "formatting" if normalize_name(r["old_name"]) == normalize_name(r["new_name"]) else "real"
    r["esg_dropped"] = ", ".join(sorted(old_t - new_t))
    r["esg_added"] = ", ".join(sorted(new_t - old_t))
    r["vague_in_new"] = ", ".join(sorted(terms_in(r["new_name"], VAGUE_TERMS)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-history", type=int, default=0, help="limit history calls (0 = no limit)")
    ap.add_argument("--sample", type=int, default=0, help="also check N random funds without a previous name")
    ap.add_argument(
        "--all",
        action="store_true",
        help="check the history of EVERY fund (about 11 hours, resumable; active funds first)",
    )
    ap.add_argument(
        "--relationships",
        action="store_true",
        help="only extract fund manager / umbrella / master links (uses lu_funds.csv; minutes, no API calls)",
    )
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)

    if args.relationships:
        funds_file = OUT / "lu_funds.csv"
        if funds_file.exists():
            with open(funds_file, encoding="utf-8") as fh:
                leis = {r["lei"] for r in csv.DictReader(fh)}
        else:
            leis = {f["lei"] for f in fetch_lu_funds()}
        extract_relationships(leis)
        return

    # 1. list
    funds = fetch_lu_funds()
    with open(OUT / "lu_funds.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(funds[0].keys()) if funds else ["lei"])
        w.writeheader()
        w.writerows(funds)
    print(f"Saved {len(funds)} funds to {OUT / 'lu_funds.csv'}")

    # 2. which funds to check
    candidates = [f for f in funds if f["previous_names"]]
    print(f"{len(candidates)} funds have a recorded previous legal name.")
    if args.all:
        todo = sorted(funds, key=lambda f: f["entity_status"] != "ACTIVE")
        if args.max_history:
            todo = todo[: args.max_history]
    else:
        todo = candidates[: args.max_history] if args.max_history else list(candidates)
        if args.sample:
            others = [f for f in funds if not f["previous_names"]]
            random.seed(42)
            todo += random.sample(others, min(args.sample, len(others)))

    # 3. dated history
    renames = []
    for i, f in enumerate(todo, 1):
        renames += name_changes(f["lei"])
        if i % 100 == 0:
            print(f"  history checked for {i}/{len(todo)} funds, {len(renames)} name changes found")
    for r in renames:
        classify(r)
    # which funds had their history checked (needed to reconstruct names over time)
    counts = Counter(r["lei"] for r in renames)
    with open(OUT / "history_checked.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["lei", "name_changes"])
        for f in todo:
            w.writerow([f["lei"], counts.get(f["lei"], 0)])
    with open(OUT / "renames.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "lei",
                "date",
                "old_name",
                "new_name",
                "change_type",
                "esg_dropped",
                "esg_added",
                "vague_in_new",
                "field",
            ],
        )
        w.writeheader()
        w.writerows(renames)

    # 4. summary (real renames only: case/punctuation-only changes are excluded)
    real = [r for r in renames if r["change_type"] == "real" and r["date"]]
    lines = []
    p = lines.append
    p(f"Luxembourg funds in GLEIF: {len(funds)}")
    p(f"  active (entity status ACTIVE): {sum(f['entity_status'] == 'ACTIVE' for f in funds)}")
    p(f"  with an ESG term in the current name: {sum(bool(terms_in(f['legal_name'], ESG_TERMS)) for f in funds)}")
    p(f"  with a recorded previous legal name: {len(candidates)}")
    p(f"Funds whose history was checked: {len(todo)}")
    p(f"Name changes found: {len(renames)} ({len(renames) - len(real)} formatting only, {len(real)} real)")
    p(f"Funds with at least one real rename: {len({r['lei'] for r in real})}")
    by_q = Counter(f"{r['date'][:4]}-Q{(int(r['date'][5:7]) - 1) // 3 + 1}" for r in real)
    p("Real renames per quarter:")
    for q in sorted(by_q):
        p(f"  {q}: {by_q[q]:4d} {'#' * min(by_q[q], 80)}")
    window = [r for r in real if "2024-05-14" <= r["date"] <= "2025-12-31"]
    dropped = [r for r in window if r["esg_dropped"]]
    p(f"Real renames between 14 May 2024 and end 2025: {len(window)} ({len({r['lei'] for r in window})} funds)")
    p(f"  dropped at least one ESG term: {len(dropped)} ({len({r['lei'] for r in dropped})} funds)")
    p(f"  added an ESG term: {sum(bool(r['esg_added']) for r in window)}")
    vague = Counter(t for r in dropped for t in r["vague_in_new"].split(", ") if t)
    p(
        "  replacement words among those that dropped ESG terms: "
        + (", ".join(f"{k} ({v})" for k, v in vague.most_common()) or "none detected")
    )
    p("Examples (to review: keyword matching also catches non-ESG meanings, e.g. 'transition' in LDI funds):")
    for r in dropped[:15]:
        p(f"  {r['date']}  {r['old_name']}  ->  {r['new_name']}")
    if args.sample and not args.all:
        sampled = {f["lei"] for f in todo[len(todo) - args.sample :]}
        hidden = [r for r in real if r["lei"] in sampled]
        p(f"Coverage test: {len(hidden)} real renames among {args.sample} funds WITHOUT a recorded previous name.")
    text = "\n".join(lines)
    print("\n" + text)
    (OUT / "summary.txt").write_text(text, encoding="utf-8")
    print(f"\nFiles in {OUT.resolve()}")


if __name__ == "__main__":
    main()
