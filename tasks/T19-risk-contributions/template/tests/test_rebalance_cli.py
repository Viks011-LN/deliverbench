"""``python -m folio.rebalance`` on the sample data."""

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
from folio.rebalance.cli import main
from folio.rebalance.export import COLUMNS

ROOT = Path(__file__).resolve().parent.parent
DATA = str(ROOT / "data")
TODAY = date(2026, 10, 30)
TRADES_TITLE = "Proposed trades (minimum ticket GBP 25,000.00, cash buffer 1.0% of NAV)"


def run(*argv, today=TODAY, entry=main):
    out, err = io.StringIO(), io.StringIO()
    code = entry(list(argv), out=out, err=err, today=today)
    return code, out.getvalue(), err.getvalue()


def trade_rows(report, title=TRADES_TITLE):
    """The rows of the trade table in a propose report, split into cells."""
    lines = report.splitlines()
    rows = []
    for line in lines[lines.index(title) + 3:]:
        if not line:
            break
        rows.append(line.split())
    return rows


def test_drift_on_the_sample():
    code, out, err = run("drift", "--data-dir", DATA)
    lines = out.splitlines()
    assert (code, err) == (0, "")
    assert lines[:4] == ["Global Balanced (GBL-BAL)", "Valued 2026-10-30 in GBP", "", "Drift from the model weights"]
    assert lines[6].split() == ["Technology", "sector", "6", "16.4%", "15.0%", "1.0%", "+1.4%", "outside"]
    assert lines[-3].split() == ["Cash", "cash", "3.3%", "4.0%", "1.0%", "-0.7%"]
    assert lines[-1] == "5 of 10 targets outside their band."


def test_propose_on_the_sample():
    code, out, err = run("propose", "--data-dir", DATA)
    assert (code, err) == (0, "")
    rows = trade_rows(out)
    sides = [row[0] for row in rows]
    assert sides == sorted(sides, key=["sell", "buy"].index) and "buy" in sides
    assert rows[0] == ["sell", "GEIF", "fund", "GBP", "59,382", "3.4303", "203,698.07", "6.0%", "5.0%", "GEIF"]
    lines = out.splitlines()
    left_out = lines[lines.index("Left out") + 3].split()
    assert left_out[:4] == ["JGB30", "sell", "4,000,000", "20,964.04"]
    assert "JPY ends below zero: buy it against another currency before the trades settle." in lines
    assert lines[-1] == "Every target is inside its band."


def test_cash_buffer_and_minimum_ticket_from_the_command_line():
    code, out, _ = run("propose", "--data-dir", DATA, "--cash-buffer", "0.05", "--min-ticket", "10000")
    assert code == 0
    title = "Proposed trades (minimum ticket GBP 10,000.00, cash buffer 5.0% of NAV)"
    assert "JGB30" in [row[1] for row in trade_rows(out, title)]
    assert "Left out" not in out
    assert any(line.startswith("Buys cut to ") and line.endswith(" to keep 5.0% of NAV in cash.")
               for line in out.splitlines())
    assert "Cash after: 5.0% of NAV (model 4.0%, buffer 5.0%)." in out


def test_options_before_or_after_the_command():
    targets = str(ROOT / "data" / "targets.csv")
    after = run("propose", "--data-dir", DATA, "--targets", targets, "--as-of", "2026-10-30")
    before = run("--data-dir", DATA, "--targets", targets, "--as-of", "2026-10-30", "propose")
    assert after == before
    assert after[0] == 0


def test_export_lists_the_proposed_trades(tmp_path):
    code, out, _ = run("export", "--data-dir", DATA)
    assert code == 0
    assert out.splitlines()[0] == ",".join(COLUMNS)
    rows = list(csv.DictReader(io.StringIO(out)))
    _, report, _ = run("propose", "--data-dir", DATA)
    assert [(row["side"], row["instrument"]) for row in rows] == [(row[0], row[1]) for row in trade_rows(report)]

    target = tmp_path / "trades.csv"
    code, out, err = run("export", "-o", str(target), "--data-dir", DATA, "--min-ticket", "0")
    assert (code, out) == (0, "")
    written = list(csv.DictReader(target.read_text(encoding="utf-8").splitlines()))
    assert f"folio-rebalance: note: wrote {len(written)} trades to {target}" in err
    assert len(written) == len(rows) + 1  # JGB30 clears a ticket of 0


def test_the_last_price_date_note_uses_the_rebalance_prefix():
    code, _, err = run("drift", "--data-dir", DATA, today=date(2026, 11, 19))
    assert code == 0
    assert err == ("folio-rebalance: note: valuing as of 2026-10-30, the last date in the price file "
                   "(asked for 2026-11-19)\n")


def test_rebalance_files_are_only_needed_by_rebalance(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    for name in ("instruments.csv", "positions.json", "prices.csv", "fx.csv"):
        shutil.copy(ROOT / "data" / name, folder / name)
    assert run("value", "--data-dir", str(folder), entry=folio_main)[0] == 0
    code, out, err = run("drift", "--data-dir", str(folder))
    assert (code, out) == (2, "")
    assert err.startswith("folio-rebalance: error: targets file not found: ")
    shutil.copy(ROOT / "data" / "targets.csv", folder / "targets.csv")
    assert run("drift", "--data-dir", str(folder))[0] == 0
    code, _, err = run("propose", "--data-dir", str(folder))
    assert code == 2 and err.startswith("folio-rebalance: error: dealing rules file not found: ")


def test_bad_input_files_exit_2(tmp_path):
    targets = tmp_path / "model.csv"
    targets.write_text("scope,key,weight,band\nsector,Technology,0.5,0.01\ncash,,0.4,0.01\n", encoding="utf-8")
    code, _, err = run("drift", "--data-dir", DATA, "--targets", str(targets))
    assert code == 2
    assert err == "folio-rebalance: error: model.csv: weights add up to 0.9, not 1 (the cash target counts too)\n"

    rules = tmp_path / "rules.toml"
    rules.write_text("min_tiket = 5000\n", encoding="utf-8")
    code, _, err = run("propose", "--data-dir", DATA, "--rules", str(rules))
    assert code == 2 and "rules.toml: unknown key min_tiket (did you mean min_ticket?)" in err


@pytest.mark.parametrize("option, value, message", [
    ("--cash-buffer", "1.2", "the cash buffer must be a share of NAV from 0 up to 1"),
    ("--cash-buffer", "half", "cash buffer 'half' is not a number"),
    ("--min-ticket", "-1", "minimum ticket must be 0 or more"),
])
def test_bad_options_are_usage_errors(capsys, option, value, message):
    with pytest.raises(SystemExit) as caught:
        main(["propose", option, value, "--data-dir", DATA])
    assert caught.value.code == 2
    assert message in capsys.readouterr().err


def test_python_dash_m_folio_rebalance():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-m", "folio.rebalance", "--help"],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("usage: folio-rebalance ")
    for command in ("drift", "propose", "export"):
        assert command in result.stdout
