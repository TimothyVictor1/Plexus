"""Look for work that has got stuck and prepare something for a person to approve.

    uv run python -m scripts.check_triggers [--org demo]

Background work: it talks to the model vendor, so it never runs inside a request.
"""

from __future__ import annotations

import argparse
import asyncio

from core.db.pool import close_pool
from core.review import create_from_triggers
from scripts.fixtures.demo import DEMO_TENANT


async def main() -> None:
    parser = argparse.ArgumentParser(description="Create review items from stuck work")
    parser.add_argument("--org", default=DEMO_TENANT)
    args = parser.parse_args()
    created = await create_from_triggers(args.org)
    print(f"{len(created)} new things waiting for a person")
    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
