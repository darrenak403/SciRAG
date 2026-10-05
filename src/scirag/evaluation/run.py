"""Runs evaluation configs and writes what they measured.

    python -m scirag.evaluation.run --config eval/configs/baseline.toml [more.toml ...]
    python -m scirag.evaluation.run --clean     # delete the evaluation accounts and papers

Each run is saved to eval-results/<name>-<time>.json with its full config, and
its table is printed. Papers are indexed on first use and reused afterwards.
"""

import argparse
import asyncio
import json
from pathlib import Path

from scirag.db.engine import get_engine
from scirag.evaluation import corpus
from scirag.evaluation.report import table
from scirag.evaluation.runner import RunConfig, run

CACHE = Path("eval-data")
RESULTS = Path("eval-results")


async def _main(configs: list[Path], clean: bool) -> None:
    try:
        if clean:
            print(f"Removed {await corpus.remove_all()} evaluation accounts.")
        for path in configs:
            result = await run(RunConfig.from_file(path), CACHE)
            RESULTS.mkdir(exist_ok=True)
            stamp = result["started_at"][:19].replace(":", "").replace("-", "")
            saved = RESULTS / f"{result['name']}-{stamp}.json"
            saved.write_text(json.dumps(result, indent=1, default=str))
            print(table(result), f"\n\nSaved to {saved}\n")
    finally:
        await get_engine().dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, nargs="+", default=[])
    parser.add_argument("--clean", action="store_true")
    arguments = parser.parse_args()
    if not arguments.config and not arguments.clean:
        parser.error("give --config or --clean")
    asyncio.run(_main(arguments.config, arguments.clean))


if __name__ == "__main__":
    main()
