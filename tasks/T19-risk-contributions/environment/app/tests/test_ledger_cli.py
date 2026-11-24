import csv
import io
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from folio.cli import main as folio_main
from folio.ledger.cli import main
from folio.ledger.export import COLUMNS
from folio.report.tables import format_money

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TODAY = date(2026, 10, 30)
FOLIO_FILES = ("instruments.csv", "positions.json", "prices.csv", "fx.csv")
LEDGER_FILES = ("trades.csv", "cash_flows.csv")


def run(*argv, data=DATA, today=TODAY):
    out, err = io.StringIO(), io.StringIO()
    code = main([*argv, "--data-dir", str(data)], out=out, err=err, today=today)
    return code, out.getvalue(), err.getvalue()


def table_rows(text):
    """Cells of the body rows of the table in ``text``: from the first rule to a blank line or the next rule."""
    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("---")) + 1
    rows = []
    for line in lines[start:]:
        if not line or line.startswith("---"):
            break
        rows.append(line.split())
    return rows


@pytest.fixture
def data_copy(tmp_path):
    for name in FOLIO_FILES + LEDGER_FILES:
        shutil.copy(DATA / name, tmp_path / name)
    return tmp_path


def test_reconcile_on_the_sample_data():
    assert run("reconcile") == (
        0, "OK: 40 instruments and 4 cash balances agree with positions.json on 2026-10-30\n", "")
    # In the middle of the FRXL and NYQV round trips, which positions.json never booked.
    code, out, err = run("reconcile", "--as-of", "2026-09-30")
    assert code == 1
    assert out.splitlines() == [
        "DIFF FRXL: 300 open from trades.csv, no position in positions.json",
        "DIFF NYQV: open quantity 8,000 from trades.csv, 0 in positions.json",
        "DIFF NYQV: open lot 2026-09-10 8,000 @ 18.60 in trades.csv only",
    ]
    assert err.startswith("folio-ledger: note: cash not compared")


def test_trades_by_instrument_and_since():
    code, out, _ = run("trades", "--instrument", "FRXL")
    lines = out.splitlines()
    assert code == 0
    assert lines[:2] == ["Global Balanced (GBL-BAL)", "Trades in FRXL up to 2026-10-30"]
    assert [row[1] for row in table_rows(out)] == ["T0065", "T0067", "T0068", "T0069", "T0071", "T0076"]
    assert table_rows(out)[0] == ["2026-06-09", "T0065", "FRXL", "buy", "600", "316.12", "USD", "94.84",
                                  "-189,766.84"]
    assert lines[-1] == "6 trades: 3 buys, 3 sales"
    _, out, _ = run("trades", "--since", "2026-10-01")
    assert out.splitlines()[1] == "Trades from 2026-10-01 to 2026-10-30"
    assert [row[1] for row in table_rows(out)] == ["T0074", "T0075", "T0076"]


def test_pnl_by_instrument_and_sector():
    code, out, _ = run("pnl")
    rows = {row[0]: row for row in table_rows(out)}
    assert code == 0
    assert rows["FRXL"] == ["FRXL", "USD", "1,200", "431,654.06", "383,357.59", "48,296.47", "36,022.79", "0.00",
                            "36,022.79"]
    assert rows["CNZA"] == ["CNZA", "EUR", "0.00", "21,892.64", "21,892.64"]
    assert out.splitlines()[-1].split() == ["Total", "64,292.98", "292,329.06", "356,622.04"]

    _, out, _ = run("pnl", "--by", "sector", "--since", "2026-10-01")
    assert out.splitlines()[1] == "Realised P&L (FIFO) and income by sector from 2026-10-01 to 2026-10-30, in GBP"
    rows = {row[0]: row for row in table_rows(out)}
    # FRXL's last sale and the GRBY interim dividend.
    assert rows["Industrials"] == ["Industrials", "2", "15,538.69", "4,629.50", "20,168.19"]
    assert out.splitlines()[-1].split() == ["Total", "7", "32,216.35", "38,512.23", "70,728.57"]


def test_cash_agrees_with_the_valuation(valuation):
    code, out, _ = run("cash")
    rows = {row[0]: row for row in table_rows(out)}
    assert code == 0
    assert rows["USD"][-2:] == ["182,400.00", "136,741.88"]
    assert rows["JPY"][-2:] == ["0", "0.00"]
    assert out.splitlines()[-1].split() == ["Total", format_money(valuation.cash_total.amount)]

    _, out, _ = run("cash", "--currency", "usd")
    assert out.splitlines()[1] == "USD cash statement up to 2026-10-30"
    assert table_rows(out)[-1][-2:] == ["-281,821.76", "182,400.00"]


def test_export(tmp_path):
    code, out, _ = run("export")
    rows = list(csv.DictReader(io.StringIO(out)))
    assert code == 0
    assert tuple(rows[0]) == COLUMNS and len(rows) == 76
    assert (rows[0]["side"], rows[0]["realised"], rows[0]["settlement"]) == ("buy", "", "-243010.00")
    sale = next(row for row in rows if row["trade_id"] == "T0070")
    assert (sale["cost"], sale["realised"], sale["fx_rate"], sale["realised_base"]) == (
        "207528.71", "15259.84", "0.733245", "11189.21")

    target = tmp_path / "ledger.csv"
    code, written, err = run("export", "-o", str(target))
    assert (code, written) == (0, "")
    assert f"folio-ledger: note: wrote 76 trades to {target}" in err
    assert target.read_text(encoding="utf-8") == out


def test_reconcile_catches_a_mistyped_price(data_copy):
    trades = data_copy / "trades.csv"
    trades.write_text(trades.read_text().replace("T0073,2026-09-15,ADZM,buy,1510,184.42",
                                                 "T0073,2026-09-15,ADZM,buy,1510,184.24"))
    code, out, _ = run("reconcile", data=data_copy)
    assert code == 1
    assert out.splitlines() == [
        "DIFF ADZM: open lot 2026-09-15 1,510 @ 184.24 in trades.csv only",
        "DIFF ADZM: open lot 2026-09-15 1,510 @ 184.42 in positions.json only",
        "DIFF cash USD: 182,671.80 in the ledger, 182,400.00 in positions.json",
    ]


def test_folio_does_not_need_the_ledger_files(data_copy):
    for name in LEDGER_FILES:
        (data_copy / name).unlink()
    out, err = io.StringIO(), io.StringIO()
    assert folio_main(["value", "--data-dir", str(data_copy)], out=out, err=err, today=TODAY) == 0
    code, out, err = run("trades", data=data_copy)
    assert (code, out) == (2, "")
    assert err.startswith("folio-ledger: error: data folder ")
    assert err.endswith("has no trades.csv, cash_flows.csv, which the ledger needs\n")


def test_bad_input_exits_2(data_copy):
    code, _, err = run("trades", "--instrument", "NOPE")
    assert (code, err) == (2, "folio-ledger: error: unknown instrument NOPE: it is not in instruments.csv\n")
    code, _, err = run("pnl", "--since", "2026-11-02")
    assert code == 2 and "--since 2026-11-02 is after the valuation date 2026-10-30" in err
    with open(data_copy / "trades.csv", "a") as handle:
        handle.write("T0077,2026-10-30,FRXL,sell,1,382.35,0,USD\n")
    code, _, err = run("cash", data=data_copy)
    assert code == 2
    assert err.startswith("folio-ledger: error: trades.csv:78: trade T0077: the sale of 1 FRXL on 2026-10-30 "
                          "is more than the 0 held")


def test_usage_errors_and_help(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["pnl", "--by", "rating"])
    assert caught.value.code == 2 and "invalid choice: 'rating'" in capsys.readouterr().err
    with pytest.raises(SystemExit) as caught:
        main(["cash", "--currency", "pounds"])
    assert caught.value.code == 2 and "invalid currency code 'POUNDS'" in capsys.readouterr().err
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0 and "reconcile" in capsys.readouterr().out


def test_python_dash_m_from_the_project_folder():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-m", "folio.ledger", "reconcile", "--as-of", "2026-10-30"],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("OK: 40 instruments")
