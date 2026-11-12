# LuxFund NameWatch

**How Luxembourg investment funds renamed after the EU's rules on ESG fund names, measured on public data.**

Since ESMA's guidelines on fund names (published 14 May 2024, applicable to existing funds from 21 May 2025), a fund with "ESG", "sustainable", "green" or "impact" in its name must hold at least 80% of investments meeting its sustainability characteristics and apply EU climate-benchmark exclusions. Many funds renamed instead. ESMA's own review (January 2026) found that 65% of the 924 funds it studied changed their name, and almost half of those that removed every ESG term adopted words like "Scored", "Screened", "Select", "Advanced" or "Committed".

NameWatch tracks this for every Luxembourg fund with an LEI: which funds dropped ESG words, when, and what replaced them. All data is public (GLEIF, licence CC0). Nothing comes from an employer or a client.

## What it does

```
GLEIF Golden Copy + change history ─> DuckDB (raw) ─> dbt models + tests ─> AI review ─> web dashboard
        extract/                      pipeline/        transform/           ai/            app/
```

| Step | What happens |
|---|---|
| **Extract** (`extract/gleif_extract.py`) | Keeps the ~40,000 Luxembourg funds and sub-funds (legal address LU, category FUND) from GLEIF's full file, then downloads each fund's dated field-change history from the GLEIF API (resumable, rate-limited). |
| **Fund links** (`extract/gleif_extract.py --relationships`) | From GLEIF's relationship records: each fund's management company (`IS_FUND-MANAGED_BY`), umbrella (`IS_SUBFUND_OF`) and master fund (`IS_FEEDER_TO`). Falls back on the manager declared as "associated entity" in the fund's own LEI record. Names and countries of the linked entities come from the LEI file. No API calls; takes a few minutes. |
| **Load** (`pipeline/load_raw.py`) | Loads the CSV files into DuckDB and logs each load with its SHA-256 fingerprint and row count. |
| **Transform and test** (`transform/`, dbt) | Cleans the data and drops formatting-only changes (case, accents, punctuation). Matches names against a versioned ESG vocabulary (a dbt seed). Rebuilds each fund's **name history over time** (valid-from / valid-to periods). Builds the marts. 20 data tests run on every build. |
| **AI review** (`ai/classify_names.py`) | Keyword rules can't tell that "transition" in an LDI fund is not a climate claim. Claude re-reads every ESG-related rename and returns a category with a one-line reason. Results are cached and only new renames are sent. |
| **Evaluate** (`ai/evaluate.py`) | You label a sample by hand; the script measures the accuracy of the rules and of the AI. The results appear in the dashboard. |
| **Dashboard** (`app/`, FastAPI) | Overview (renames per quarter with the ESMA milestones, flows from ESG words to replacements, share of ESG names over time), word-by-word redline of every rename, fund search with name history, manager and umbrella, fund houses by management company, data and method. JSON API at `/docs`. |

## Run it (Windows PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 1. Extract (skip if you already have the files in gleif_check\)
python extract\gleif_extract.py --all          # ~11 h for every fund, resumable
#   quicker sample: python extract\gleif_extract.py --max-history 300 --sample 100

python extract\gleif_extract.py --relationships   # fund managers and umbrellas, a few minutes

# 2. Put the extract files where the pipeline reads them
copy gleif_check\*.csv data\raw\

# 3. Build the warehouse (load, dbt build and tests, AI review if a key is set)
$env:ANTHROPIC_API_KEY = "sk-ant-..."          # optional
python -m pipeline.run

# 4. Open the dashboard
uvicorn app.main:app --reload                  # http://localhost:8000
```

`history_checked.csv` says which funds' histories were downloaded. If it's missing (older extracts), the pipeline assumes the funds with a rename were checked.

To measure accuracy:

```powershell
python -m ai.evaluate --template 60    # writes data\ai\golden_labels.csv: fill the `label` column
python -m ai.evaluate                  # scores rules and AI; shown on the "Data and method" page
```

Stop the dashboard before re-running the pipeline: DuckDB allows one writer at a time.

## Project layout

```
extract/gleif_extract.py      GLEIF Golden Copy + field-modification history
pipeline/                     config, raw loader, orchestrator (python -m pipeline.run)
transform/                    dbt project (staging, intermediate, marts, seeds, tests)
ai/                           LLM classification and evaluation
app/                          FastAPI dashboard (templates, static, ECharts bundled for offline use)
dags/namewatch_dag.py         the same steps as a monthly Airflow DAG
tests/                        pytest, run on a small fictional fixture
```

Stack: Python, DuckDB, dbt, Anthropic API, FastAPI, Jinja, ECharts, pytest, ruff, GitHub Actions, Docker, Airflow (DAG).

```powershell
pip install -r requirements-dev.txt
pytest                      # builds a warehouse from the fictional fixture and tests models, pages and API
ruff check .
```

## Limits

- GLEIF records **legal** names. A marketing name can change without the LEI record changing, and some records are updated late.
- With a partial extraction, the over-time figures cover only the funds whose history was checked.
- Dropping an ESG word is not wrongdoing: a fund may simply choose not to meet the 80% threshold. NameWatch shows signals to review, not findings of non-compliance.
- A management company is known only when the fund reports it to GLEIF. Funds without one are grouped by the first word of their name (the "Name prefix" tab).
- Next step two: read the funds' KIDs and SFDR annexes, and check that names match their documented commitments.

Data: [GLEIF Golden Copy](https://www.gleif.org/en/lei-data/gleif-golden-copy/download-the-golden-copy) and [GLEIF API](https://www.gleif.org/en/lei-data/gleif-api). Rules: [ESMA guidelines on funds' names](https://www.esma.europa.eu/sites/default/files/library/esma34-472-373_guidelines_on_funds_names.pdf).
