"""Dump the OpenAPI spec to ``openapi.json`` for deterministic Orval generation.

Run in CI so the frontend regenerates its client from a committed artifact rather
than hitting a live server::

    python -m scripts.export_openapi            # -> ./openapi.json
    python -m scripts.export_openapi build/api.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.main import app


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
    out.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
    print(f"Wrote {out} ({len(app.openapi()['paths'])} paths)")


if __name__ == "__main__":
    main()
