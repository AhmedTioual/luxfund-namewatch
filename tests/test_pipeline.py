import duckdb

from app.data import name_diff


def q(warehouse, sql):
    with duckdb.connect(str(warehouse), read_only=True) as con:
        return con.execute(sql).fetchall()


def test_formatting_only_changes_are_excluded(warehouse):
    (n_fmt,) = q(warehouse, "select count(*) from staging.stg_name_changes where is_formatting_only")[0]
    (n_real,) = q(warehouse, "select count(*) from marts.fct_renames")[0]
    (n_all,) = q(warehouse, "select count(*) from staging.stg_name_changes")[0]
    assert n_fmt > 0 and n_real + n_fmt == n_all


def test_esg_term_replaced_by_vague_word_is_classified(warehouse):
    rows = q(
        warehouse,
        "select category, esg_terms_dropped, vague_terms_added from marts.fct_renames "
        "where old_name like '%SUSTAINABLE%' and new_name like '%SELECT%' limit 1",
    )
    assert rows, "the fixture contains Sustainable -> Select renames"
    category, dropped, added = rows[0]
    assert category == "esg_to_vague" and "sustainable" in dropped and "select" in added


def test_name_history_has_one_current_name_per_fund(warehouse):
    (funds,) = q(warehouse, "select count(*) from staging.stg_funds")[0]
    (current,) = q(warehouse, "select count(*) from intermediate.int_name_history where is_current")[0]
    assert funds == current


def test_esg_share_falls_after_the_deadline(warehouse):
    rows = dict(q(warehouse, "select quarter, esg_name_share from marts.agg_esg_names_by_quarter"))
    assert rows["2024-Q1"] > rows["2025-Q4"]


def test_kpis_single_row_and_consistent(warehouse):
    k = q(warehouse, "select funds, funds_dropped_esg, funds_esg_to_vague from marts.mart_kpis")
    assert len(k) == 1
    funds, dropped, vague = k[0]
    assert funds == 1500 and 0 < vague <= dropped


def test_name_diff_marks_removed_and_added_words():
    html = str(name_diff("ALPHA ESG EMU BOND", "ALPHA TILTED EMU BOND", ["esg"], ["tilted"]))
    assert '<del class="rl-del key">ESG</del>' in html
    assert '<ins class="rl-ins key">TILTED</ins>' in html
    assert "EMU BOND" in html


def test_name_diff_escapes_html():
    assert "<script>" not in str(name_diff("A <script>", "A b"))


def test_manager_links_prefer_relationship_records(warehouse):
    rows = dict(q(warehouse, "select manager_source, count(*) from marts.dim_fund group by 1"))
    assert rows["GLEIF relationship record"] > rows["Fund LEI record (associated entity)"] > 0


def test_third_party_manco_spans_several_brands(warehouse):
    (prefixes,) = q(
        warehouse, "select name_prefixes from marts.agg_fund_managers where manager_name like 'Kirchberg%'"
    )[0]
    assert prefixes > 5


def test_language_tag_changes_are_not_renames(warehouse):
    (raw_tags,) = q(warehouse, "select count(*) from raw.name_changes where old_name in ('lb', 'en')")[0]
    assert raw_tags > 0, "the fixture contains language-tag changes"
    (in_history,) = q(
        warehouse, "select count(*) from intermediate.int_name_history where name in ('lb', 'de', 'en', 'fr')"
    )[0]
    (in_renames,) = q(
        warehouse, "select count(*) from marts.fct_renames where old_name in ('lb', 'en') or new_name in ('de', 'fr')"
    )[0]
    (excluded,) = q(warehouse, "select language_tag_changes_excluded from marts.mart_data_quality")[0]
    assert in_history == 0 and in_renames == 0 and excluded == raw_tags
