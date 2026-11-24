"""Allow ``python -m folio.benchmark``."""

import sys

from folio.benchmark.cli import main

if __name__ == "__main__":
    sys.exit(main())
