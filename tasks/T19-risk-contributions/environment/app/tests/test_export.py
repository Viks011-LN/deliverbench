import csv
import io
import json

from folio.report.csv_export import write_csv
from folio.report.json_export import valuation_document, write_json


def exported_csv(valuation):
    buffer = io.StringIO()
    count = write_csv(valuation, buffer)
    return count, list(csv.DictReader(io.StringIO(buffer.getvalue())))


def test_csv_has_one_row_per_position(valuation):
    count, rows = exported_csv(valuation)
    assert count == len(rows) == len(valuation.positions)
    assert [row["instrument"] for row in rows] == [line.instrument.id for line in valuation.positions]
    header = list(rows[0])
    assert header[:3] == ["portfolio", "as_of", "instrument"]
    assert header.index("sector") == header.index("kind") + 1
    assert header[-1] == "weight"


def test_csv_values_are_plain_numbers(small_valuation):
    _, rows = exported_csv(small_valuation)
    bond = rows[1]
    assert bond["instrument"] == "BBB"
    assert bond["kind"] == "bond"
    assert bond["sector"] == "Government"
    assert bond["local_value"] == "10000.00"
    assert bond["fx_rate"] == "0.800000"
    assert bond["base_value"] == "8000.00"
    assert bond["weight"] == "0.320000"
    assert bond["as_of"] == "2026-10-30"


def test_json_document(small_valuation):
    doc = valuation_document(small_valuation)
    assert doc["portfolio"] == {"code": "TEST", "name": "Test book"}
    assert doc["nav"] == "25000.00"
    assert [p["instrument"] for p in doc["positions"]] == ["AAA", "BBB", "CCC"]
    equity = doc["positions"][0]
    assert equity["sector"] == "Technology"
    assert equity["quantity"] == "1000"
    assert equity["weight"] == 0.48
    assert equity["stale_price"] is False
    assert doc["cash"] == [
        {"currency": "GBP", "amount": "1000.00", "fx_rate": "1.000000", "base_value": "1000.00", "weight": 0.04}
    ]


def test_json_keys_follow_csv_order(small_valuation):
    keys = list(valuation_document(small_valuation)["positions"][0])
    assert keys[:4] == ["instrument", "name", "kind", "sector"]
    assert keys[-1] == "weight"


def test_write_json_round_trips(valuation):
    buffer = io.StringIO()
    assert write_json(valuation, buffer) == len(valuation.positions)
    assert buffer.getvalue().endswith("}\n")
    doc = json.loads(buffer.getvalue())
    assert doc["as_of"] == "2026-10-30"
    assert len(doc["positions"]) == 38
    assert {p["sector"] for p in doc["positions"]} == {line.instrument.sector for line in valuation.positions}
