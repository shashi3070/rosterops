"""Allow ``python -m rosterops``."""

from __future__ import annotations

import sys

from rosterops.cli import main

if __name__ == "__main__":
    sys.exit(main())
