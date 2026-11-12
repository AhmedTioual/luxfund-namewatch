"""Generate a small FICTIONAL dataset in the same format as the GLEIF extract.

Used only by the automated tests and for development without network access.
Every name here is invented. The real data comes from extract/gleif_extract.py.

    python -m tests.fixtures.make_fixture        # writes tests/fixtures/data/
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).parent / "data"
HOUSES = ["NORTHSTAR", "ALPINE", "MERIDIAN", "RIVERBEND", "KESTREL", "BELLMONT", "HALVARD", "CORVANE", "ESTREL",
          "GREYFIELD", "ORION", "LUMEN"]  # fmt: skip
ASSETS = ["GLOBAL EQUITY", "EURO CORPORATE BOND", "EMERGING MARKETS EQUITY", "EMU GOVERNMENT BOND", "US EQUITY",
          "GLOBAL HIGH YIELD", "ASIA EX JAPAN EQUITY", "MULTI ASSET INCOME", "EURO SHORT DURATION", "WORLD EQUITY INDEX"]  # fmt: skip
ESG = ["ESG", "SUSTAINABLE", "CLIMATE", "GREEN", "IMPACT", "SRI", "RESPONSIBLE", "TRANSITION", "ESG LEADERS"]
VAGUE = ["SCREENED", "SELECT", "ENHANCED", "TILTED", "LEADERS", "QUALITY", "EXCLUSION"]
FORMS = ["SICAV", "FCP", "SCSP", "SA", "RAIF"]


def main(n_funds: int = 1500, seed: int = 7) -> None:
    rng = random.Random(seed)
    OUT.mkdir(parents=True, exist_ok=True)
    funds, renames, checked = [], [], []
    for i in range(n_funds):
        lei = f"5299{i:08d}LUFIX{rng.randint(100, 999)}"
        house, asset = rng.choice(HOUSES), rng.choice(ASSETS)
        esg = rng.random() < 0.18
        name = f"{house} {rng.choice(ESG) + ' ' if esg else ''}{asset}"
        init = date(2014, 1, 1) + timedelta(days=rng.randint(0, 3900))
        history = []
        current = name
        if esg and rng.random() < 0.45:  # ESMA wave: drop or replace the ESG term
            when = date(2024, 9, 1) + timedelta(days=int(abs(rng.gauss(250, 80))))
            replacement = rng.choice(VAGUE + [""])
            for t in ESG:
                current = (
                    current.replace(t + " ", (replacement + " ") if replacement else "", 1) if t in current else current
                )
            history.append((when, name, current))
        elif rng.random() < 0.06:  # ordinary rename
            when = min(init + timedelta(days=rng.randint(100, 3000)), date(2026, 10, 1))
            current = name.replace(house, rng.choice(HOUSES), 1)
            if current != name:
                history.append((when, name, current))
        if rng.random() < 0.08:  # formatting-only change
            when = date(2022, 4, 1) + timedelta(days=rng.randint(0, 500))
            history.append((when, current, current.title()))
            current = current.title()
        history.sort()
        status = "ACTIVE" if rng.random() < 0.75 else "INACTIVE"
        funds.append({
            "lei": lei, "legal_name": current, "previous_names": history[0][1] if history and rng.random() < 0.6 else "",
            "other_names": "", "legal_form": rng.choice(FORMS), "entity_status": status,
            "registration_status": "ISSUED" if status == "ACTIVE" else "LAPSED",
            "initial_registration": init.isoformat(), "last_update": "2026-10-01",
        })  # fmt: skip
        if rng.random() < 0.05:  # GLEIF also logs changes of the name's language tag ("lb" -> "de"): not renames
            when = date(2022, 6, 15) + timedelta(days=rng.randint(0, 900))
            renames.append(
                {
                    "lei": lei,
                    "date": when.isoformat(),
                    "old_name": "lb",
                    "new_name": "de",
                    "field": "LEIREC/Entity/LegalName/@xml:lang",
                }
            )
            renames.append(
                {
                    "lei": lei,
                    "date": when.isoformat(),
                    "old_name": "en",
                    "new_name": "fr",
                    "field": "LEIREC/Entity/LegalName",
                }
            )  # same, without the field telling us
        if history or rng.random() < 0.3:
            checked.append({"lei": lei, "name_changes": len(history)})
            for when, old, new in history:
                renames.append({"lei": lei, "date": when.isoformat(), "old_name": old, "new_name": new,
                                "field": "LEIREC/Entity/LegalName"})  # fmt: skip
    # Fund managers (fictional): each house has a management company; a third-party ManCo
    # ("Kirchberg Fund Services") manages funds for several houses, as white-label ManCos do in Luxembourg.
    managers = {h: f"5299MGR{i:06d}LUFIX{i:02d}" for i, h in enumerate(HOUSES)}
    third_party = "5299MGR999999LUFIX99"
    entities = [
        {
            "lei": lei,
            "legal_name": f"{h.title()} Asset Management S.A.",
            "country": "LU",
            "category": "GENERAL",
            "entity_status": "ACTIVE",
        }
        for h, lei in managers.items()
    ]
    entities.append(
        {
            "lei": third_party,
            "legal_name": "Kirchberg Fund Services S.A.",
            "country": "LU",
            "category": "GENERAL",
            "entity_status": "ACTIVE",
        }
    )
    umbrellas = {}
    rels = []
    for f in funds:
        house = f["legal_name"].split()[0].upper()
        roll = rng.random()
        if house in managers and roll < 0.62:
            mgr = third_party if rng.random() < 0.15 else managers[house]
            rels.append(
                {
                    "fund_lei": f["lei"],
                    "related_lei": mgr,
                    "related_name": "",
                    "relationship_type": "IS_FUND-MANAGED_BY",
                    "relationship_status": "ACTIVE",
                    "start_date": "2023-06-01",
                    "registration_status": "PUBLISHED",
                    "source": "relationship_record",
                }
            )
        elif house in managers and roll < 0.75:
            rels.append(
                {
                    "fund_lei": f["lei"],
                    "related_lei": managers[house],
                    "related_name": "",
                    "relationship_type": "ASSOCIATED_FUND_FAMILY",
                    "relationship_status": "ACTIVE",
                    "start_date": "",
                    "registration_status": "",
                    "source": "lei_record",
                }
            )
        if f["legal_form"] == "SICAV" and house in managers and rng.random() < 0.8:
            if house not in umbrellas:
                umbrellas[house] = f"5299UMB{len(umbrellas):06d}LUFIX{len(umbrellas):02d}"
                entities.append(
                    {
                        "lei": umbrellas[house],
                        "legal_name": f"{house.title()} Funds SICAV",
                        "country": "LU",
                        "category": "FUND",
                        "entity_status": "ACTIVE",
                    }
                )
            rels.append(
                {
                    "fund_lei": f["lei"],
                    "related_lei": umbrellas[house],
                    "related_name": "",
                    "relationship_type": "IS_SUBFUND_OF",
                    "relationship_status": "ACTIVE",
                    "start_date": "2020-01-01",
                    "registration_status": "PUBLISHED",
                    "source": "relationship_record",
                }
            )
    for fname, rows in (
        ("lu_funds.csv", funds),
        ("renames.csv", renames),
        ("history_checked.csv", checked),
        ("fund_relationships.csv", rels),
        ("related_entities.csv", entities),
    ):
        with open(OUT / fname, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print(f"{len(funds)} funds, {len(renames)} renames, {len(checked)} checked, {len(rels)} relationships -> {OUT}")


if __name__ == "__main__":
    main()
