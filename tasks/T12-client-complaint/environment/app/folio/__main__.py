"""Allow ``python -m folio``."""

import sys

from folio.cli import main

if __name__ == "__main__":
    sys.exit(main())
