"""The rules, one module per kind.

A rule module provides:

    KIND                       the kind it decides, as it appears in the feed
    key(event)                 the alert's key, "<kind>:..." (mutes and the cooldown go by it)
    evaluate(event, settings)  a Finding (alertd/model.py) when the event is worth an alert, otherwise None.
                               ``settings`` is the kind's own section of the settings: its table in
                               alertd/defaults.toml, as the config file sets it.

A rule decides only whether an event is worth an alert, how serious it is and why. It never looks at the state:
staleness, mutes, quiet hours, the cooldown and the daily cap are the shared suppressions (alertd/suppress.py),
which the engine applies to every kind alike. A rule reads its event's fields with the Event helpers
(alertd/feed.py), which raise EventError for a field that is absent or of the wrong type, and writes the parts of
its message with alertd/format.py."""
