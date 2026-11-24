"""Loading the config file."""
import json

from bt.config.validate import validate_config
from bt.errors import ConfigError


def read_json(path):
    """Parse a JSON file; a syntax error is a ConfigError naming the line."""
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path}: not valid JSON ({exc.msg}, line {exc.lineno})") from None


def load_config(path):
    """Read the JSON config, check it and lay it over DEFAULTS. Unknown keys are an error, so a typo cannot pass
    silently. Returns the complete config; its `signal` section is kept as the file gives it."""
    return validate_config(path, read_json(path))
