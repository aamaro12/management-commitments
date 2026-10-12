#!/usr/bin/env python3
"""Portable entrypoint; works without installing the package."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from management_commitments.cli import main

raise SystemExit(main())
