"""
Root conftest shared by both tests/unit/ and tests/integration/
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
