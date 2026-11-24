"""Allow ``python -m folio.compliance``."""

import sys

from folio.compliance.cli import main

if __name__ == "__main__":
    sys.exit(main())
