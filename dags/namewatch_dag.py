"""Airflow DAG: the monthly refresh of LuxFund NameWatch.

GLEIF publishes its Golden Copy several times a day, but fund names change rarely,
so a monthly run is enough. Each task is the same command you can run by hand.
"""

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT = "/opt/namewatch"  # where the repository is deployed

with DAG(
    dag_id="luxfund_namewatch",
    start_date=datetime(2026, 11, 1),
    schedule="@monthly",
    catchup=False,
    default_args={"retries": 2},
    tags=["gleif", "esg", "luxembourg"],
) as dag:
    extract = BashOperator(
        task_id="extract_gleif",
        bash_command=f"cd {PROJECT} && python extract/gleif_extract.py --all && cp gleif_check/*.csv data/raw/",
    )
    load = BashOperator(task_id="load_raw", bash_command=f"cd {PROJECT} && python -m pipeline.load_raw")
    transform = BashOperator(task_id="dbt_build", bash_command=f"cd {PROJECT}/transform && dbt build --profiles-dir .")
    ai_review = BashOperator(task_id="ai_review", bash_command=f"cd {PROJECT} && python -m ai.classify_names")
    reload = BashOperator(
        task_id="reload_with_ai",
        bash_command=f"cd {PROJECT} && python -m pipeline.load_raw && cd transform && dbt build --profiles-dir .",
    )
    evaluate = BashOperator(task_id="evaluate", bash_command=f"cd {PROJECT} && python -m ai.evaluate || true")

    extract >> load >> transform >> ai_review >> reload >> evaluate
