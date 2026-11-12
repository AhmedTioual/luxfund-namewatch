"""Paths and settings shared by the pipeline steps and the web app."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = Path(os.getenv("NAMEWATCH_RAW_DIR", ROOT / "data" / "raw"))
AI_DIR = Path(os.getenv("NAMEWATCH_AI_DIR", ROOT / "data" / "ai"))
WAREHOUSE = Path(os.getenv("NAMEWATCH_DB", ROOT / "data" / "warehouse.duckdb"))
DBT_DIR = ROOT / "transform"

RAW_FILES = {
    "funds": "lu_funds.csv",
    "name_changes": "renames.csv",
    "history_checked": "history_checked.csv",
}
# Optional: written by `extract/gleif_extract.py --relationships`
_REL_COLS = ["fund_lei", "related_lei", "related_name", "relationship_type", "relationship_status", "start_date",
             "registration_status", "source"]  # fmt: skip
_ENT_COLS = ["lei", "legal_name", "country", "category", "entity_status"]
OPTIONAL_FILES = {
    "fund_relationships": ("fund_relationships.csv", ", ".join(f"{c} varchar" for c in _REL_COLS)),
    "related_entities": ("related_entities.csv", ", ".join(f"{c} varchar" for c in _ENT_COLS)),
}
CLASSIFICATIONS_FILE = AI_DIR / "name_classifications.csv"
GOLDEN_FILE = AI_DIR / "golden_labels.csv"
EVAL_FILE = AI_DIR / "eval_report.json"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("NAMEWATCH_MODEL", "claude-haiku-5-5")
