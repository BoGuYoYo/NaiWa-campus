"""pytest 根配置：把仓库根加入 sys.path，保证 python -m pytest 与 pytest 行为一致。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
