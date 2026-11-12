import duckdb
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_pages_render(warehouse):
    lei = (
        duckdb.connect(str(warehouse), read_only=True)
        .execute("select lei from marts.fct_renames where is_esg_rename limit 1")
        .fetchone()[0]
    )
    for url in ["/", "/renames", "/renames?category=esg_to_vague&scope=all&page_no=2", "/funds?q=green",
                f"/funds/{lei}", "/houses", "/houses?by=prefix", "/method", "/insights",
                "/renames?manager=5299MGR999999LUFIX99&scope=all"]:  # fmt: skip
        r = client.get(url)
        assert r.status_code == 200, url
    assert client.get("/funds/NOTALEI").status_code == 404


def test_api(warehouse):
    k = client.get("/api/kpis").json()
    assert k["funds"] == 1500
    body = client.get("/api/renames?category=esg_removed&limit=5").json()
    assert body["total"] > 0 and all(i["category"] == "esg_removed" for i in body["items"])


def test_chart_data_is_script_safe(warehouse):
    html = client.get("/").text
    assert "&#34;" not in html.split("<script>")[-1]
