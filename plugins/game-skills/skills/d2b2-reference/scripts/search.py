"""Search the local D2B2 item archive or print a full item record."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_ROOT = Path.home() / ".agents" / "reference-data" / "d2b2"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="*", help="Words in Korean or English item names")
    parser.add_argument("--id", help="Print catalog and raw tooltip data for an exact item ID")
    parser.add_argument("--kind", choices=["base", "unique", "set", "runeword"])
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="Print search results as JSON")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    root = args.data_root.expanduser().resolve()
    latest_path = root / "latest.json"
    if not latest_path.is_file():
        parser.error(f"Archive not found: {latest_path}. Run sync.py first.")
    metadata = json.loads(latest_path.read_text(encoding="utf-8"))
    snapshot = root / metadata["snapshot"]

    if args.id:
        catalog = json.loads((snapshot / "catalog.json").read_text(encoding="utf-8"))
        item = next((item for item in catalog["items"] if item["id"] == args.id), None)
        if item is None:
            parser.error(f"Unknown item ID: {args.id}")
        tooltip_path = snapshot / "tooltips" / "items" / Path(*args.id.split(":"))
        tooltip_path = tooltip_path.with_suffix(".json")
        tooltip = json.loads(tooltip_path.read_text(encoding="utf-8"))
        names = {}
        for language in metadata["languages"]:
            data = json.loads((snapshot / "names" / f"{language}.json").read_text(encoding="utf-8"))
            names[language] = data.get(item["nameKey"], item["nameKey"])
        print(json.dumps({"version": metadata["game_version"], "item": item,
                          "names": names, "tooltip": tooltip}, ensure_ascii=False, indent=2))
        return

    terms = [term.casefold() for term in args.query if term.strip()]
    if not terms:
        parser.error("Provide a search query or --id")
    matches = []
    with (snapshot / "records.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            if args.kind and record["kind"] != args.kind:
                continue
            haystack = " ".join(str(value) for value in record.values()).casefold()
            if all(term in haystack for term in terms):
                matches.append(record)
    if args.json:
        print(json.dumps({"version": metadata["game_version"], "total": len(matches),
                          "items": matches[:args.limit]}, ensure_ascii=False, indent=2))
    else:
        print(f"D2B2 {metadata['game_version']}: {len(matches)} matches")
        for record in matches[:args.limit]:
            print(f"{record['id']:24} {record['name_ko']} / {record['name_en']}")
        if len(matches) > args.limit:
            print(f"... {len(matches) - args.limit} more; use --limit or --json")


if __name__ == "__main__":
    main()
