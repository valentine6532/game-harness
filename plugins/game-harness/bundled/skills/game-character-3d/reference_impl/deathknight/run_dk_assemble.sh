#!/bin/bash
# deathknight: fit + merge the parts (assemble_parts.py) -> remove the second face Tripo projected onto the neck fur (fix_ghost.py)
# usage: bash workspace/deathknight/run_dk_assemble.sh   (writes assembly/final; then run_dk_process.sh)
cd "$(dirname "$0")"
W=$(pwd -W)
NOWIN="pythonw D:/HarnessPrograming/diablo/workspace/plaza_v2/tools/nowin.py"
BL=D:/blander/blender.exe
rm -f assembly/final/T_Hero_BaseColor.pre_ghost.png      # a fresh atlas is the new original
C=$(NAME=Hero python assembly/make_cfg.py final head,arm_r,arm_l,torso,legs '{"arm_r":{"trim":{"above_z":0.80}},"arm_l":{"trim":{"above_z":0.80}}}')
$NOWIN $BL -b --python tools/assemble_parts.py -- "$C" 2>&1 | grep -E "FIT|CLASSES|ASSEMBLE_DONE|Error|Traceback" | cut -c1-160
$NOWIN $BL -b --python tools/fix_ghost.py -- "$W/assembly/final/Hero_low.glb" "$W/assembly/final/T_Hero_BaseColor.png" \
  "{\"y\":[0.008,0.06],\"z\":[0.815,0.87],\"nx_min\":0.2,\"parts_npy\":\"$W/assembly/final/parts.npy\",\"part\":0}" 2>&1 | grep -E "GHOST|Error|Traceback"
