"""bt: the desk's cross-sectional equity backtest.

    python -m bt --prices PRICES.csv --config CONFIG.json [--equity EQUITY.csv]
                 [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--format json|text]

README.md documents every option and every setting of the config file; docs/ARCHITECTURE.md describes the
modules and the day loop.

Only the standard library is used, on purpose: the desk runs this on machines where installing a package takes a
ticket. All arithmetic is plain Python floats in a fixed order, so a run is reproducible bit for bit, and the
golden files in tests/golden depend on that.
"""

__version__ = "4.7.2"
