"""Run the whole pipeline: load -> dbt build -> AI review (optional) -> dbt build -> evaluation.

    python -m pipeline.run              # everything (AI step runs only if ANTHROPIC_API_KEY is set)
    python -m pipeline.run --skip-ai

The same steps are defined as an Airflow DAG in dags/namewatch_dag.py.
"""

import argparse
import os
import subprocess
import sys
import time

from pipeline import load_raw
from pipeline.config import ANTHROPIC_API_KEY, DBT_DIR, GOLDEN_FILE, WAREHOUSE


def step(title: str, fn) -> None:
    print(f"\n== {title}")
    t = time.time()
    fn()
    print(f"   done in {time.time() - t:.1f}s")


def dbt_build() -> None:
    env = {**os.environ, "NAMEWATCH_DB": str(WAREHOUSE)}
    result = subprocess.run(
        ["dbt", "build", "--profiles-dir", ".", "--quiet", "--warn-error-options", '{"error": []}'],
        cwd=DBT_DIR, env=env,
    )  # fmt: skip
    if result.returncode != 0:
        sys.exit("dbt build failed: see the messages above (a failed data test stops the pipeline).")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-ai", action="store_true")
    args = ap.parse_args()
    step("1. Load raw files into DuckDB", load_raw.main)
    step("2. Transform and test (dbt build)", dbt_build)
    if ANTHROPIC_API_KEY and not args.skip_ai:
        from ai import classify_names

        sys.argv = [sys.argv[0]]
        step("3. AI review of ESG-related renames", classify_names.main)
        step("4. Reload and rebuild with the AI categories", lambda: (load_raw.main(), dbt_build()))
    else:
        print("\n== 3. AI review skipped (no ANTHROPIC_API_KEY or --skip-ai): keyword rules only")
    if GOLDEN_FILE.exists():
        from ai import evaluate

        step("5. Evaluate rules and LLM against the golden set", evaluate.evaluate)
    print(f"\nWarehouse ready: {WAREHOUSE}\nStart the dashboard:  uvicorn app.main:app --reload")


if __name__ == "__main__":
    main()
