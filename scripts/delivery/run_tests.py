"""Run the delivery protocol suite from any cwd, with no third-party packages."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/delivery"))
suite = unittest.defaultTestLoader.discover(str(ROOT / "tests/delivery"), pattern="test_*.py")
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
