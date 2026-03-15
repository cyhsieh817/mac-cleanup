#!/usr/bin/env python3
"""mac-cleanup — run directly without pip install."""

import sys
from pathlib import Path

# Allow running from repo root without installation
sys.path.insert(0, str(Path(__file__).parent))

from mac_cleanup.cli import main

if __name__ == "__main__":
    main()
