#!/bin/bash
# run_codex.sh <dir> <tag> <prompt text file> <out png> <image...>   -> <dir>/<tag>_stdout.txt, <dir>/<out png>
# codex sometimes fails to copy the image out of its sandbox; then take it from the session's generated_images folder.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
D=$1; TAG=$2; P=$3; OUT=$4; shift 4
IMGS=(); for f in "$@"; do IMGS+=(-i "$f"); done
cd "$D"; rm -f "$OUT"
pythonw "$HERE/nowin.py" codex exec --sandbox workspace-write --skip-git-repo-check --cd . "${IMGS[@]}" -o ${TAG}.md "$(cat $P)" < /dev/null > ${TAG}_stdout.txt 2>&1
if [ ! -f "$OUT" ]; then
  sid=$(grep -m1 "session id" ${TAG}_stdout.txt | awk '{print $3}')
  G=$(ls -d "$APPDATA"/orca/codex-accounts/*/home/generated_images/$sid ${CODEX_HOME:-~/.codex}/generated_images/$sid ~/.codex/generated_images/$sid 2>/dev/null | head -1)
  f=$(ls -t $G/*.png 2>/dev/null | head -1); [ -n "$f" ] && cp "$f" "$OUT"
fi
echo "$D $TAG $( [ -f "$OUT" ] && echo ok || echo MISSING )"
