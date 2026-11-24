"""Allow ``python -m folio.scenarios``."""

import sys

from folio.scenarios.cli import main

if __name__ == "__main__":
    sys.exit(main())
