"""The strategies: one module per signal type, bt/strategies/<type>.py, picked up by the config's `signal.type`.

docs/design/strategy-slot.md says what a strategy module defines (PARAMETERS, warmup(params) and score(history,
params)) and what the engine does around it; docs/strategies.md describes the desk's strategies, and
bt/signals/slot.py is the engine's side of the slot. A new strategy is a new file here, and nothing else changes.

Every module in this package is a strategy. This file defines nothing else on purpose: a strategy module becomes
an attribute of the package when it is imported, so any name defined here could clash with a strategy's.
"""
