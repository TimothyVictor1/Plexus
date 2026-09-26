"""Regenerate the plain-language wording for every process in an org.

    uv run python -m scripts.refresh_labels [--org demo]

Background work: it talks to the model vendor, so it must never run inside a request.
"""

from __future__ import annotations

import argparse
import asyncio

from core.db.pool import close_pool
from core.processes.service import refresh_labels
from scripts.fixtures.demo import DEMO_TENANT


async def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate plain-language process names")
    parser.add_argument("--org", default=DEMO_TENANT)
    args = parser.parse_args()
    for process_id, outcome in (await refresh_labels(args.org)).items():
        print(f"{process_id:22} {outcome}")
    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
