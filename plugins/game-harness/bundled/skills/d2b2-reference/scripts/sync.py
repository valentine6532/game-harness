"""Archive D2B2's public, versioned D2R item data for local reference."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import quote
from urllib.request import Request, urlopen


SOURCE = "https://d2b2.pages.dev/data/"
DEFAULT_ROOT = Path.home() / ".agents" / "reference-data" / "d2b2"
USER_AGENT = "Mozilla/5.0 (compatible; D2B2PersonalReferenceArchive/1.0)"
VERSION_PATH = re.compile(r"^versions/[A-Za-z0-9._-]+/$")
ITEM_ID = re.compile(r"^[a-z-]+:[A-Za-z0-9_-]+$")
IMAGE_ID = re.compile(r"^[0-9a-f]{64}$")


def fetch(relative_path: str) -> bytes:
    url = SOURCE + quote(relative_path, safe="/._-")
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=30) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}: {url}")
                return response.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(0.7 * (attempt + 1))
    raise AssertionError("unreachable")


def write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_bytes(payload)
    temporary.replace(path)


def json_file(snapshot: Path, version_path: str, relative_path: str):
    target = snapshot / relative_path
    if target.is_file():
        try:
            return json.loads(target.read_bytes())
        except (OSError, ValueError):
            pass
    payload = fetch(version_path + relative_path)
    document = json.loads(payload)
    write_atomic(target, payload)
    return document


def image_file(snapshot: Path, image_id: str) -> None:
    target = snapshot / "images" / f"{image_id}.webp"
    if target.is_file() and target.stat().st_size > 12:
        return
    payload = fetch("images/" + image_id + ".webp")
    if payload[:4] != b"RIFF" or payload[8:12] != b"WEBP":
        raise ValueError(f"Invalid WebP: {image_id}")
    write_atomic(target, payload)


def run_jobs(label: str, jobs, worker, workers: int):
    jobs = list(jobs)
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(worker, job): job for job in jobs}
        for done, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                results.append((job, future.result()))
            except Exception as exc:
                raise RuntimeError(f"{label} failed for {job}: {exc}") from exc
            if done % 200 == 0 or done == len(jobs):
                print(f"{label}: {done}/{len(jobs)}", flush=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    args = parser.parse_args()
    root = args.data_root.expanduser().resolve()

    index_payload = fetch("index.json")
    versions = json.loads(index_payload)
    if not isinstance(versions, list) or not versions:
        raise ValueError("Missing version index")
    version = versions[-1]
    version_path = version["path"]
    if not VERSION_PATH.fullmatch(version_path):
        raise ValueError(f"Unexpected version path: {version_path}")
    if not isinstance(version.get("languages"), list) or not version["languages"]:
        raise ValueError("Missing languages")

    snapshot = root / version_path.rstrip("/")
    snapshot.mkdir(parents=True, exist_ok=True)
    write_atomic(root / "source-index.json", index_payload)
    print(f"Version {version['gameVersion']} ({version['date']})", flush=True)

    catalog = json_file(snapshot, version_path, "catalog.json")
    core = json_file(snapshot, version_path, "tooltips/core.json")
    items = catalog["items"]
    if not items or len({item["id"] for item in items}) != len(items):
        raise ValueError("Empty catalog or duplicate item IDs")
    for item in items:
        if not ITEM_ID.fullmatch(item["id"]):
            raise ValueError(f"Unexpected item ID: {item['id']}")
    if not core.get("tables"):
        raise ValueError("Empty tooltip core")

    languages = version["languages"]
    localized_paths = [f"names/{lang}.json" for lang in languages]
    localized_paths += [f"tooltips/strings/{lang}.json" for lang in languages]
    run_jobs("Languages", localized_paths,
             lambda path: json_file(snapshot, version_path, path), args.workers)

    item_paths = ["tooltips/items/" + item["id"].replace(":", "/", 1) + ".json"
                  for item in items]
    tooltip_files = run_jobs("Tooltips", item_paths,
                             lambda path: json_file(snapshot, version_path, path), args.workers)
    images = {item["image"] for item in items if item.get("image")}
    for _, part in tooltip_files:
        for item in part.get("items", []):
            if item.get("image"):
                images.add(item["image"])
    if any(not IMAGE_ID.fullmatch(image_id) for image_id in images):
        raise ValueError("Unexpected image ID")
    run_jobs("Images", sorted(images), lambda image_id: image_file(snapshot, image_id),
             args.workers)

    ko = json.loads((snapshot / "names/koKR.json").read_bytes())
    en = json.loads((snapshot / "names/enUS.json").read_bytes())
    records = []
    for item in items:
        key = item["nameKey"]
        base = next((other for other in items if other["id"] == item.get("baseId")), None)
        record = {
            "id": item["id"], "kind": item["kind"],
            "name_ko": ko.get(key) or en.get(key) or key,
            "name_en": en.get(key) or key,
            "base_ko": (ko.get(base["nameKey"]) or en.get(base["nameKey"]) or base["nameKey"]) if base else "",
            "code": item.get("code", ""), "type": item.get("type", ""),
            "tooltip": "tooltips/items/" + item["id"].replace(":", "/", 1) + ".json",
        }
        records.append(record)
    records_payload = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                              for row in records).encode("utf-8")
    write_atomic(snapshot / "records.jsonl", records_payload)
    summary = {
        "source": "https://d2b2.pages.dev/", "data_source": SOURCE,
        "game_version": version["gameVersion"], "source_date": version["date"],
        "version_path": version_path, "snapshot": version_path.rstrip("/"),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "item_count": len(items), "set_count": len(catalog["sets"]),
        "tooltip_count": len(item_paths), "image_count": len(images),
        "languages": languages,
        "catalog_sha256": hashlib.sha256((snapshot / "catalog.json").read_bytes()).hexdigest(),
    }
    manifest = json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    write_atomic(snapshot / "manifest.json", manifest)
    write_atomic(root / "latest.json", manifest)
    print(f"Complete: {len(items)} items, {len(images)} images -> {snapshot}", flush=True)


if __name__ == "__main__":
    main()
