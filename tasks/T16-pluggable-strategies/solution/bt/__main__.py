"""The entry point: python -m bt (the options are in bt/cli.py and README.md)."""
import sys

from bt.cli import main

sys.exit(main())
