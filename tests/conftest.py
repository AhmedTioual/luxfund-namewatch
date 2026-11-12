"""Build a warehouse from the fictional fixture once per test session."""

import os
import subprocess
import tempfile
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "data"
TMP = Path(tempfile.mkdtemp(prefix="namewatch-tests-"))
os.environ["NAMEWATCH_RAW_DIR"] = str(FIXTURE)
os.environ["NAMEWATCH_DB"] = str(TMP / "warehouse.duckdb")
os.environ["NAMEWATCH_AI_DIR"] = str(TMP / "ai")
os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def warehouse():
    if not (FIXTURE / "lu_funds.csv").exists():
        from tests.fixtures.make_fixture import main as make

        make()
    from pipeline import load_raw
    from pipeline.config import DBT_DIR

    load_raw.main()
    result = subprocess.run(
        ["dbt", "build", "--profiles-dir", ".", "--quiet"], cwd=DBT_DIR, env=os.environ, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return Path(os.environ["NAMEWATCH_DB"])
