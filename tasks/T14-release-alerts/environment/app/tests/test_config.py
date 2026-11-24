import pytest

from alertd.config import flatten, load_defaults, load_settings, type_of, unflatten
from alertd.errors import ConfigError


def test_flatten_and_unflatten():
    nested = {"a": {"b": 1, "c": {"d": [1, 2]}}, "e": "x"}
    flat = flatten(nested)
    assert flat == {"a.b": 1, "a.c.d": [1, 2], "e": "x"}
    assert unflatten(flat) == nested


def test_every_default_has_a_supported_type():
    for key, value in load_defaults().items():
        assert type_of(value) in {"number", "string", "boolean", "list"}, key


def test_the_defaults_alone(defaults):
    assert defaults.get("alerts.daily_cap") == 25
    assert defaults.get("price_move.threshold_pct") == 1.5
    assert defaults.source("alerts.daily_cap") == "default"
    assert defaults.set_in_file() == []


def test_a_config_file_sets_only_what_it_changes(make_settings):
    settings = make_settings("[alerts]\ndaily_cap = 12\n")
    assert settings.get("alerts.daily_cap") == 12
    assert settings.source("alerts.daily_cap").endswith("settings.toml")
    assert settings.get("alerts.cooldown_minutes") == 30
    assert settings.set_in_file() == ["alerts.daily_cap"]


def test_an_unknown_key_is_an_error(make_settings):
    with pytest.raises(ConfigError, match="unknown key alerts.daily_limit"):
        make_settings("[alerts]\ndaily_limit = 12\n")


def test_an_unknown_table_is_an_error(make_settings):
    with pytest.raises(ConfigError, match="unknown key weather.threshold"):
        make_settings("[weather]\nthreshold = 1\n")


def test_a_table_where_a_value_is_declared_is_an_error(make_settings):
    with pytest.raises(ConfigError, match="unknown key"):
        make_settings("[price_move.threshold_pct]\nhigh = 1.0\n")


def test_integers_and_decimals_are_both_numbers(make_settings):
    settings = make_settings("[price_move]\nthreshold_pct = 2\n[alerts]\ndaily_cap = 12.0\n")
    assert settings.get("price_move.threshold_pct") == 2
    assert settings.get("alerts.daily_cap") == 12.0


@pytest.mark.parametrize("text", [
    '[alerts]\ndaily_cap = "twenty"\n',
    "[alerts]\ndaily_cap = true\n",
    "[news]\nwatchlist = [1, 2]\n",
    '[news]\nwatchlist = "ORVK"\n',
    "[alerts]\ncooldown_minutes = -5\n",
    '[alerts]\nquiet_start = "10pm"\n',
])
def test_a_value_of_the_wrong_type_is_an_error(make_settings, text):
    with pytest.raises(ConfigError):
        make_settings(text)


def test_a_file_that_is_not_toml(make_settings):
    with pytest.raises(ConfigError, match="not valid TOML"):
        make_settings("[alerts\n")


def test_a_named_file_must_exist(tmp_path):
    with pytest.raises(ConfigError, match="cannot read"):
        load_settings(tmp_path / "missing.toml")


def test_section_gives_a_kinds_settings_as_a_copy(make_settings):
    settings = make_settings("[news]\nwatchlist = [\"ORVK\"]\n")
    section = settings.section("news")
    assert section["watchlist"] == ["ORVK"]
    section["watchlist"].append("KSVH")
    assert settings.get("news.watchlist") == ["ORVK"]
    assert settings.section("nothing") == {}


def test_the_desks_config_loads(root):
    settings = load_settings(root / "config" / "alerts.toml")
    assert settings.get("alerts.daily_cap") == 20
    assert settings.get("alerts.quiet_end") == "07:00"
    assert settings.get("alerts.quiet_start") == "22:00"
    assert "ORVK" in settings.get("news.watchlist")
