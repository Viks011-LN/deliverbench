"""alertd: the desk's alert system.

Events come in on a feed. For each, the rule for its kind decides whether it is worth an alert, how serious it is
and why; the shared suppressions decide whether the alert is sent; the message is written in the house style.
README.md says how alertd is run; docs/ARCHITECTURE.md describes its parts."""

__version__ = "1.6.2"
