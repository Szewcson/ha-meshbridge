from __future__ import annotations

import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).parents[1] / "rootfs" / "usr" / "local" / "lib"
sys.path.insert(0, str(MODULE_ROOT))
