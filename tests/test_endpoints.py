"""F02: setups load by name, and setup cards never carry an address."""
from __future__ import annotations

from pathlib import Path

import pytest

from dbench.endpoints import SetupError, get_setup, load_setups, setup_id

REPO = Path(__file__).resolve().parents[1]
HOST_IP = ".".join(["10", "1", "2", "3"])

GOOD = f"""
[alpha]
url = "http://{HOST_IP}:8000/v1"
model = "alpha-model"
engine = "SGLang"
quantisation = "MXFP4 experts, FP8 dense"
context_length = 1048576
reasoning_effort = "high"
temperature = 1.0

[beta]
url = "http://gpubox:8000/v1"
model = "beta-model"
"""


def write(tmp_path, text):
    path = tmp_path / "endpoints.local.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_committed_example_loads():
    setups = load_setups(REPO / "endpoints.example.toml")
    assert "example-local" in setups


def test_setup_loads_by_name(tmp_path):
    setup = get_setup("alpha", write(tmp_path, GOOD))
    assert setup.model == "alpha-model"
    assert setup.context_length == 1048576


def test_card_has_settings_but_no_address(tmp_path):
    setup = get_setup("alpha", write(tmp_path, GOOD))
    card = setup.card("abc123")
    assert card["engine"] == "SGLang" and card["reasoning_effort"] == "high" and card["setup_id"] == "abc123"
    assert "url" not in card and "api_key_env" not in card
    assert HOST_IP not in str(card)


def test_card_refuses_an_address_hidden_in_another_field(tmp_path):
    text = GOOD.replace('engine = "SGLang"', f'engine = "SGLang on {HOST_IP}"')
    with pytest.raises(SetupError, match="address"):
        get_setup("alpha", write(tmp_path, text)).card("x")


def test_card_refuses_the_host_name_in_another_field(tmp_path):
    text = GOOD.replace('model = "beta-model"', 'model = "beta-model"\nnotes = "served from gpubox"')
    with pytest.raises(SetupError, match="address"):
        get_setup("beta", write(tmp_path, text)).card("x")


def test_unknown_keys_are_refused(tmp_path):
    with pytest.raises(SetupError, match="unknown keys"):
        load_setups(write(tmp_path, GOOD.replace("temperature", "temprature")))


def test_url_and_model_are_required(tmp_path):
    with pytest.raises(SetupError, match="'model' is required"):
        load_setups(write(tmp_path, '[gamma]\nurl = "http://localhost:1/v1"\n'))


def test_missing_file_says_what_to_do(tmp_path):
    with pytest.raises(SetupError, match="endpoints.example.toml"):
        load_setups(tmp_path / "endpoints.local.toml")


def test_unknown_setup_lists_the_known_ones(tmp_path):
    with pytest.raises(SetupError, match="alpha, beta"):
        get_setup("delta", write(tmp_path, GOOD))


def test_setup_ids_are_random_and_stable(tmp_path):
    ids = tmp_path / "ids.json"
    first = setup_id("alpha", ids)
    assert setup_id("alpha", ids) == first
    assert setup_id("beta", ids) != first
    assert len(first) == 12
