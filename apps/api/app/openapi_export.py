"""Write the OpenAPI contract the TypeScript client is generated from.

Usage: ``python -m app.openapi_export <path>``. Output is deterministic (sorted keys) so the
committed file only changes when the contract does.
"""

import json
import sys
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.main import create_app


def openapi_document() -> dict[str, Any]:
    settings = Settings(_env_file=None, environment="test")
    return create_app(settings).openapi()


def render() -> str:
    return json.dumps(openapi_document(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m app.openapi_export <path>", file=sys.stderr)
        return 2
    Path(argv[0]).write_text(render(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
