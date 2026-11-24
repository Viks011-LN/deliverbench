"""Comparison of the book with its benchmark index: ``python -m folio.benchmark``.

Reads the index constituents and weights (benchmark.csv) and the daily index
levels (benchmark_levels.csv) next to the usual data files, and reports where
the book differs from the index and how far its returns have strayed. See
docs/benchmark.md. Nothing in the core ``folio`` commands reads these files.
"""
