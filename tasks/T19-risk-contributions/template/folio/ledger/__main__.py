"""Allow ``python -m folio.ledger``."""

import sys

from folio.ledger.cli import main

if __name__ == "__main__":
    sys.exit(main())
