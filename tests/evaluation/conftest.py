"""Rend les fabriques de `tests/tools/text_helpers.py` importables (mode `importlib`)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
