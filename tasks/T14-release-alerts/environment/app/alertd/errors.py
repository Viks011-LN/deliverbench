"""The errors alertd reports to whoever runs it.

cli.py turns a ConfigError, FeedError or StateError into one line on stderr and exit status 2. An EventError
concerns one event only: the engine skips that event with a note and decides the rest of the feed as usual."""


class AlertdError(Exception):
    """Something alertd cannot work with; the message says what and where."""


class ConfigError(AlertdError):
    """A settings file alertd refuses: an unknown key, a value of the wrong type, a file it cannot read."""


class FeedError(AlertdError):
    """A feed line that is not an event: not a JSON object, or without a kind, an id or a time."""


class EventError(AlertdError):
    """An event its rule cannot read: a field the rule needs is absent or of the wrong type."""


class StateError(AlertdError):
    """A state file alertd cannot read or write."""
