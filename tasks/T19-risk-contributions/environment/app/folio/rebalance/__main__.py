"""Allow ``python -m folio.rebalance``."""

import sys

from folio.rebalance.cli import main

if __name__ == "__main__":
    sys.exit(main())
