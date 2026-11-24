import csv
import io
import os
import shutil
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from folio import cli as folio_cli
from folio.benchmark.cli import main
from folio.benchmark.csv_export import COLUMNS
from folio.calc import exposure
from folio.calc.exposure import Dimension
from folio.data.folder import FILES

ROOT = Path(__file__).resolve().parent.parent
DATA = str(ROOT / "data")
TODAY = date(2026, 10, 30)


def run(*argv, entry=main):
    out, err = io.StringIO(), io.StringIO()
    code = entry(list(argv), out=out, err=err, today=TODAY)
    return code, out.getvalue(), err.getvalue()


def table_rows(text, title):
    """The body rows of the table under ``title``, up to its closing rule or a blank line."""
    lines = text.splitlines()
    start = lines.index(title) + 3
    end = next((i for i in range(start, len(lines)) if not lines[i] or lines[i].startswith("---")), len(lines))
    return lines[start:end]


def test_active_by_sector():
    code, out, err = run("active", "--by", "sector", "--data-dir", DATA)
    assert (code, err) == (0, "")
    lines = out.splitlines()
    assert lines[:2] == ["Global Balanced (GBL-BAL)", "Valued 2026-10-30 in GBP"]
    assert lines[3] == "Active weights by sector against benchmark.csv (53 constituents)"
    assert lines[4].split() == ["Sector", "Held", "In", "index", "Book", "Index", "Active"]
    body = table_rows(out, lines[3])
    assert body[-1].split() == ["Cash", "3.25%", "0.00%", "+3.25%"]
    assert sum(1 for line in body if line.startswith("Cash ")) == 1
    assert lines[-1].split() == ["Total", "38", "53", "100.00%", "100.00%", "0.00%"]


def test_active_by_kind_and_currency():
    _, out, _ = run("active", "--by", "kind", "--data-dir", DATA)
    assert [row.split()[0] for row in table_rows(out, out.splitlines()[3])] == ["equity", "bond", "fund", "Cash"]
    _, out, _ = run("active", "--by", "currency", "--data-dir", DATA)
    body = table_rows(out, out.splitlines()[3])
    assert body[0].startswith("GBP ")  # the GBP cash counts as GBP exposure
    assert not any(row.startswith("Cash") for row in body)
    assert {"AUD", "CAD", "CHF"} <= {row.split()[0] for row in body}  # currencies only the index has


def test_active_per_holding():
    code, out, _ = run("active", "--data-dir", DATA)
    assert code == 0
    title = "Active weights by holding against benchmark.csv (53 constituents)"
    body = table_rows(out, title)
    assert len(body) == 62 + 3
    names = [row.split()[0] for row in body]
    assert names[-3:] == ["CASH"] * 3
    active = [Decimal(row.split()[-1].rstrip("%")) for row in body[:-3]]
    assert active == sorted(active, reverse=True)
    fraxley = next(row for row in body if row.startswith("FRXL "))  # in the index and instruments.csv, not held
    assert fraxley.split()[-3:] == ["0.00%", "2.10%", "-2.10%"]
    assert "Orvelle Networks Inc" in next(row for row in body if row.startswith("ORVL "))


def test_overlap():
    code, out, _ = run("overlap", "--top", "2", "--data-dir", DATA)
    assert code == 0
    lines = out.splitlines()
    assert lines[3] == "Overlap against benchmark.csv (53 constituents)"
    assert lines[4].startswith("Active share ") and lines[5].startswith("In common ")
    assert lines[6].split() == ["Book", "38", "instruments,", "29", "of", "them", "in", "the", "index"]
    over, under = table_rows(out, "Largest overweights"), table_rows(out, "Largest underweights")
    assert len(over) == len(under) == 2
    assert all(row.split()[-1].startswith("+") for row in over)
    assert all(row.split()[-1].startswith("-") for row in under)


def test_tracking_and_window():
    code, out, err = run("tracking", "--data-dir", DATA)
    assert (code, err) == (0, "")
    pairs = {line[:22].strip(): line[22:].strip() for line in out.splitlines()[4:]}
    assert out.splitlines()[3] == "Tracking against HGB6040"
    assert pairs["Window"].endswith("to 2026-10-30, 60 daily returns")
    assert pairs["Tracking error (ann.)"].endswith("%")
    assert set(pairs) >= {"Book return", "Index return", "Relative return", "Beta", "Worst relative day"}
    _, out, _ = run("tracking", "--window", "30", "--data-dir", DATA)
    assert "to 2026-10-30, 30 daily returns" in out


def test_tracking_by_sector_adds_the_split():
    code, out, _ = run("tracking", "--by", "sector", "--data-dir", DATA)
    assert code == 0
    title = next(line for line in out.splitlines() if line.startswith("Relative return by sector, "))
    body = table_rows(out, title)
    assert body[-1].startswith("Cash ")
    assert {"Government", "Technology", "Materials"} <= {row.split()[0] for row in body}
    relative = [line.split()[-1] for line in out.splitlines()
                if line.startswith("Relative return ") and line != title]
    assert len(relative) == 2 and relative[0] == relative[1]  # the split adds up to the figure above it
    assert any(line.startswith("Residual ") and "of the index priced" in line for line in out.splitlines())


def test_by_follows_the_core_dimensions(monkeypatch, capsys):
    with pytest.raises(SystemExit) as caught:
        main(["active", "--by", "weather", "--data-dir", DATA])
    assert caught.value.code == 2 and "invalid choice: 'weather'" in capsys.readouterr().err
    domicile = Dimension("domicile", "Domicile", lambda line: line.instrument.country)
    monkeypatch.setitem(exposure.DIMENSIONS, "domicile", domicile)  # as if added to folio.calc.exposure
    code, out, _ = run("active", "--by", "domicile", "--data-dir", DATA)
    assert code == 0 and "Active weights by domicile" in out
    assert {"US", "CH", "Cash"} <= {row.split()[0] for row in table_rows(out, out.splitlines()[3])}
    code, out, _ = run("tracking", "--by", "domicile", "--data-dir", DATA)
    assert code == 0 and "Relative return by domicile, " in out


def test_export_csv(tmp_path):
    code, out, _ = run("export", "--data-dir", DATA)
    assert code == 0
    rows = list(csv.DictReader(io.StringIO(out)))
    assert out.splitlines()[0] == ",".join(COLUMNS)
    assert len(rows) == 65
    assert [row["instrument"] for row in rows[:-3]] == sorted(row["instrument"] for row in rows[:-3])
    assert sum(Decimal(row["active_weight"]) for row in rows) == pytest.approx(0, abs=Decimal("0.0001"))
    zeta = next(row for row in rows if row["instrument"] == "ORVL")
    assert (zeta["book_weight"], zeta["index_weight"], zeta["active_weight"]) == ("0.000000", "0.030000", "-0.030000")
    target = tmp_path / "active.csv"
    code, out, err = run("export", "-o", str(target), "--data-dir", DATA)
    assert (code, out) == (0, "")
    assert f"folio-benchmark: note: wrote 65 rows to {target}" in err
    assert target.read_text().splitlines()[0] == ",".join(COLUMNS)


def test_options_before_or_after_the_command(tmp_path):
    weights = tmp_path / "index.csv"
    weights.write_text("id,weight\nADZM,0.5\nUKT34,0.5\n")
    after = run("overlap", "--benchmark", str(weights), "--data-dir", DATA, "--as-of", "2026-10-30")
    before = run("--benchmark", str(weights), "--data-dir", DATA, "--as-of", "2026-10-30", "overlap")
    assert after == before
    assert after[0] == 0 and "against index.csv (2 constituents)" in after[1]


def test_errors_exit_2_without_traceback(tmp_path):
    code, out, err = run("active", "--benchmark", str(tmp_path / "nowhere.csv"), "--data-dir", DATA)
    assert (code, out) == (2, "")
    assert err.startswith("folio-benchmark: error: benchmark weights file not found")
    bad = tmp_path / "bad.csv"
    bad.write_text("id,weight\nADZM,0.5\nUKT34,0.4\n")
    code, _, err = run("overlap", "--benchmark", str(bad), "--data-dir", DATA)
    assert code == 2 and "folio-benchmark: error: bad.csv: weights add up to 0.9, not 1" in err
    code, _, err = run("tracking", "--levels", str(ROOT / "data" / "prices.csv"), "--data-dir", DATA)
    assert code == 2 and "prices.csv:1: expected a date column and one level column" in err
    code, _, err = run("tracking", "--window", "10", "--data-dir", DATA)
    assert code == 2 and "only 10 daily returns in the window" in err


def test_core_commands_do_not_need_the_benchmark_files(tmp_path):
    for name in FILES.values():
        shutil.copy(ROOT / "data" / name, tmp_path / name)
    code, out, _ = run("value", "--data-dir", str(tmp_path), entry=folio_cli.main)
    assert code == 0 and out.startswith("Global Balanced (GBL-BAL)")
    code, _, err = run("active", "--data-dir", str(tmp_path))
    assert code == 2 and "benchmark weights file not found" in err


def test_python_dash_m_folio_benchmark():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-m", "folio.benchmark", "overlap", "--as-of", "2026-10-30"],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "Active share" in result.stdout
