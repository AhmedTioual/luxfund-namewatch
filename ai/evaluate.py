"""Step 4 - measure how often the keyword rules and the LLM get the category right.

You label a sample of renames by hand (the "golden set"), then this script compares:
    python -m ai.evaluate --template 60    # writes data/ai/golden_labels.csv with 60 renames to label
    (open it in Excel, fill the `label` column with one of the categories, save)
    python -m ai.evaluate                  # writes data/ai/eval_report.json, shown in the dashboard

Categories: esg_removed, esg_to_vague, esg_reworded, esg_added, not_esg, other_rename
"""

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from datetime import UTC, datetime

import duckdb

from pipeline.config import EVAL_FILE, GOLDEN_FILE, WAREHOUSE

CATEGORIES = ["esg_removed", "esg_to_vague", "esg_reworded", "esg_added", "not_esg", "other_rename"]


def make_template(n: int) -> None:
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        rows = con.execute(
            """select lei, cast(change_date as varchar), old_name, new_name, rule_category
               from intermediate.int_renames_classified where is_esg_candidate"""
        ).fetchall()
    rng = random.Random(42)
    by_cat = defaultdict(list)
    for r in rows:
        by_cat[r[4]].append(r)
    picked = []
    while len(picked) < min(n, len(rows)):  # round-robin over categories so rare cases are represented
        for cat in list(by_cat):
            if by_cat[cat] and len(picked) < n:
                picked.append(by_cat[cat].pop(rng.randrange(len(by_cat[cat]))))
    GOLDEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    if GOLDEN_FILE.exists():
        raise SystemExit(f"{GOLDEN_FILE} already exists; delete it first to make a new template.")
    with open(GOLDEN_FILE, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["lei", "change_date", "old_name", "new_name", "label", "notes"])
        for lei, d, old, new, _ in picked:
            w.writerow([lei, d, old, new, "", ""])
    print(f"Wrote {len(picked)} renames to label in {GOLDEN_FILE}. Fill `label` with: {', '.join(CATEGORIES)}")


def scores(pairs: list[tuple[str, str]]) -> dict:
    """pairs = [(truth, predicted)] -> accuracy, per-class precision/recall, confusion."""
    if not pairs:
        return {"n": 0}
    acc = sum(t == p for t, p in pairs) / len(pairs)
    per = {}
    for c in CATEGORIES:
        tp = sum(t == c and p == c for t, p in pairs)
        fp = sum(t != c and p == c for t, p in pairs)
        fn = sum(t == c and p != c for t, p in pairs)
        if tp + fp + fn:
            per[c] = {
                "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                "recall": round(tp / (tp + fn), 3) if tp + fn else None,
                "support": tp + fn,
            }
    confusion = Counter(f"{t} -> {p}" for t, p in pairs if t != p)
    return {"n": len(pairs), "accuracy": round(acc, 3), "per_class": per, "errors": confusion.most_common(10)}


def evaluate() -> None:
    if not GOLDEN_FILE.exists():
        raise SystemExit(f"No {GOLDEN_FILE}. Run `python -m ai.evaluate --template 60` and label it first.")
    with open(GOLDEN_FILE, encoding="utf-8") as fh:
        golden = [r for r in csv.DictReader(fh) if (r.get("label") or "").strip() in CATEGORIES]
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        rows = con.execute(
            """select lei, cast(change_date as varchar), old_name, new_name, rule_category, ai_category
               from intermediate.int_renames_classified"""
        ).fetchall()
    pred = {(r[0], r[1], r[2], r[3]): (r[4], r[5]) for r in rows}
    rules, llm, examples = [], [], []
    for g in golden:
        key = (g["lei"], g["change_date"], g["old_name"], g["new_name"])
        if key not in pred:
            continue
        rule_cat, ai_cat = pred[key]
        truth = g["label"].strip()
        rules.append((truth, rule_cat))
        if ai_cat:
            llm.append((truth, ai_cat))
        if rule_cat != truth or (ai_cat and ai_cat != truth):
            examples.append(
                {"old": g["old_name"], "new": g["new_name"], "truth": truth, "rules": rule_cat, "llm": ai_cat}
            )
    report = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "labelled": len(golden),
        "rules": scores(rules),
        "llm": scores(llm),
        "disagreements": examples[:20],
    }
    EVAL_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Rules accuracy: {report['rules'].get('accuracy')} on {report['rules']['n']} labelled renames")
    print(f"LLM accuracy:   {report['llm'].get('accuracy')} on {report['llm']['n']}")
    print(f"Report: {EVAL_FILE}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", type=int, default=0, help="write a golden-set template with N renames to label")
    args = ap.parse_args()
    make_template(args.template) if args.template else evaluate()


if __name__ == "__main__":
    main()
