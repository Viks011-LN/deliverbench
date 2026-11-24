"""python -m folio.compliance: the three commands on the sample data, and how they fail."""

import io
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from folio import cli as folio_cli
from folio.compliance.cli import main
from folio.data.folder import FILES

ROOT = Path(__file__).resolve().parent.parent
DATA = str(ROOT / "data")
TODAY = date(2026, 10, 30)
TNSL = "VIOLATION restricted_holdings TNSL: 0.9% held, restricted since 2026-10-01 (Thermal coal over 10% of revenue)"

# A stricter mandate for the same book, without a restricted list.
STRICT = """\
[mandate]
portfolio = "GBL-BAL"

[guidelines.issuer_max_share]
value = 0.06

[guidelines.max_positions]
value = 30

[guidelines.restricted_holdings]
enabled = false
"""


def run(*argv, today=TODAY):
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), out=out, err=err, today=today)
    return code, out.getvalue(), err.getvalue()


def data_folder(tmp_path, *extra):
    """A copy of the folio input files, plus the ``extra`` files named, in tmp_path/data."""
    folder = tmp_path / "data"
    folder.mkdir()
    for name in list(FILES.values()) + list(extra):
        shutil.copy(ROOT / "data" / name, folder / name)
    return str(folder)


def test_check_reports_the_restricted_holding_and_exits_1():
    assert run("check", "--data-dir", DATA) == (1, TNSL + "\n", "")


def test_check_explain_shows_the_headroom_of_every_guideline():
    code, out, _ = run("check", "--explain", "--data-dir", DATA)
    lines = out.splitlines()
    assert code == 1 and lines[0] == TNSL
    assert lines[2] == "Headroom (tightest subject of each guideline)"
    assert lines[3].split() == ["Guideline", "Tightest", "Actual", "Limit", "Headroom", "In", "GBP"]
    rows = {line.split()[0]: line.split()[1:] for line in lines[5:]}
    assert rows["issuer_max_share"] == ["ADZM", "6.2%", "max", "7.0%", "0.8%", "156,588.12"]
    assert rows["country_max_share"][:2] == ["US", "26.4%"]
    assert rows["govt_min_share"][-4:] == ["min", "15.0%", "0.6%", "110,558.36"]
    assert rows["max_positions"] == ["positions", "38", "max", "40", "2"]
    assert rows["restricted_holdings"] == ["TNSL", "0.9%", "none", "held", "-0.9%", "-180,010.00"]
    assert not any(line.startswith("OK") for line in lines)


def test_check_passes_before_the_restriction_starts():
    assert run("check", "--data-dir", DATA, "--as-of", "2026-09-30") == (0, "OK: 7 guidelines checked\n", "")
    code, out, _ = run("check", "--explain", "--data-dir", DATA, "--as-of", "2026-09-30")
    assert code == 0 and out.endswith("\n\nOK: 7 guidelines checked\n")
    assert "restricted_holdings  no restricted holdings" in out


def test_an_issuer_restriction_catches_shares_and_bonds():
    code, out, _ = run("check", "--data-dir", DATA, "--as-of", "2026-07-15")
    assert code == 1
    assert [line.split(":")[0] for line in out.splitlines()] == [
        "VIOLATION restricted_holdings MXTB", "VIOLATION restricted_holdings MXTB29"]
    assert "issuer MXTB restricted since 2026-06-15" in out


def test_guidelines_option_replaces_the_mandate(tmp_path):
    strict = tmp_path / "strict.toml"
    strict.write_text(STRICT)
    code, out, err = run("check", "--data-dir", DATA, "--guidelines", str(strict))
    assert code == 1
    assert out.splitlines() == [
        "VIOLATION issuer_max_share ADZM: 6.2% > 6.0%",
        "VIOLATION max_positions positions: 38 > 30",
    ]
    assert err == "folio-compliance: note: restricted_holdings is switched off in strict.toml\n"


def test_options_before_or_after_the_command_and_report_settings():
    before = run("--data-dir", DATA, "--as-of", "2026-10-30", "check")
    after = run("check", "--data-dir", DATA, "--as-of", "2026-10-30")
    assert before == after
    _, out, _ = run("check", "--data-dir", DATA, "--set", "report.percent_places=2")
    assert out.startswith("VIOLATION restricted_holdings TNSL: 0.90% held")


def test_mandate_command():
    code, out, err = run("mandate", "--data-dir", DATA)
    lines = out.splitlines()
    assert (code, err) == (0, "")
    assert lines[:3] == ["Mandate for Global Balanced (GBL-BAL)", "Client: Ellesmere Staff Pension Scheme",
                         "From guidelines.toml: 7 guidelines, 7 in force"]
    assert lines[4].split() == ["Guideline", "Covers", "Limit", "Status", "Note"]
    assert lines[6].startswith("issuer_max_share ") and "max 7.0%  in force  Schedule 2, para 1" in lines[6]
    assert lines[-1].startswith("restricted_holdings ") and "none held" in lines[-1]


def test_mandate_command_shows_guidelines_switched_off(tmp_path):
    strict = tmp_path / "strict.toml"
    strict.write_text(STRICT)
    _, out, _ = run("mandate", "--data-dir", DATA, "--guidelines", str(strict))
    lines = out.splitlines()
    assert lines[1:3] == ["Client: GBL-BAL", "From strict.toml: 3 guidelines, 2 in force"]
    assert lines[-1].startswith("restricted_holdings ") and lines[-1].endswith("none held  off")


def test_restricted_command():
    code, out, err = run("restricted", "--data-dir", DATA)
    lines = out.splitlines()
    assert (code, err) == (0, "")
    assert lines[:4] == ["Global Balanced (GBL-BAL)", "Valued 2026-10-30 in GBP", "", "Restricted holdings"]
    assert lines[6].startswith("TNSL        Tansley Mining plc ") and lines[6].endswith("Thermal coal over 10% of revenue")
    coming = lines.index("Coming onto the list")
    assert lines[coming + 3].startswith("BRXS30 ") and "issuer Brixham Shipping  2026-11-16" in lines[coming + 3]
    assert lines[-1] == "restricted.csv on 2026-10-30: 5 entries, 3 in force, 1 lifted, 1 not yet in force"


def test_restricted_command_with_nothing_held():
    code, out, _ = run("restricted", "--data-dir", DATA, "--as-of", "2026-09-30")
    assert code == 0 and "Restricted holdings\nNone.\n" in out
    assert "TNSL " in out.split("Coming onto the list")[1]


def test_compliance_files_are_needed_only_by_compliance(tmp_path):
    folder = data_folder(tmp_path)
    code, out, err = run("check", "--data-dir", folder)
    assert (code, out) == (2, "")
    assert err == (f"folio-compliance: error: no guidelines.toml in {folder}; "
                   f"give the client's mandate with --guidelines FILE\n")
    code, _, err = run("restricted", "--data-dir", folder)
    assert code == 2 and err.startswith("folio-compliance: error: restricted list not found")
    assert folio_cli.main(["value", "--data-dir", folder], out=io.StringIO(), err=io.StringIO(), today=TODAY) == 0


def test_restricted_list_is_read_only_when_its_guideline_is_in_force(tmp_path):
    folder = data_folder(tmp_path, "guidelines.toml")
    code, _, err = run("check", "--data-dir", folder)
    assert code == 2 and "guidelines.toml has restricted_holdings in force but there is no" in err
    strict = tmp_path / "strict.toml"
    strict.write_text(STRICT)
    code, out, _ = run("check", "--data-dir", folder, "--guidelines", str(strict))
    assert code == 1 and "restricted" not in out


def test_errors_exit_2_without_traceback(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text('[mandate]\nportfolio = "GBL-BAL"\n\n[guidelines.issuer_max_share]\nvalue = 1.5\n')
    assert run("check", "--data-dir", DATA, "--guidelines", str(bad)) == (2, "", (
        "folio-compliance: error: bad.toml: guidelines.issuer_max_share.value must be a fraction of NAV "
        "above 0 and at most 1, got 1.5\n"))
    other = tmp_path / "other.toml"
    other.write_text('[mandate]\nportfolio = "INC-EQ"\n\n[guidelines.max_positions]\nvalue = 40\n')
    code, _, err = run("mandate", "--data-dir", DATA, "--guidelines", str(other))
    assert code == 2 and "other.toml is the mandate for portfolio INC-EQ, but the data folder holds GBL-BAL" in err
    code, _, err = run("check", "--data-dir", DATA, "--guidelines", str(tmp_path / "missing.toml"))
    assert code == 2 and err.startswith("folio-compliance: error: mandate file not found")
    code, _, err = run("check", "--data-dir", str(tmp_path / "nowhere"))
    assert code == 2 and err.startswith("folio-compliance: error: data folder not found")


def test_usage_errors_exit_through_argparse(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["check", "--explian", "--data-dir", DATA])
    assert caught.value.code == 2
    assert "folio-compliance: error: unrecognized arguments: --explian" in capsys.readouterr().err


def test_python_dash_m_folio_compliance():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-m", "folio.compliance", "mandate", "--as-of", "2026-10-30"],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("Mandate for Global Balanced (GBL-BAL)\n")
