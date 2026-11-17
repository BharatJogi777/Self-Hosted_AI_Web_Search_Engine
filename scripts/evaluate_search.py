from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.search.evaluation import evaluate_run, metrics_as_dict


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate ranked search results against relevance judgments."
    )
    parser.add_argument("--qrels", type=Path, default=Path("evaluation/queries.json"))
    parser.add_argument("--run", type=Path, default=Path("evaluation/sample_run.json"))
    parser.add_argument("-k", type=int, default=10)
    args = parser.parse_args()

    with args.qrels.open(encoding="utf-8") as handle:
        judgments = json.load(handle)
    with args.run.open(encoding="utf-8") as handle:
        run = json.load(handle)

    per_query, aggregate = evaluate_run(
        judgments["queries"],
        run["results"],
        k=args.k,
    )
    print(json.dumps({
        "aggregate": metrics_as_dict(aggregate),
        "per_query": [metrics_as_dict(item) for item in per_query],
    }, indent=2))


if __name__ == "__main__":
    main()
