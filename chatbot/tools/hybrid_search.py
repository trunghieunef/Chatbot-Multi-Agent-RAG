from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.rag import hybrid_search as _backend_hybrid_search  # noqa: E402

if __name__ != "__main__":
    sys.modules[__name__] = _backend_hybrid_search
else:
    import argparse
    import asyncio
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(_backend_hybrid_search.hybrid_search(args.query)),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
