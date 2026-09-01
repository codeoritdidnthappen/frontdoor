"""Makes the repo root importable, so `from tests.x import y` works under bare `pytest`.

CI runs `pytest`, not `python -m pytest`. The `-m` form puts the working directory on `sys.path`;
the bare form does not, so cross-test imports resolved on a laptop and failed collection on CI —
which meant the tests guarding the seal never ran on a pull request. Adding the root here, rather
than a `tests/__init__.py`, keeps pytest's rootdir-based discovery unchanged.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
