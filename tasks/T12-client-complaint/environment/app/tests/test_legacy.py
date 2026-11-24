"""The deprecated modules still work for the scripts that import them."""

from decimal import Decimal

import pytest

from folio.calc import exposure
from folio.config.loader import load_settings
from folio.legacy import exposure_old, settings_v1


def test_v1_defaults_and_deprecation_warning():
    with pytest.deprecated_call():
        old = settings_v1.load_v1()
    assert old.max_share == 0.20
    assert old.base_currency == "GBP"
    assert old.decimals == 2


def test_v1_file_overrides_defaults(tmp_path):
    path = tmp_path / "folio.ini"
    path.write_text("[limits]\nmax_share = 0.3\n[general]\nbase_currency = eur\n")
    with pytest.deprecated_call():
        old = settings_v1.load_v1(str(path))
    assert old.max_share == 0.3
    assert old.base_currency == "EUR"
    with pytest.deprecated_call(), pytest.raises(FileNotFoundError):
        settings_v1.load_v1(str(tmp_path / "missing.ini"))
    with pytest.deprecated_call():
        broken = settings_v1.load_v1(text="[limits]\nmax_share = 2\n")
    with pytest.raises(ValueError, match="max_share"):
        broken.max_share


def test_v1_migrates_to_v2_overrides(tmp_path):
    with pytest.deprecated_call():
        old = settings_v1.load_v1(text="[limits]\nmax_share = 0.15\n")
    settings = load_settings(overrides=old.to_v2_overrides(), cwd=tmp_path)
    assert settings.limits.sector_max_share == Decimal("0.15")
    assert settings.limits.name_max_share == Decimal("0.15")
    assert settings.report.money_places == 2


def test_old_sector_exposure_ignores_fx_and_cash(small_valuation):
    quantities = {"AAA": 1000, "BBB": 10000, "CCC": 2000}
    prices = {"AAA": 12, "BBB": 100, "CCC": 2}
    sectors = {"AAA": "Technology", "BBB": "Government", "CCC": "Diversified"}
    with pytest.deprecated_call():
        shares = exposure_old.exposure_by_sector(quantities, prices, sectors)
    # BBB counts as 1,000,000 "units of money": no per-100 quoting, no USD->GBP.
    assert shares["Government"] == pytest.approx(1_000_000 / 1_016_000)
    assert sum(shares.values()) == pytest.approx(1.0)
    new = exposure.by_sector(small_valuation)
    assert new.share_of("Government") == Decimal("0.32")
    assert exposure_old.max_share_breaches(shares, 0.01) == [
        ("Government", pytest.approx(0.984, abs=1e-3)),
        ("Technology", pytest.approx(0.0118, abs=1e-4)),
    ]
    with pytest.deprecated_call(), pytest.raises(KeyError, match="no price for CCC"):
        exposure_old.exposure_by_sector({"CCC": 1}, {}, sectors)
