import sys
from pathlib import Path

# Ensure both monorepo root and backend root are in sys.path for flexible execution
backend_dir = Path(__file__).resolve().parent.parent
monorepo_root = backend_dir.parent

for p in [str(monorepo_root), str(backend_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)
