import dataclasses
from decimal import Decimal

import pytest

from folio.config.loader import DEFAULTS_PATH, load_settings, parse_override, read_toml
from folio.config.settings import SECTIONS, settings_from_dict
from folio.errors import ConfigError


def test_defaults(settings):
    assert settings.limits.sector_max_share == Decimal("0.25")
    assert isinstance(settings.limits.sector_max_share, Decimal)
    assert settings.limits.disabled == ()
    assert settings.risk.var_confidence == 0.99
    assert settings.report.show_cash is True
    assert settings.fx.base_currency == "GBP"


def test_defaults_file_and_dataclasses_list_the_same_keys():
    defaults = read_toml(DEFAULTS_PATH)
    assert set(defaults) == set(SECTIONS)
    for section, cls in SECTIONS.items():
        assert set(defaults[section]) == {field.name for field in dataclasses.fields(cls)}, section


def test_set_overrides_are_typed(tmp_path):
    settings = load_settings(
        overrides=["limits.sector_max_share=0.3", "fx.base_currency=USD", "report.show_cash=false",
                   "limits.disabled=var_share,name_share", "risk.var_lookback_days=40"],
        cwd=tmp_path,
    )
    assert settings.limits.sector_max_share == Decimal("0.3")
    assert settings.fx.base_currency == "USD"
    assert settings.report.show_cash is False
    assert settings.limits.disabled == ("var_share", "name_share")
    assert settings.risk.var_lookback_days == 40


def test_unknown_setting_suggests_the_right_name(tmp_path):
    with pytest.raises(ConfigError, match=r"did you mean limits\.sector_max_share\?"):
        load_settings(overrides=["limits.sector_max_shar=0.3"], cwd=tmp_path)
    with pytest.raises(ConfigError, match=r"unknown section \[limit\] \(did you mean limits\?\)"):
        load_settings(overrides=["limit.sector_max_share=0.3"], cwd=tmp_path)


@pytest.mark.parametrize("text", ["limits", "sector_max_share=0.3", "limits.=1", "a.b.c=1"])
def test_malformed_override(text):
    with pytest.raises(ConfigError, match="--set"):
        parse_override(text)


@pytest.mark.parametrize("override, message", [
    ("report.top_n=abc", "report.top_n must be a whole number"),
    ("limits.sector_max_share=1.5", "limits.sector_max_share must be a fraction of NAV"),
    ("risk.var_confidence=1.2", "risk.var_confidence must be"),
    ("risk.min_observations=90", r"between 2 and risk.var_lookback_days \(60\)"),
    ("fx.base_currency=pounds", "fx.base_currency: invalid currency code"),
    ("report.show_cash=1", "report.show_cash must be true or false"),
])
def test_bad_values_name_the_setting(tmp_path, override, message):
    with pytest.raises(ConfigError, match=message):
        load_settings(overrides=[override], cwd=tmp_path)


def test_local_file_sits_between_defaults_and_set(tmp_path):
    (tmp_path / "folio.toml").write_text("[limits]\nsector_max_share = 0.4\nname_max_share = 0.1\n")
    settings = load_settings(cwd=tmp_path)
    assert settings.limits.sector_max_share == Decimal("0.4")
    assert settings.limits.var_max_share == Decimal("0.03")  # untouched default
    settings = load_settings(overrides=["limits.name_max_share=0.05"], cwd=tmp_path)
    assert settings.limits.name_max_share == Decimal("0.05")


def test_explicit_config_file(tmp_path):
    path = tmp_path / "desk.toml"
    path.write_text('[fx]\nbase_currency = "EUR"\n')
    assert load_settings(config_path=path, cwd=tmp_path).fx.base_currency == "EUR"
    with pytest.raises(ConfigError, match="settings file not found"):
        load_settings(config_path=tmp_path / "missing.toml")


def test_settings_from_dict_requires_every_field():
    data = read_toml(DEFAULTS_PATH)
    del data["limits"]["var_max_share"]
    with pytest.raises(ConfigError, match="limits.var_max_share has no value"):
        settings_from_dict(data)
