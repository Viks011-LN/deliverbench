import io
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from folio.cli import main

ROOT = Path(__file__).resolve().parent.parent
DATA = str(ROOT / "data")
TODAY = date(2026, 11, 19)  # after the last price date, as on a real desk


def run(*argv, today=TODAY):
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), out=out, err=err, today=today)
    return code, out.getvalue(), err.getvalue()


def test_value_defaults_to_the_last_price_date():
    code, out, err = run("value", "--data-dir", DATA)
    assert code == 0
    assert out.startswith("Global Balanced (GBL-BAL)\nValued 2026-10-30 in GBP\n")
    assert "folio: note: valuing as of 2026-10-30, the last date in the price file (asked for 2026-11-19)" in err


def test_options_before_or_after_the_command():
    after = run("report", "--by", "kind", "--data-dir", DATA, "--as-of", "2026-10-30")
    before = run("--data-dir", DATA, "--as-of", "2026-10-30", "report", "--by", "kind")
    assert after == before
    assert after[0] == 0 and after[2] == ""


def test_report_by_sector():
    code, out, _ = run("report", "--by", "sector", "--data-dir", DATA, "--as-of", "2026-10-30")
    lines = out.splitlines()
    assert code == 0
    assert lines[3] == "Exposure by sector"
    assert lines[4].split() == ["Sector", "Positions", "Market", "value", "Weight"]
    assert lines[6].startswith("Government ")
    assert lines[-1].startswith("Total") and lines[-1].endswith("100.0%")
    assert sum(1 for line in lines if line.startswith("Cash ")) == 1


def test_value_by_weight_and_risk_by_currency():
    _, out, _ = run("value", "--sort", "weight", "--data-dir", DATA, "--as-of", "2026-10-30")
    assert out.splitlines()[5].startswith("GEIF ")
    code, out, _ = run("risk", "--by", "currency", "--data-dir", DATA, "--as-of", "2026-10-30")
    assert code == 0 and "Expected shortfall 99% 1d by currency" in out


def test_unknown_breakdown_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["report", "--by", "rating", "--data-dir", DATA])
    assert caught.value.code == 2
    assert "invalid choice: 'rating'" in capsys.readouterr().err


def test_export_csv_and_json(tmp_path):
    code, out, _ = run("export", "--data-dir", DATA)
    assert code == 0
    assert out.splitlines()[0].startswith("portfolio,as_of,instrument,name,kind,sector")
    assert len(out.splitlines()) == 39
    target = tmp_path / "positions.json"
    code, out, err = run("export", "--format", "json", "-o", str(target), "--data-dir", DATA)
    assert code == 0 and out == ""
    assert f"wrote 38 positions to {target}" in err
    assert json.loads(target.read_text())["base_currency"] == "GBP"


def test_check_limits_passes_on_the_sample():
    code, out, _ = run("check-limits", "--data-dir", DATA)
    assert code == 0
    assert out.startswith("OK: ") and out.endswith(" rules checked, no breaches\n")
    _, verbose, _ = run("check-limits", "-v", "--data-dir", DATA)
    assert "ok sector_share Government: 21.1% <= 25.0%" in verbose.splitlines()


def test_check_limits_reports_breaches_and_exits_1():
    code, out, _ = run("check-limits", "--data-dir", DATA, "--set", "limits.sector_max_share=0.15",
                       "--set", "limits.currency_max_share=0.25")
    assert code == 1
    assert out.splitlines() == [
        "BREACH sector_share Government: 21.1% > 15.0%",
        "BREACH sector_share Technology: 16.4% > 15.0%",
        "BREACH currency_share USD: 29.6% > 25.0%",
    ]


def test_set_before_the_command_is_kept():
    code, out, _ = run("--set", "limits.sector_max_share=0.2", "check-limits", "--data-dir", DATA,
                       "--set", "limits.disabled=var_share")
    assert code == 1
    assert out == "BREACH sector_share Government: 21.1% > 20.0%\n"


def test_errors_exit_2_without_traceback(tmp_path):
    code, out, err = run("value", "--data-dir", str(tmp_path / "nowhere"))
    assert (code, out) == (2, "")
    assert err.startswith("folio: error: data folder not found")
    code, _, err = run("value", "--data-dir", DATA, "--set", "limits.sector_max_shar=0.3")
    assert code == 2 and "did you mean limits.sector_max_share?" in err
    code, _, err = run("check-limits", "--data-dir", DATA, "--set", "limits.disabled=nonsense")
    assert code == 2 and "unknown rule(s) nonsense" in err


def test_python_dash_m_from_the_project_folder():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-m", "folio", "report", "--as-of", "2026-10-30"],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "Exposure by sector" in result.stdout
