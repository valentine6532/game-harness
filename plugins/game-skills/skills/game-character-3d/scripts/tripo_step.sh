#!/bin/bash
# One Tripo task without a console window, logged to the ledger.
#   bash tripo_step.sh <out dir> <asset tag> <tripo command...>
#   e.g. tripo_step.sh body/model dk generate multiview-to-model f.png l.png b.png r.png --model tripo-v3.1 \
#          -p texture_quality=detailed -p geometry_quality=detailed -p pbr=true
# Adds --out/--json/--no-open/--yes/--timeout 3600, prints "<out dir> <task id> <credits> <status> <error>" and the
# balance, appends {at, asset, purpose, task_id} to $LEDGER. Tripo's progress and errors land in result.json (nowin.py
# merges stderr into stdout); err.txt only catches nowin.py itself. Keep the task id: after a timeout or reboot download the
# result with `tripo task get <id> --download -o <dir>` instead of submitting (and paying) again.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/../config.env"
OUT=$1; ASSET=$2; shift 2
WHAT=$(echo "$*" | cut -c1-240 | tr '"' "'")   # full command (inputs included) for the ledger
mkdir -p "$OUT"
pythonw "$HERE/nowin.py" "$TRIPO" "$@" --out "$OUT" --json --no-open --yes --timeout 3600 > "$OUT/result.json" 2> "$OUT/err.txt" < /dev/null
fields=$(python - "$OUT/result.json" <<'PY'
import json, sys
t = open(sys.argv[1], encoding='utf-8', errors='replace').read()
d = {}
for l in reversed(t.splitlines()):          # generate/mesh/anim print one JSON line
    if l.startswith('{') and l.rstrip().endswith('}'):
        try: d = json.loads(l); break
        except ValueError: pass
if not d and '{' in t:                       # task get prints indented JSON
    try: d = json.loads(t[t.index('{'):])
    except ValueError: pass
print(d.get('task_id', ''), d.get('credits_consumed', ''), d.get('status', ''), d.get('error', ''))
PY
)
tid=${fields%% *}
echo "{\"at\":\"$(date +%FT%T)\",\"asset\":\"$ASSET\",\"purpose\":\"$OUT: $WHAT\",\"task_id\":\"$tid\"}" >> "$LEDGER"
echo "$OUT $fields"
pythonw "$HERE/nowin.py" "$TRIPO" balance 2>&1 | tail -1
