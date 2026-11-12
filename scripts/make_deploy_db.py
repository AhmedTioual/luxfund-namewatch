"""Make a compact, read-only copy of the warehouse for hosting the dashboard.

    python -m pipeline.run                 # build the warehouse first
    python -m scripts.make_deploy_db       # writes deploy/namewatch.duckdb

Commit deploy/namewatch.duckdb, then point the host at it with NAMEWATCH_DB=deploy/namewatch.duckdb.
"""

from pathlib import Path

import duckdb

from pipeline.config import WAREHOUSE

OUT = Path(__file__).resolve().parents[1] / "deploy" / "namewatch.duckdb"


def main() -> None:
    if not WAREHOUSE.exists():
        raise SystemExit(f"No warehouse at {WAREHOUSE}: run python -m pipeline.run first.")
    OUT.parent.mkdir(exist_ok=True)
    for f in (OUT, OUT.with_suffix(".duckdb.wal")):
        f.unlink(missing_ok=True)
    con = duckdb.connect()
    con.execute(f"attach '{WAREHOUSE.as_posix()}' as src (read_only)")
    con.execute(f"attach '{OUT.as_posix()}' as deploy")
    con.execute("copy from database src to deploy")  # rewrites tables compactly, no free pages
    con.execute("detach deploy")
    con.close()
    mb = OUT.stat().st_size / 1e6
    print(f"{OUT} written ({mb:.1f} MB)")
    if mb > 95:
        print("Over GitHub's 100 MB file limit: track it with Git LFS (git lfs track 'deploy/*.duckdb').")


if __name__ == "__main__":
    main()
