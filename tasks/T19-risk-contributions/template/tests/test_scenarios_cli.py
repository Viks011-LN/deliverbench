import io
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from folio.cli import main as folio_main
from folio.scenarios.cli import main
from folio.scenarios.scenario_file import read_scenarios

ROOT = Path(__file__).resolve().parent.parent
DATA = str(ROOT / "data")
TODAY = date(2026, 10, 30)
SAMPLE = read_scenarios(ROOT / "data" / "scenarios.toml")
NAMES = [scenario.name for scenario in SAMPLE]


def run(*argv, today=TODAY):
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), out=out, err=err, today=today)
    return code, out.getvalue(), err.getvalue()


def money(cell):
    return float(cell.replace(",", ""))


def test_list_shows_every_scenario_in_name_order():
    code, out, err = run("list", "--data-dir", DATA)
    assert (code, err) == (0, "")
    lines = out.splitlines()
    assert lines[0] == f"{len(SAMPLE)} scenarios in {Path(DATA) / 'scenarios.toml'}"
    assert lines[2].split() == ["Scenario", "Description"]
    assert [line.split()[0] for line in lines[4:]] == sorted(NAMES)


@pytest.mark.parametrize("by", ["sector", "currency", "kind"])
def test_run_by_each_dimension(by):
    code, out, err = run("run", "equity-sell-off", "--by", by, "--data-dir", DATA)
    assert (code, err) == (0, "")
    lines = out.splitlines()
    assert lines[:4] == ["Global Balanced (GBL-BAL)", "Valued 2026-10-30 in GBP", "",
                         "Scenario equity-sell-off: Equities fall 20%, the diversified equity funds 15%"]
    assert f"P&L by {by}" in lines
    assert lines[-1].startswith("NAV after the scenario: GBP ")
    total = next(line for line in lines if line.startswith("Total"))
    assert total.split()[1] == "38"


def test_run_default_groups_by_sector_and_matches_compare():
    _, out, _ = run("run", "dollar-slide", "--data-dir", DATA)
    assert "P&L by sector" in out
    total = next(line for line in out.splitlines() if line.startswith("Total")).split()
    _, compared, _ = run("compare", "--data-dir", DATA)
    row = next(line for line in compared.splitlines() if line.startswith("dollar-slide ")).split()
    assert total[-2:] == row[1:3]  # same P&L and share of NAV
    assert "Shocks: USD -12%" in out


def test_historical_run_names_its_window():
    _, out, _ = run("run", "worst-week", "--data-dir", DATA)
    shocks = next(line for line in out.splitlines() if line.startswith("Shocks: "))
    assert shocks.startswith("Shocks: worst 5-day move of the book, 2026-")
    _, out, _ = run("run", "worst-month-each", "--data-dir", DATA)
    assert "each over its own dates" in out


def test_compare_puts_the_worst_scenario_first():
    code, out, _ = run("compare", "--data-dir", DATA)
    assert code == 0
    lines = out.splitlines()
    assert lines[3].startswith("Scenario P&L, worst first; NAV before GBP ")
    rows = lines[6:]
    assert sorted(row.split()[0] for row in rows) == sorted(NAMES)
    pnl = [money(row.split()[1]) for row in rows]
    assert pnl == sorted(pnl)
    assert pnl[0] < 0


def test_options_before_or_after_the_command(tmp_path):
    copy = tmp_path / "mine.toml"
    copy.write_text("[scenarios.only]\nyield_bp = 50\n", encoding="utf-8")
    after = run("compare", "--data-dir", DATA, "--scenarios", str(copy))
    before = run("--scenarios", str(copy), "--data-dir", DATA, "compare")
    assert after == before
    assert after[0] == 0 and "only " in after[1] and "rates-up-100" not in after[1]


def test_export_to_stdout_and_to_a_file(tmp_path):
    code, out, err = run("export", "--data-dir", DATA)
    assert (code, err) == (0, "")
    lines = out.splitlines()
    assert lines[0].startswith("scenario,portfolio,as_of,instrument,")
    assert len(lines) == 1 + len(SAMPLE) * (38 + 3)  # every position and cash balance per scenario
    target = tmp_path / "stress.csv"
    code, out, err = run("export", "-o", str(target), "--data-dir", DATA)
    assert (code, out) == (0, "")
    assert f"folio-scenarios: note: wrote {len(lines) - 1} rows for {len(SAMPLE)} scenarios to {target}" in err
    assert target.read_text(encoding="utf-8").splitlines() == lines


def test_unknown_scenario_is_an_error():
    code, out, err = run("run", "equity-selloff", "--data-dir", DATA)
    assert (code, out) == (2, "")
    assert err == ("folio-scenarios: error: scenarios.toml has no scenario 'equity-selloff' "
                   "(did you mean equity-sell-off?); the list command shows them all\n")


def test_bad_scenario_file_is_an_error(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("[scenarios.oops]\nsector = { Technlogy = -10 }\n", encoding="utf-8")
    code, _, err = run("list", "--data-dir", DATA, "--scenarios", str(bad))
    assert code == 2
    assert err.startswith("folio-scenarios: error: bad.toml: scenario oops: sector 'Technlogy' is not in "
                          "instruments.csv (did you mean Technology?)")


def test_folio_itself_does_not_need_a_scenario_file(tmp_path):
    for name in ("instruments.csv", "positions.json", "prices.csv", "fx.csv"):
        shutil.copy(ROOT / "data" / name, tmp_path / name)
    assert folio_main(["value", "--data-dir", str(tmp_path), "--as-of", "2026-10-30"],
                      out=io.StringIO(), err=io.StringIO()) == 0
    code, _, err = run("list", "--data-dir", str(tmp_path))
    assert code == 2 and err.startswith("folio-scenarios: error: scenario file not found: ")


def test_notes_and_settings_come_from_folio():
    code, _, err = run("compare", "--data-dir", DATA, today=date(2026, 11, 19))
    assert code == 0
    assert "folio-scenarios: note: valuing as of 2026-10-30, the last date in the price file" in err
    _, out, _ = run("run", "rates-up-100", "--data-dir", DATA, "--set", "report.money_places=0")
    total = next(line for line in out.splitlines() if line.startswith("Total"))
    assert "." not in total.split()[2]
    code, _, err = run("list", "--data-dir", DATA, "--set", "report.no_such_key=1")
    assert code == 2 and err.startswith("folio-scenarios: error: ")


def test_unknown_grouping_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["run", "worst-week", "--by", "rating", "--data-dir", DATA])
    assert caught.value.code == 2
    assert "invalid choice: 'rating'" in capsys.readouterr().err


def test_python_dash_m_from_the_project_folder():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-m", "folio.scenarios", "compare", "--as-of", "2026-10-30"],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "Scenario P&L, worst first" in result.stdout
