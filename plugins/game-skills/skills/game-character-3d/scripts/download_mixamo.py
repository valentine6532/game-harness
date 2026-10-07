"""Retrieve exact Mixamo motion IDs from a public archive (copied from the World of Oldcraft kit, 2026-09-29).

Example: python $SKILL/scripts/download_mixamo.py --motion-id <UUID> --output <folder>
Requires requests. This is a source acquisition tool; it does not retarget or export.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import requests

REPO = 'Linzhan/Mixamo-Animations-Characters'
BASE = 'https://huggingface.co/datasets/' + REPO
HEADER = b'Kaydara FBX Binary  \x00\x1a\x00'


def get(url):
    response = requests.get(url, timeout=(20, 120))
    response.raise_for_status()
    return response


def acquire(ids, output, revision='main'):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    info = get('https://huggingface.co/api/datasets/' + REPO + '/revision/' + quote(revision, safe='')).json()
    sha = info['sha']
    raw_base = BASE + '/resolve/' + sha + '/'
    metadata = get(raw_base + 'metadata.csv').content
    rows = list(csv.DictReader(io.StringIO(metadata.decode('utf-8-sig'))))
    receipt_path = output / 'downloads.json'
    prior = json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else []
    by_id = {r['motion_id']: r for r in prior}
    downloaded = []
    for motion_id in dict.fromkeys(ids):
        found = [r for r in rows if r.get('motion_id') == motion_id]
        if len(found) != 1:
            raise ValueError(f'Expected one metadata row for {motion_id}, got {len(found)}')
        row = found[0]
        path = PurePosixPath(row['file'])
        if len(path.parts) != 2 or path.parts[0] != 'animation' or path.suffix.lower() != '.fbx':
            raise ValueError('Unexpected archive path: ' + row['file'])
        url = raw_base + quote(row['file'], safe='/')
        payload = get(url).content
        if not payload.startswith(HEADER) or len(payload) < 1024:
            raise ValueError('Response is not a binary FBX: ' + url)
        digest = hashlib.sha256(payload).hexdigest()
        target = output / path.name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise FileExistsError('Refusing to overwrite a different local file: ' + str(target))
        if not target.exists():
            temporary = target.with_suffix('.fbx.part')
            temporary.write_bytes(payload)
            temporary.replace(target)
        record = dict(row, url=url, local=path.name, bytes=len(payload), sha256=digest,
                      archive=REPO, archive_revision=sha,
                      metadata_sha256=hashlib.sha256(metadata).hexdigest(),
                      verification='Binary header checked; inspect FBX timing and skeletal curves before retargeting.')
        by_id[motion_id] = record
        downloaded.append(record)
        # Preserve successful acquisitions if a later network request fails.
        receipt_path.write_text(json.dumps(list(by_id.values()), indent=2) + '\n', encoding='utf-8')
        print(json.dumps(record), flush=True)
    (output / 'metadata.csv').write_bytes(metadata)
    return downloaded


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--motion-id', action='append', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--revision', default='main')
    args = parser.parse_args()
    acquire(args.motion_id, args.output, args.revision)
