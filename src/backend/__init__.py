"""skillRadar — AI coding tool skill/plugin trending radar."""

import sys
from pathlib import Path

# `src.backend`으로 임포트될 때도 `backend.*` 절대 임포트가 동작하도록 src/를 경로에 추가한다.
_SRC = str(Path(__file__).resolve().parent.parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
