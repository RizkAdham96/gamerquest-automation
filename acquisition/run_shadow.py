import argparse
from pathlib import Path

from acquisition.engine import write_shadow_queue


def main(root: Path | str | None = None, output_path: Path | str | None = None) -> int:
    root_path = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    target = Path(output_path) if output_path is not None else root_path / "acquisition" / "shadow_queue.json"
    payload = write_shadow_queue(root_path, target)

    print("\n===================================")
    print("GAMERQUEST ACQUISITION SHADOW")
    print("===================================")
    print(f"Opportunities: {payload['count']}")

    visible = [
        item
        for item in payload.get("opportunities", [])
        if item.get("decision") in {"PRIORITIZE", "WATCH"}
    ][:10]

    if not visible:
        print("No PRIORITIZE/WATCH opportunities in this run.")
        return 0

    for index, item in enumerate(visible, start=1):
        print(
            f"{index}. [{item.get('decision')}] "
            f"{item.get('score')}/100 — {item.get('title')}"
        )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build GamerQuest acquisition shadow queue")
    parser.add_argument("--root", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    raise SystemExit(main(root=args.root, output_path=args.output))
