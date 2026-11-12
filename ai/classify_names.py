"""Step 3 (optional) - an LLM reviews the ESG-related renames the keyword rules found.

Keyword rules are fast but naive: "transition" in an LDI fund is not a climate
claim, and "GR" may be a shortened "Green". The LLM reads each old and new name
and returns a category with a short rationale. Results are cached in
data/ai/name_classifications.csv, so only new renames are sent on later runs.

    set ANTHROPIC_API_KEY=...        (PowerShell: $env:ANTHROPIC_API_KEY="...")
    python -m ai.classify_names [--limit 50]

The final category used in the dashboard is the LLM's when available, else the
rules'. ai/evaluate.py measures both against hand-labelled examples.
"""

import argparse
import csv
import json
import sys

import duckdb

from pipeline.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, CLASSIFICATIONS_FILE, WAREHOUSE

CATEGORIES = {
    "esg_removed": "The old name made an ESG/sustainability claim and the new name makes none, with no vague replacement.",
    "esg_to_vague": "The ESG claim was replaced by a vaguer word (screened, select, tilted, leaders, enhanced, quality...).",
    "esg_reworded": "Both names make an ESG claim, but a different one (e.g. 'Sustainable' -> 'ESG Enhanced').",
    "esg_added": "The old name made no ESG claim and the new name does.",
    "not_esg": "A keyword matched but is not an ESG claim in context (e.g. 'transition' in a liability-driven "
    "investment fund, a share-class transition, a surname).",
    "other_rename": "A rename unrelated to ESG claims (brand, merger, strategy, abbreviation without ESG meaning).",
}
FIELDS = ["lei", "change_date", "old_name", "new_name", "category", "old_is_esg", "new_is_esg", "confidence",
          "rationale", "model"]  # fmt: skip

TOOL = {
    "name": "record_classifications",
    "description": "Record one classification per rename, in the order given.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "category": {"type": "string", "enum": list(CATEGORIES)},
                        "old_is_esg": {"type": "boolean", "description": "Does the OLD name make an ESG/sustainability claim?"},
                        "new_is_esg": {"type": "boolean", "description": "Does the NEW name make an ESG/sustainability claim?"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "rationale": {"type": "string", "description": "One short sentence"},
                    },
                    "required": ["id", "category", "old_is_esg", "new_is_esg", "confidence", "rationale"],
                },
            }
        },
        "required": ["items"],
    },
}  # fmt: skip

SYSTEM = (
    "You review legal-name changes of Luxembourg investment funds after the ESMA guidelines on funds' names "
    "using ESG or sustainability-related terms (applicable to existing funds from 21 May 2025). For each rename, "
    "decide whether the old and the new names make an ESG or sustainability claim (ESG, sustainable, green, "
    "climate, impact, SRI, responsible, social, transition in the climate sense...), then pick one category:\n"
    + "\n".join(f"- {k}: {v}" for k, v in CATEGORIES.items())
    + "\nJudge only from the names; be conservative and lower the confidence when the meaning is unclear."
)


def pending(con, done: set) -> list[dict]:
    rows = con.execute(
        """select lei, cast(change_date as varchar), old_name, new_name, rule_category
           from intermediate.int_renames_classified
           where is_esg_candidate
           order by change_date desc"""
    ).fetchall()
    keys = ("lei", "change_date", "old_name", "new_name", "rule_category")
    out = [dict(zip(keys, r, strict=True)) for r in rows]
    return [r for r in out if (r["lei"], r["change_date"], r["old_name"], r["new_name"]) not in done]


def classify_batch(client, batch: list[dict]) -> list[dict]:
    listing = "\n".join(
        f'{i}. "{r["old_name"]}" -> "{r["new_name"]}" ({r["change_date"]})' for i, r in enumerate(batch)
    )
    msg = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4000,
        system=SYSTEM,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "record_classifications"},
        messages=[{"role": "user", "content": f"Classify these renames:\n{listing}"}],
    )
    items = next(b.input for b in msg.content if b.type == "tool_use")["items"]
    by_id = {it["id"]: it for it in items}
    out = []
    for i, r in enumerate(batch):
        it = by_id.get(i)
        if not it:
            continue
        out.append({
            "lei": r["lei"], "change_date": r["change_date"], "old_name": r["old_name"], "new_name": r["new_name"],
            "category": it["category"], "old_is_esg": it["old_is_esg"], "new_is_esg": it["new_is_esg"],
            "confidence": it["confidence"], "rationale": it["rationale"], "model": ANTHROPIC_MODEL,
        })  # fmt: skip
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="classify at most N renames (0 = all pending)")
    ap.add_argument("--batch", type=int, default=25)
    args = ap.parse_args()
    if not ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY is not set: skipping the AI step (the dashboard uses the keyword rules).")
        return
    import anthropic

    done_rows = []
    if CLASSIFICATIONS_FILE.exists():
        with open(CLASSIFICATIONS_FILE, encoding="utf-8") as fh:
            done_rows = list(csv.DictReader(fh))
    done = {(r["lei"], r["change_date"], r["old_name"], r["new_name"]) for r in done_rows}
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        todo = pending(con, done)
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(done_rows)} renames already classified, {len(todo)} to classify with {ANTHROPIC_MODEL}.")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    new_rows = []
    for start in range(0, len(todo), args.batch):
        batch = todo[start : start + args.batch]
        try:
            new_rows += classify_batch(client, batch)
        except Exception as exc:  # keep what we have; the next run resumes
            print(f"  batch {start // args.batch + 1} failed: {exc}", file=sys.stderr)
            break
        print(f"  {min(start + args.batch, len(todo))}/{len(todo)}")
    CLASSIFICATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CLASSIFICATIONS_FILE, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(done_rows + new_rows)
    rule_of = {(t["lei"], t["change_date"], t["old_name"], t["new_name"]): t["rule_category"] for t in todo}
    agree = sum(
        r["category"] == rule_of.get((r["lei"], r["change_date"], r["old_name"], r["new_name"])) for r in new_rows
    )
    print(f"Saved {len(new_rows)} new classifications ({agree} agree with the keyword rules) to {CLASSIFICATIONS_FILE}")
    print(json.dumps({"classified": len(done_rows) + len(new_rows)}))


if __name__ == "__main__":
    main()
